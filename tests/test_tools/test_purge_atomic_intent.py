from __future__ import annotations

import os
import queue
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest

import knowledge_server.storage.database as database
from knowledge_server.models import SuggestionDecision
from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.decisions import submit_suggestion_decisions
from knowledge_server.tools.evidence import get_evidence
from knowledge_server.tools.evidence_chain import get_suggestion_evidence_chain
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.suggest import suggest_fields, suggest_manifest_candidates
from tests.test_tools.test_ks_hard_purge import (
    _catalog_row,
    _fts_shadow_bytes,
    _ingest,
    _manifest_suggestion_row,
    _sqlite_storage_bytes,
    _write_catalog_csv,
)

ERASED_TERM = "qxzsharedprefixzzzzatomicuniquetailjkvw"
ERASED_SUFFIX = b"zzzzatomicuniquetailjkvw"
RETAINED_TERM = "qxzsharedprefixaaaa"

# Test-only synchronization at actual transaction/maintenance boundaries. The
# parent kills only this child after its ready line, never after a timed sleep.
PURGE_CHILD = r"""
import sys
from knowledge_server.storage import KnowledgeStore

store = KnowledgeStore(sys.argv[1])
document_id, stage = sys.argv[2:]

def pause():
    print("PURGE_BOUNDARY:" + stage, flush=True)
    sys.stdin.buffer.read(1)
    raise RuntimeError("parent must terminate the synchronized child")

def trace(sql):
    normalized = " ".join(sql.lower().split())
    if stage == "fts_optimize" and "values('optimize')" in normalized:
        pause()
    if stage == "checkpoint" and normalized == "pragma wal_checkpoint(truncate)":
        pause()
    if stage == "vacuum" and normalized == "vacuum":
        pause()

class PauseBeforeClearCommit:
    def __init__(self, connection):
        self.connection = connection
        self.clearing = False
    def __getattr__(self, name):
        return getattr(self.connection, name)
    def __enter__(self):
        self.connection.__enter__()
        return self
    def __exit__(self, *args):
        if self.clearing and args[0] is None:
            pause()
        return self.connection.__exit__(*args)
    def execute(self, sql, *args):
        result = self.connection.execute(sql, *args)
        if "delete from purge_scrub_pending" in " ".join(sql.lower().split()):
            self.clearing = True
        return result

if stage == "before_maintenance":
    store._scrub_sqlite_storage_after_purge = pause
elif stage == "clear_commit":
    store.conn = PauseBeforeClearCommit(store.conn)
else:
    store.conn.set_trace_callback(trace)
store.purge_document("project-a", document_id, confirm_purge=True)
raise RuntimeError("purge did not reach the requested boundary")
"""


@pytest.mark.parametrize("soft_deleted", [False, True])
@pytest.mark.parametrize(
    "stage",
    ["before_maintenance", "fts_optimize", "checkpoint", "vacuum", "clear_commit"],
)
def test_terminated_purge_retains_intent_and_retries_after_reopen(
    tmp_path: Path,
    soft_deleted: bool,
    stage: str,
) -> None:
    store, document_id, retained_id, source_files = _prepare_store(tmp_path)
    # Force prefix compression and prove full-term bytes alone would miss the term.
    with store.conn:
        store.conn.execute("INSERT INTO document_chunks(document_chunks) VALUES('optimize')")
    index_bytes = b"".join(
        row[0] for row in store.conn.execute("SELECT block FROM document_chunks_data")
    )
    assert ERASED_TERM.encode() not in index_bytes
    assert ERASED_SUFFIX in index_bytes
    assert get_evidence(store=store, project_id="project-a", query=ERASED_TERM).chunk_count > 0
    assert ERASED_SUFFIX in _sqlite_storage_bytes(store.db_path)
    if soft_deleted:
        assert store.delete_document("project-a", document_id).success
    store.close()

    _terminate_at_boundary(tmp_path / "ks.sqlite3", document_id, stage)

    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    assert store._find_document_any_state("project-a", document_id) is None
    assert store._purge_scrub_pending_exists(project_id="project-a", document_id=document_id)
    if stage in ("before_maintenance", "fts_optimize"):
        assert ERASED_SUFFIX in _fts_shadow_bytes(store)
    if stage == "clear_commit":
        assert ERASED_SUFFIX not in _fts_shadow_bytes(store)
        assert ERASED_SUFFIX not in _sqlite_storage_bytes(store.db_path)
    assert not store.purge_document("other-project", document_id, confirm_purge=True).success
    assert not store.purge_document("project-a", document_id).success
    assert store._purge_scrub_pending_exists(project_id="project-a", document_id=document_id)

    result = store.purge_document("project-a", document_id, confirm_purge=True)

    assert result.success, result.warnings
    assert not store._purge_scrub_pending_exists(project_id="project-a", document_id=document_id)
    assert ERASED_SUFFIX not in _fts_shadow_bytes(store)
    assert ERASED_SUFFIX not in _sqlite_storage_bytes(store.db_path)
    assert not store.conn.execute(
        "SELECT 1 FROM manifest_suggestions WHERE project_id='project-a'"
    ).fetchall()
    assert not store.conn.execute(
        "SELECT 1 FROM manifest_suggestion_review_state WHERE project_id='project-a'"
    ).fetchall()
    _assert_retained_state(store, retained_id, source_files)
    store.close()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _assert_retained_state(store, retained_id, source_files)
    store.close()


@pytest.mark.parametrize("failure", ["intent_write", "final_delete", "commit"])
@pytest.mark.parametrize("soft_deleted", [False, True])
def test_deletion_and_intent_roll_back_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    soft_deleted: bool,
) -> None:
    store, document_id, _, _ = _prepare_store(tmp_path)
    if soft_deleted:
        assert store.delete_document("project-a", document_id).success
    before = _logical_snapshot(store)
    if failure == "commit":
        monkeypatch.setattr(store, "conn", FailCommitConnection(store.conn))
    else:
        event = (
            "BEFORE INSERT ON purge_scrub_pending"
            if failure == "intent_write"
            else "AFTER DELETE ON documents"
        )
        with store.conn:
            store.conn.execute(
                f"CREATE TRIGGER fail_purge {event} BEGIN SELECT RAISE(ABORT, 'injected atomic failure'); END"
            )
    with pytest.raises(sqlite3.DatabaseError, match="injected atomic failure"):
        store.purge_document("project-a", document_id, confirm_purge=True)
    assert not store.conn.in_transaction
    assert _logical_snapshot(store) == before
    assert not store._purge_scrub_pending_exists(project_id="project-a", document_id=document_id)
    assert store.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    store.close()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    assert _logical_snapshot(store) == before
    store.close()


@pytest.mark.parametrize("retry", [False, True])
@pytest.mark.parametrize("failure", ["clear_write", "clear_commit", "warning_write"])
def test_pending_state_persistence_failure_never_reports_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    retry: bool,
    failure: str,
) -> None:
    store, document_id, retained_id, source_files = _prepare_store(tmp_path)
    if retry:
        with monkeypatch.context() as patch:
            patch.setattr(
                store, "_scrub_sqlite_storage_after_purge", lambda: ["injected maintenance error"]
            )
            assert not store.purge_document("project-a", document_id, confirm_purge=True).success
    with monkeypatch.context() as patch:
        if failure == "clear_commit":
            patch.setattr(store, "conn", FailCommitConnection(store.conn, only_clear=True))
        else:
            if failure == "warning_write":
                patch.setattr(
                    store,
                    "_scrub_sqlite_storage_after_purge",
                    lambda: ["injected maintenance error"],
                )
                event = "BEFORE UPDATE ON purge_scrub_pending"
            else:
                event = "BEFORE DELETE ON purge_scrub_pending"
            with store.conn:
                store.conn.execute(
                    f"CREATE TRIGGER fail_persistence {event} BEGIN SELECT RAISE(ABORT, 'injected persistence failure'); END"
                )
        result = store.purge_document("project-a", document_id, confirm_purge=True)
        assert not result.success
        assert "pending cleanup intent remains" in result.warnings[-1]
        assert store._purge_scrub_pending_exists(project_id="project-a", document_id=document_id)
        assert not store.conn.in_transaction
    if failure != "clear_commit":
        with store.conn:
            store.conn.execute("DROP TRIGGER fail_persistence")
    store.close()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    assert store._purge_scrub_pending_exists(project_id="project-a", document_id=document_id)
    assert store.purge_document("project-a", document_id, confirm_purge=True).success
    assert not store._purge_scrub_pending_exists(project_id="project-a", document_id=document_id)
    assert ERASED_SUFFIX not in _fts_shadow_bytes(store)
    assert ERASED_SUFFIX not in _sqlite_storage_bytes(store.db_path)
    _assert_retained_state(store, retained_id, source_files)
    store.close()


def test_retry_clears_only_its_own_intent_and_gates_maintenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, document_id, retained_id, source_files = _prepare_store(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(
            store, "_scrub_sqlite_storage_after_purge", lambda: ["injected maintenance error"]
        )
        assert not store.purge_document("project-a", document_id, confirm_purge=True).success
    store._mark_purge_scrub_pending(
        project_id="project-b", document_id="second-pending", warnings=[]
    )
    store._mark_purge_scrub_pending(
        project_id="project-a", document_id="same-project-pending", warnings=[]
    )
    before = _logical_snapshot(store)

    def unexpected_maintenance():
        pytest.fail("wrong-project or unconfirmed call invoked maintenance")

    with monkeypatch.context() as patch:
        patch.setattr(store, "_scrub_sqlite_storage_after_purge", unexpected_maintenance)
        assert not store.purge_document("project-b", document_id, confirm_purge=True).success
        assert not store.purge_document("project-a", document_id).success
        assert _logical_snapshot(store) == before
    assert store.purge_document("project-a", document_id, confirm_purge=True).success
    assert store._purge_scrub_pending_exists(project_id="project-b", document_id="second-pending")
    assert store._purge_scrub_pending_exists(
        project_id="project-a", document_id="same-project-pending"
    )
    assert not store._purge_scrub_pending_exists(project_id="project-a", document_id=document_id)
    _assert_retained_state(store, retained_id, source_files)
    store.close()


def test_intent_and_all_deletions_share_one_committed_transaction(tmp_path: Path) -> None:
    store, document_id, _, _ = _prepare_store(tmp_path)
    statements = []
    store.conn.set_trace_callback(statements.append)
    assert store.purge_document("project-a", document_id, confirm_purge=True).success
    sql = [" ".join(statement.lower().split()) for statement in statements]
    intent = next(
        i
        for i, statement in enumerate(sql)
        if statement.startswith("insert into purge_scrub_pending")
    )
    commit = next(i for i in range(intent + 1, len(sql)) if sql[i] == "commit")
    assert sql[intent - 1] == "begin"
    for table in (
        "manifest_suggestions",
        "manifest_suggestion_review_state",
        "document_chunks",
        "field_catalog",
        "documents",
    ):
        assert any(
            statement.startswith(f"delete from {table} ") for statement in sql[intent:commit]
        )
    compact = next(i for i, statement in enumerate(sql) if "values('optimize')" in statement)
    clear = next(
        i
        for i, statement in enumerate(sql)
        if statement.startswith("delete from purge_scrub_pending")
    )
    assert commit < compact < clear
    assert sql[clear + 1] == "commit"
    store.close()


@pytest.mark.parametrize("secure_delete", [0, 1, 2])
@pytest.mark.parametrize("retry", [False, True])
@pytest.mark.parametrize("soft_deleted", [False, True])
def test_successful_purge_removes_pending_record_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    secure_delete: int,
    retry: bool,
    soft_deleted: bool,
) -> None:
    store, document_id, retained_id, source_files = _prepare_store(tmp_path)
    setting = {0: "OFF", 1: "ON", 2: "FAST"}[secure_delete]
    store.conn.execute(f"PRAGMA secure_delete = {setting}")
    if soft_deleted:
        assert store.delete_document("project-a", document_id).success
    if retry:
        with monkeypatch.context() as patch:
            patch.setattr(
                store, "_scrub_sqlite_storage_after_purge", lambda: ["injected maintenance error"]
            )
            assert not store.purge_document("project-a", document_id, confirm_purge=True).success
        assert store._purge_scrub_pending_exists(project_id="project-a", document_id=document_id)

    # Capture and positively detect the pending row after VACUUM has placed it
    # in the main file. Its own later deletion must scrub both table/index pages.
    pending_bytes = []
    clear = store._clear_purge_scrub_pending

    def observe_then_clear(**kwargs):
        row = store.conn.execute(
            "SELECT created_at, updated_at FROM purge_scrub_pending "
            "WHERE project_id=? AND document_id=?",
            ("project-a", document_id),
        ).fetchone()
        pending_bytes.extend([document_id.encode(), *(value.encode() for value in row)])
        assert all(value in store.db_path.read_bytes() for value in pending_bytes)
        return clear(**kwargs)

    monkeypatch.setattr(store, "_clear_purge_scrub_pending", observe_then_clear)
    assert document_id.encode() in _sqlite_storage_bytes(store.db_path)
    result = store.purge_document("project-a", document_id, confirm_purge=True)
    assert result.success, result.warnings
    assert not store._purge_scrub_pending_exists(project_id="project-a", document_id=document_id)
    assert all(value not in _sqlite_storage_bytes(store.db_path) for value in pending_bytes)
    assert store.conn.execute("PRAGMA secure_delete").fetchone()[0] == secure_delete
    _assert_retained_state(store, retained_id, source_files)
    store.close()
    assert all(value not in _sqlite_storage_bytes(store.db_path) for value in pending_bytes)
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _assert_retained_state(store, retained_id, source_files)
    store.close()


@pytest.mark.parametrize("failure", ["reader", "checkpoint_error"])
def test_pending_record_checkpoint_failure_is_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    store, document_id, retained_id, source_files = _prepare_store(tmp_path)
    store.conn.execute("PRAGMA secure_delete = OFF")
    store.conn.execute("PRAGMA busy_timeout = 1234")
    reader = sqlite3.connect(store.db_path)
    clear = store._clear_purge_scrub_pending

    def obstruct_finalization(**kwargs):
        if failure == "reader":
            reader.execute("BEGIN")
            assert reader.execute("SELECT COUNT(*) FROM purge_scrub_pending").fetchone()[0] == 1
        else:
            def fail_checkpoint():
                raise sqlite3.OperationalError("injected final checkpoint failure")
            monkeypatch.setattr(store, "_wal_checkpoint_truncate", fail_checkpoint)
        return clear(**kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_clear_purge_scrub_pending", obstruct_finalization)
        result = store.purge_document("project-a", document_id, confirm_purge=True)
    reader.rollback()
    reader.close()
    # Restore the injected checkpoint implementation before the public retry.
    monkeypatch.undo()
    assert not result.success
    assert any("retry" in warning.lower() for warning in result.warnings)
    assert store._purge_scrub_pending_exists(project_id="project-a", document_id=document_id)
    assert not store.conn.in_transaction
    assert store.conn.execute("PRAGMA secure_delete").fetchone()[0] == 0
    assert store.conn.execute("PRAGMA busy_timeout").fetchone()[0] == 1234
    store.close()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    store.conn.execute("PRAGMA secure_delete = OFF")
    assert store.purge_document("project-a", document_id, confirm_purge=True).success
    assert document_id.encode() not in _sqlite_storage_bytes(store.db_path)
    assert not store._purge_scrub_pending_exists(project_id="project-a", document_id=document_id)
    _assert_retained_state(store, retained_id, source_files)
    store.close()


def test_failed_intent_restoration_does_not_claim_retry_state_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, document_id, _, _ = _prepare_store(tmp_path)
    clear = store._clear_purge_scrub_pending

    def fail_checkpoint():
        raise sqlite3.OperationalError("injected final checkpoint failure")

    def fail_restore(**kwargs):
        raise sqlite3.OperationalError("injected intent restoration failure")

    def obstruct_finalization(**kwargs):
        monkeypatch.setattr(store, "_wal_checkpoint_truncate", fail_checkpoint)
        return clear(**kwargs)

    monkeypatch.setattr(store, "_clear_purge_scrub_pending", obstruct_finalization)
    monkeypatch.setattr(store, "_mark_purge_scrub_pending", fail_restore)
    result = store.purge_document("project-a", document_id, confirm_purge=True)
    assert not result.success
    assert "could not be restored or verified" in result.warnings[-1]
    assert not any("intent remains" in warning for warning in result.warnings)
    assert not store._purge_scrub_pending_exists(project_id="project-a", document_id=document_id)
    assert not store.conn.in_transaction
    store.close()


def test_reingest_keeps_pending_intent_until_next_confirmed_purge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, document_id, retained_id, source_files = _prepare_store(tmp_path)
    store.conn.execute("PRAGMA secure_delete = OFF")
    with monkeypatch.context() as patch:
        patch.setattr(
            store, "_scrub_sqlite_storage_after_purge", lambda: ["injected maintenance error"]
        )
        assert not store.purge_document("project-a", document_id, confirm_purge=True).success
    refreshed = _ingest(store, tmp_path, tmp_path / "erased.csv")
    assert refreshed.document_id == document_id
    assert store._find_document("project-a", document_id) is not None
    assert store._purge_scrub_pending_exists(project_id="project-a", document_id=document_id)
    assert get_evidence(store=store, project_id="project-a", query=ERASED_TERM).chunk_count > 0
    assert store.purge_document("project-a", document_id, confirm_purge=True).success
    assert not store._purge_scrub_pending_exists(project_id="project-a", document_id=document_id)
    assert document_id.encode() not in _sqlite_storage_bytes(store.db_path)
    _assert_retained_state(store, retained_id, source_files)
    store.close()


class FailCommitConnection:
    def __init__(self, connection, *, only_clear=False):
        self.connection = connection
        self.only_clear = only_clear
        self.clearing = False

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None and (not self.only_clear or self.clearing):
            self.connection.rollback()
            raise sqlite3.OperationalError("injected atomic failure at commit")
        return self.connection.__exit__(exc_type, exc_value, traceback)

    def execute(self, sql, *args):
        result = self.connection.execute(sql, *args)
        if "delete from purge_scrub_pending" in " ".join(sql.lower().split()):
            self.clearing = True
        return result


def _terminate_at_boundary(db_path: Path, document_id: str, stage: str) -> None:
    source_root = Path(database.__file__).resolve().parents[2]
    proc = subprocess.Popen(
        [sys.executable, "-c", PURGE_CHILD, str(db_path), document_id, stage],
        cwd=source_root,
        env={**os.environ, "PYTHONPATH": str(source_root)},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    ready: queue.Queue[bytes] = queue.Queue()
    reader = threading.Thread(target=lambda: ready.put(proc.stdout.readline()), daemon=True)
    reader.start()
    try:
        line = ready.get(timeout=20)
        if line.rstrip(b"\r\n") != f"PURGE_BOUNDARY:{stage}".encode():
            _, stderr = proc.communicate(timeout=10)
            pytest.fail(f"purge child did not reach boundary: {line!r}, {stderr!r}")
        proc.kill()
        proc.wait(timeout=10)
        assert proc.returncode != 0
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.communicate(timeout=10)
        reader.join(timeout=10)


def _prepare_store(tmp_path: Path):
    erased = _write_catalog_csv(
        tmp_path / "erased.csv",
        [_catalog_row("Erased", "erase_id", "string", f"Primary key. {ERASED_TERM}")],
    )
    retained = _write_catalog_csv(
        tmp_path / "retained.csv",
        [_catalog_row("Retained", "retained_id", "string", f"Primary key. {RETAINED_TERM}")],
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest = _ingest(store, tmp_path, erased)
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-b",
        file_path=str(retained),
        doc_type="csv",
    )
    erased_suggestion = suggest_fields(store=store, project_id="project-a").suggestions[0]
    retained_suggestion = suggest_fields(store=store, project_id="project-b").suggestions[0]
    identity = suggest_manifest_candidates(
        store=store, project_id="project-a", scope="identity_role"
    ).suggestions[0]
    for project, suggestions in (
        ("project-a", [erased_suggestion, identity]),
        ("project-b", [retained_suggestion]),
    ):
        submit_suggestion_decisions(
            store=store,
            project_id=project,
            decisions=[
                SuggestionDecision(suggestion_id=item.suggestion_id, status="accepted")
                for item in suggestions
            ],
        )
    assert (
        store.conn.execute("SELECT COUNT(*) FROM manifest_suggestion_review_state").fetchone()[0]
        > 0
    )
    return (
        store,
        ingest.document_id,
        retained_suggestion.suggestion_id,
        {path: path.read_bytes() for path in (erased, retained)},
    )


def _logical_snapshot(store):
    return {
        table: [tuple(row) for row in store.conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
        for table in (
            "documents",
            "document_chunks",
            "field_catalog",
            "manifest_suggestions",
            "manifest_suggestion_review_state",
            "purge_scrub_pending",
        )
    }


def _assert_retained_state(store, retained_id, source_files):
    assert get_evidence(store=store, project_id="project-b", query=RETAINED_TERM).chunk_count > 0
    assert _manifest_suggestion_row(store, retained_id)["status"] == "accepted"
    assert get_suggestion_evidence_chain(
        store=store, project_id="project-b", suggestion_id=retained_id
    ).success
    assert all(path.read_bytes() == content for path, content in source_files.items())
    assert store.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    with store.conn:
        store.conn.execute("INSERT INTO document_chunks(document_chunks) VALUES('integrity-check')")
    config = dict(store.conn.execute("SELECT k, v FROM document_chunks_config"))
    assert config["version"] == 4
    assert "secure-delete" not in config
