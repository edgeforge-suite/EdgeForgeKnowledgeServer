from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from knowledge_server.models import SuggestionDecision
from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.decisions import submit_suggestion_decisions
from knowledge_server.tools.delete import delete_document, purge_document
from knowledge_server.tools.evidence import get_evidence
from knowledge_server.tools.evidence_chain import get_suggestion_evidence_chain
from knowledge_server.tools.field_catalog import read_field_catalog
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.read import read_document
from knowledge_server.tools.search import list_documents, search_documents
from knowledge_server.tools.suggest import suggest_fields, suggest_manifest_candidates


def test_purge_active_document_removes_content_and_dependent_suggestions(
    tmp_path: Path,
) -> None:
    account = _write_catalog_csv(
        tmp_path / "account.csv",
        [_catalog_row("Account", "account_id", "string", "Primary account identifier.")],
    )
    loan = _write_catalog_csv(
        tmp_path / "loan.csv",
        [_catalog_row("Loan", "loan_id", "string", "Primary loan identifier.")],
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    account_ingest = _ingest(store, tmp_path, account)
    _ingest(store, tmp_path, loan)
    account_suggestion = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="account_id",
    ).suggestions[0]
    loan_suggestion = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="loan_id",
    ).suggestions[0]
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(suggestion_id=account_suggestion.suggestion_id, status="accepted"),
            SuggestionDecision(suggestion_id=loan_suggestion.suggestion_id, status="accepted"),
        ],
    )

    result = purge_document(
        store=store,
        project_id="project-a",
        document_id=account_ingest.document_id,
        confirm_purge=True,
    )
    stale_decision = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(suggestion_id=account_suggestion.suggestion_id, status="rejected")
        ],
    )
    stale_chain = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=account_suggestion.suggestion_id,
        scope="fields",
    )

    assert result.success is True
    assert result.tool_name == "purge_document"
    assert result.document_name == "account.csv"
    assert _row_count(store, "documents", account_ingest.document_id) == 0
    assert _row_count(store, "document_chunks", account_ingest.document_id) == 0
    assert _row_count(store, "field_catalog", account_ingest.document_id) == 0
    assert _manifest_suggestion_row(store, account_suggestion.suggestion_id) is None
    assert stale_decision.success is False
    assert "Suggestion not found" in stale_decision.outcomes[0].error
    assert stale_chain.success is False
    assert "suggestion not found" in stale_chain.warnings[0]
    assert [
        document.name for document in list_documents(store=store, project_id="project-a").documents
    ] == ["loan.csv"]
    assert search_documents(store=store, project_id="project-a", query="account").result_count == 0
    assert get_evidence(store=store, project_id="project-a", query="account").chunk_count == 0
    assert (
        read_document(
            store=store,
            project_id="project-a",
            document_id=account_ingest.document_id,
        ).success
        is False
    )
    assert read_field_catalog(store=store, project_id="project-a", entity="Account").fields == []
    assert (
        suggest_fields(
            store=store,
            project_id="project-a",
            field_name_pattern="account_id",
        ).suggestions
        == []
    )
    refreshed_loan = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="loan_id",
    ).suggestions[0]
    assert refreshed_loan.suggestion_id == loan_suggestion.suggestion_id
    assert refreshed_loan.status == "accepted"


def test_purge_scrubs_document_bytes_from_sqlite_storage(tmp_path: Path) -> None:
    sentinel = "PURGE_SENTINEL_7fc0b8056d9d4b36aab4"
    source = _write_catalog_csv(
        tmp_path / "account.csv",
        [_catalog_row("Account", "account_id", "string", sentinel)],
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest = _ingest(store, tmp_path, source)
    store.conn.execute("PRAGMA wal_checkpoint(FULL)")
    sentinel_bytes = sentinel.encode("utf-8")

    assert sentinel_bytes in _sqlite_storage_bytes(store.db_path)

    result = purge_document(
        store=store,
        project_id="project-a",
        document_id=ingest.document_id,
        confirm_purge=True,
    )

    assert result.success is True
    assert get_evidence(store=store, project_id="project-a", query=sentinel).chunk_count == 0
    assert sentinel_bytes not in _sqlite_storage_bytes(store.db_path)


@pytest.mark.parametrize("soft_deleted", [False, True])
def test_purge_removes_indexed_terms_from_multiple_segments(
    tmp_path: Path,
    soft_deleted: bool,
) -> None:
    term = "qzxjkvwplmfrb"
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    store.conn.execute("INSERT INTO document_chunks(document_chunks, rank) VALUES('automerge', 0)")
    source = _write_catalog_csv(
        tmp_path / "erase.csv",
        [_catalog_row("Example", "erase_id", "string", term)],
    )
    ingest = _ingest(store, tmp_path, source)
    for index in range(3):
        retained = _write_catalog_csv(
            tmp_path / f"retained{index}.csv",
            [_catalog_row("Retained", f"retained_{index}", "string", "retained evidence")],
        )
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-b",
            file_path=str(retained),
            doc_type="csv",
        )
    suggestion = suggest_fields(store=store, project_id="project-b").suggestions[0]
    submit_suggestion_decisions(
        store=store,
        project_id="project-b",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="accepted")],
    )
    reuse = suggest_manifest_candidates(
        store=store, project_id="project-b", scope="portfolio_reuse", field_name_pattern=term
    ).suggestions[0]
    assert ingest.document_id in reuse.source_document_ids
    assert (
        store.conn.execute("SELECT COUNT(DISTINCT segid) FROM document_chunks_idx").fetchone()[0]
        > 1
    )
    assert term.encode() in _fts_shadow_bytes(store)
    assert term.encode() in _sqlite_storage_bytes(store.db_path)
    if soft_deleted:
        assert store.delete_document("project-a", ingest.document_id).success

    result = store.purge_document("project-a", ingest.document_id, confirm_purge=True)

    assert result.success, result.warnings
    assert term.encode() not in _fts_shadow_bytes(store)
    assert term.encode() not in _sqlite_storage_bytes(store.db_path)
    assert term in source.read_text(encoding="utf-8")
    assert _manifest_suggestion_row(store, reuse.suggestion_id) is None
    assert not get_suggestion_evidence_chain(
        store=store, project_id="project-b", suggestion_id=reuse.suggestion_id,
        scope="portfolio_reuse",
    ).success
    store.close()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    assert store.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    store.conn.execute("INSERT INTO document_chunks(document_chunks) VALUES('integrity-check')")
    store.conn.commit()
    assert get_evidence(store=store, project_id="project-b", query="retained").chunk_count > 0
    assert _manifest_suggestion_row(store, suggestion.suggestion_id)["status"] == "accepted"
    assert get_suggestion_evidence_chain(
        store=store, project_id="project-b", suggestion_id=suggestion.suggestion_id
    ).success
    assert (
        store.conn.execute("SELECT v FROM document_chunks_config WHERE k='version'").fetchone()[0]
        == 4
    )
    store.close()


@pytest.mark.parametrize("soft_deleted", [False, True])
def test_purge_removes_prefix_compressed_term_suffix(
    tmp_path: Path, soft_deleted: bool,
) -> None:
    retained_term = "qxzsharedprefixaaaa"
    erased_term = "qxzsharedprefixzzzzuniquetailjkvw"
    suffix = b"zzzzuniquetailjkvw"
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    retained = _write_catalog_csv(
        tmp_path / "retained.csv",
        [_catalog_row("Retained", "retained_id", "string", retained_term)],
    )
    erased = _write_catalog_csv(
        tmp_path / "erased.csv",
        [_catalog_row("Erased", "erased_id", "string", erased_term)],
    )
    _ingest(store, tmp_path, retained)
    ingest = _ingest(store, tmp_path, erased)
    with store.conn:
        store.conn.execute("INSERT INTO document_chunks(document_chunks) VALUES('optimize')")
    index_bytes = b"".join(
        row[0] for row in store.conn.execute("SELECT block FROM document_chunks_data")
    )
    # Prove the full-term byte check is blind to this indexed, prefix-compressed term.
    assert erased_term.encode() not in index_bytes
    assert suffix in index_bytes
    assert get_evidence(store=store, project_id="project-a", query=erased_term).chunk_count > 0
    assert suffix in _sqlite_storage_bytes(store.db_path)
    if soft_deleted:
        assert store.delete_document("project-a", ingest.document_id).success

    result = store.purge_document("project-a", ingest.document_id, confirm_purge=True)

    assert result.success, result.warnings
    assert suffix not in _fts_shadow_bytes(store)
    assert suffix not in _sqlite_storage_bytes(store.db_path)
    assert erased_term in erased.read_text(encoding="utf-8")
    store.close()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    assert get_evidence(store=store, project_id="project-a", query=erased_term).chunk_count == 0
    assert get_evidence(store=store, project_id="project-a", query=retained_term).chunk_count > 0
    assert store.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    store.close()


def test_purge_reports_incomplete_scrub_when_reader_blocks_wal_truncate(
    tmp_path: Path,
) -> None:
    sentinel = "qxzreaderblockedjkvw"
    source = _write_catalog_csv(
        tmp_path / "account.csv",
        [_catalog_row("Account", "account_id", "string", sentinel)],
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest = _ingest(store, tmp_path, source)
    previous_timeout = store.conn.execute("PRAGMA busy_timeout").fetchone()[0]
    reader = sqlite3.connect(store.db_path)
    reader.row_factory = sqlite3.Row
    reader.execute("BEGIN")
    reader_row = reader.execute(
        "SELECT content FROM document_chunks WHERE document_id = ?",
        (ingest.document_id,),
    ).fetchone()

    assert reader_row is not None
    assert sentinel in reader_row["content"]

    try:
        result = purge_document(
            store=store,
            project_id="project-a",
            document_id=ingest.document_id,
            confirm_purge=True,
        )

        assert result.success is False
        assert "SQLite storage scrub could not complete" in result.warnings[0]
        assert "blocked by another connection" in result.warnings[0]
        assert get_evidence(store=store, project_id="project-a", query=sentinel).chunk_count == 0
        assert sentinel.encode("utf-8") in _sqlite_storage_bytes(store.db_path)
        assert store.conn.execute("PRAGMA busy_timeout").fetchone()[0] == previous_timeout
    finally:
        reader.rollback()
        reader.close()

    store.close()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    assert store._purge_scrub_pending_exists(project_id="project-a", document_id=ingest.document_id)
    retry = purge_document(
        store=store,
        project_id="project-a",
        document_id=ingest.document_id,
        confirm_purge=True,
    )

    assert retry.success is True
    assert retry.warnings == []
    assert sentinel.encode("utf-8") not in _sqlite_storage_bytes(store.db_path)
    assert sentinel.encode() not in _fts_shadow_bytes(store)
    assert not store._purge_scrub_pending_exists(
        project_id="project-a", document_id=ingest.document_id
    )
    store.close()


@pytest.mark.parametrize("stage", ["compact", "checkpoint", "vacuum"])
def test_purge_maintenance_failure_is_retryable_after_reopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    term = "qzxmaintenancejkvw"
    source = _write_catalog_csv(
        tmp_path / "erase.csv",
        [_catalog_row("Example", "erase_id", "string", term)],
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest = _ingest(store, tmp_path, source)
    previous_timeout = store.conn.execute("PRAGMA busy_timeout").fetchone()[0]

    def fail():
        # Also prove an interrupted write transaction is rolled back before pending state is saved.
        store.conn.execute("INSERT INTO document_chunks(document_chunks) VALUES('optimize')")
        raise sqlite3.DatabaseError("injected maintenance failure")

    class FailingVacuumConnection:
        def __init__(self, connection):
            self.connection = connection

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def __enter__(self):
            return self.connection.__enter__()

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def execute(self, sql, *args):
            if sql == "VACUUM":
                raise sqlite3.OperationalError("injected maintenance failure")
            return self.connection.execute(sql, *args)

    with monkeypatch.context() as patch:
        if stage == "vacuum":
            patch.setattr(store, "conn", FailingVacuumConnection(store.conn))
        else:
            helper = (
                "_compact_fts_index_after_purge"
                if stage == "compact"
                else "_wal_checkpoint_truncate"
            )
            patch.setattr(store, helper, fail)
        result = store.purge_document("project-a", ingest.document_id, confirm_purge=True)
        assert not result.success
        assert "injected maintenance failure" in result.warnings[0]
        assert "retry purge_document" in result.warnings[0]
        assert store.conn.execute("PRAGMA busy_timeout").fetchone()[0] == previous_timeout
        assert not store.conn.in_transaction
    store.close()

    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    assert store._purge_scrub_pending_exists(project_id="project-a", document_id=ingest.document_id)
    assert not store.purge_document("other-project", ingest.document_id, confirm_purge=True).success
    assert store.purge_document("project-a", ingest.document_id, confirm_purge=True).success
    assert term.encode() not in _fts_shadow_bytes(store)
    assert term.encode() not in _sqlite_storage_bytes(store.db_path)
    assert store.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    store.close()


def test_later_purge_cleans_residue_from_previous_successful_purge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    term = "qxzoldpurgeresiduejkvw"
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    first = _write_catalog_csv(
        tmp_path / "first.csv",
        [_catalog_row("Example", "first_id", "string", term)],
    )
    second = _write_catalog_csv(
        tmp_path / "second.csv",
        [_catalog_row("Example", "second_id", "string", "second")],
    )
    first_ingest, second_ingest = _ingest(store, tmp_path, first), _ingest(store, tmp_path, second)
    with monkeypatch.context() as patch:
        # Reproduce the previous implementation: storage scrub without FTS compaction.
        patch.setattr(store, "_compact_fts_index_after_purge", lambda: None)
        assert store.purge_document(
            "project-a", first_ingest.document_id, confirm_purge=True
        ).success
    assert term.encode() in _fts_shadow_bytes(store)
    store.close()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    assert not store.purge_document(
        "project-a", first_ingest.document_id, confirm_purge=True
    ).success
    assert store.purge_document("project-a", second_ingest.document_id, confirm_purge=True).success
    assert term.encode() not in _fts_shadow_bytes(store)
    assert term.encode() not in _sqlite_storage_bytes(store.db_path)
    store.close()


def test_purge_requires_explicit_confirmation(tmp_path: Path) -> None:
    source = _write_catalog_csv(
        tmp_path / "account.csv",
        [_catalog_row("Account", "account_id", "string", "Primary account identifier.")],
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest = _ingest(store, tmp_path, source)

    result = purge_document(
        store=store,
        project_id="project-a",
        document_id=ingest.document_id,
    )

    assert result.success is False
    assert "confirm_purge=True is required" in result.warnings[0]
    assert _row_count(store, "documents", ingest.document_id) == 1
    assert _row_count(store, "document_chunks", ingest.document_id) > 0
    assert _row_count(store, "field_catalog", ingest.document_id) > 0


def test_purge_unknown_document_returns_clear_warning(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = purge_document(
        store=store,
        project_id="project-a",
        document_id="missing-doc",
        confirm_purge=True,
    )

    assert result.success is False
    assert result.warnings == ["document not found for purge: missing-doc"]


def test_purge_soft_deleted_document_removes_retained_chunks_and_metadata(
    tmp_path: Path,
) -> None:
    source = _write_catalog_csv(
        tmp_path / "account.csv",
        [_catalog_row("Account", "account_id", "string", "Primary account identifier.")],
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest = _ingest(store, tmp_path, source)
    delete_result = delete_document(
        store=store,
        project_id="project-a",
        document_id=ingest.document_id,
    )

    assert delete_result.success is True
    assert _row_count(store, "document_chunks", ingest.document_id) > 0

    purge_result = purge_document(
        store=store,
        project_id="project-a",
        document_id=ingest.document_id,
        confirm_purge=True,
    )

    assert purge_result.success is True
    assert _row_count(store, "documents", ingest.document_id) == 0
    assert _row_count(store, "document_chunks", ingest.document_id) == 0
    assert _row_count(store, "field_catalog", ingest.document_id) == 0


def test_reingest_after_purge_creates_fresh_pending_suggestions(tmp_path: Path) -> None:
    source = _write_catalog_csv(
        tmp_path / "account.csv",
        [_catalog_row("Account", "account_id", "string", "Primary account identifier.")],
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest = _ingest(store, tmp_path, source)
    suggestion = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="account_id",
    ).suggestions[0]
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="accepted")],
    )
    purge_document(
        store=store,
        project_id="project-a",
        document_id=ingest.document_id,
        confirm_purge=True,
    )

    _ingest(store, tmp_path, source)
    refreshed = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="account_id",
    ).suggestions[0]

    assert refreshed.suggestion_id == suggestion.suggestion_id
    assert refreshed.status == "pending"


def test_purge_clears_orphaned_identity_review_state(tmp_path: Path) -> None:
    ddl = tmp_path / "identity.sql"
    ddl.write_text(
        """
        CREATE TABLE ACCOUNT (
            account_id VARCHAR2(36) PRIMARY KEY
        );
        """,
        encoding="utf-8",
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(ddl),
        doc_type="sql",
    )
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="ACCOUNT",
    ).suggestions[0]
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="accepted")],
    )

    ddl.write_text(
        """
        -- changed source evidence
        CREATE TABLE ACCOUNT (
            account_id VARCHAR2(36) PRIMARY KEY
        );
        """,
        encoding="utf-8",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(ddl),
        doc_type="sql",
    )
    assert _manifest_suggestion_row(store, suggestion.suggestion_id) is None

    purge_document(
        store=store,
        project_id="project-a",
        document_id=ingest.document_id,
        confirm_purge=True,
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(ddl),
        doc_type="sql",
    )
    refreshed = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="ACCOUNT",
    ).suggestions[0]

    assert refreshed.suggestion_id == suggestion.suggestion_id
    assert refreshed.status == "pending"


def _ingest(store: KnowledgeStore, tmp_path: Path, source: Path):
    return ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(source),
        doc_type="csv",
    )


def _write_catalog_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["entity", "field_name", "type", "nullable", "description"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def _catalog_row(
    entity: str,
    field_name: str,
    field_type: str,
    description: str,
) -> dict[str, str]:
    return {
        "entity": entity,
        "field_name": field_name,
        "type": field_type,
        "nullable": "false",
        "description": description,
    }


def _row_count(store: KnowledgeStore, table: str, document_id: str) -> int:
    column = "id" if table == "documents" else "document_id"
    row = store.conn.execute(
        f"SELECT COUNT(*) AS row_count FROM {table} WHERE {column} = ?",
        (document_id,),
    ).fetchone()
    return int(row["row_count"])


def _manifest_suggestion_row(store: KnowledgeStore, suggestion_id: str):
    return store.conn.execute(
        "SELECT status FROM manifest_suggestions WHERE suggestion_id = ?",
        (suggestion_id,),
    ).fetchone()


def _sqlite_storage_bytes(db_path: Path) -> bytes:
    data = b""
    for suffix in ["", "-wal", "-shm"]:
        path = Path(f"{db_path}{suffix}")
        if path.exists():
            data += path.read_bytes()
    return data


def _fts_shadow_bytes(store: KnowledgeStore) -> bytes:
    data = bytearray()
    for table in ("data", "idx", "content", "docsize", "config"):
        for row in store.conn.execute(f"SELECT * FROM document_chunks_{table}"):
            for value in row:
                if isinstance(value, bytes):
                    data.extend(value)
                elif isinstance(value, str):
                    data.extend(value.encode("utf-8"))
    return bytes(data)
