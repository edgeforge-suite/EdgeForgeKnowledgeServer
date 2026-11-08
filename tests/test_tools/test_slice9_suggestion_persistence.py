from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from knowledge_server.models import SuggestionDecision
from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.decisions import submit_suggestion_decisions
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.suggest import suggest_fields, suggest_manifest_candidates


def test_suggest_fields_persists_stable_ids_and_evidence_snapshot(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    fixture = _write_dictionary_csv(
        tmp_path / "account.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "Primary account identifier",
            }
        ],
    )

    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="csv",
    )

    first = suggest_fields(store=store, project_id="project-a", field_name_pattern="account_id")
    second = suggest_fields(store=store, project_id="project-a", field_name_pattern="account_id")

    assert first.suggestions
    assert second.suggestions
    assert first.suggestions[0].suggestion_id == second.suggestions[0].suggestion_id
    assert first.suggestions[0].status == "pending"
    row = store.conn.execute(
        """
        SELECT suggestion_payload, status
        FROM manifest_suggestions
        WHERE project_id = ? AND suggestion_id = ?
        """,
        ("project-a", first.suggestions[0].suggestion_id),
    ).fetchone()
    assert row is not None
    payload = json.loads(row["suggestion_payload"])
    assert row["status"] == "pending"
    assert payload["field_name"] == "account_id"
    assert payload["evidence"][0]["document_id"] == first.suggestions[0].evidence[0].document_id
    assert payload["evidence"][0]["source_location"]


def test_suggest_manifest_candidates_fields_scope_preserves_field_behavior(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    fixture = _write_dictionary_csv(
        tmp_path / "account.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "Primary account identifier",
            }
        ],
    )

    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="csv",
    )

    first = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="fields",
        entity="Account",
        field_name_pattern="account_id",
    )
    second = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="fields",
        entity="Account",
        field_name_pattern="account_id",
    )

    assert first.tool_name == "suggest_manifest_candidates"
    assert first.scope == "fields"
    assert first.suggestion_count == 1
    assert first.source_document_count == 1
    assert first.suggestions[0].field_name == "account_id"
    assert first.suggestions[0].entity == "Account"
    assert first.suggestions[0].suggestion_id == second.suggestions[0].suggestion_id
    row = store.conn.execute(
        """
        SELECT suggestion_type, status
        FROM manifest_suggestions
        WHERE suggestion_id = ?
        """,
        (first.suggestions[0].suggestion_id,),
    ).fetchone()
    assert row is not None
    assert row["suggestion_type"] == "field"
    assert row["status"] == "pending"


def test_suggest_manifest_candidates_preserves_status_after_decision(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    fixture = _write_dictionary_csv(
        tmp_path / "account.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "Primary account identifier",
            }
        ],
    )

    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="csv",
    )
    initial = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="fields",
        field_name_pattern="account_id",
    )
    suggestion_id = initial.suggestions[0].suggestion_id
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion_id, status="accepted")],
    )

    refreshed = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="fields",
        field_name_pattern="account_id",
    )

    assert refreshed.suggestions[0].suggestion_id == suggestion_id
    assert refreshed.suggestions[0].status == "accepted"


def test_suggest_manifest_candidates_unsupported_scope_returns_warning_without_persisting(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="not_a_scope",
        entity="Account",
    )

    assert result.success is False
    assert result.scope == "not_a_scope"
    assert result.unsupported_scope is True
    assert result.suggestions == []
    assert "Unsupported suggestion scope" in result.warnings[0]
    row = store.conn.execute(
        "SELECT COUNT(*) AS row_count FROM manifest_suggestions"
    ).fetchone()
    assert row["row_count"] == 0


def test_suggest_manifest_candidates_persists_portfolio_reuse_rows(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    current = tmp_path / "current.md"
    source = tmp_path / "source.md"
    current.write_text("# Current\n\nLocal project notes.\n", encoding="utf-8")
    source.write_text("# Balance Pattern\n\nPortfolio balance pattern.\n", encoding="utf-8")
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(current),
        doc_type="markdown",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-b",
        file_path=str(source),
        doc_type="markdown",
    )

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="portfolio_reuse",
        field_name_pattern="balance",
    )

    assert result.suggestion_count == 1
    suggestion = result.suggestions[0]
    row = store.conn.execute(
        """
        SELECT project_id, suggestion_type, field_name, suggestion_payload
        FROM manifest_suggestions
        WHERE suggestion_id = ?
        """,
        (suggestion.suggestion_id,),
    ).fetchone()
    assert row is not None
    assert row["project_id"] == "project-a"
    assert row["suggestion_type"] == "portfolio_reuse"
    assert row["field_name"]
    payload = json.loads(row["suggestion_payload"])
    assert payload["payload"]["matched_project_id"] == "project-b"


def test_suggest_manifest_candidates_persists_transform_rows(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    source_fixture = _write_dictionary_csv(
        tmp_path / "source.csv",
        [
            {
                "entity": "RORequest",
                "field_name": "paymentId",
                "type": "string",
                "length": "",
                "nullable": "true",
                "description": "Payment identifier from upstream request",
            }
        ],
    )
    target_fixture = _write_dictionary_csv(
        tmp_path / "target.csv",
        [
            {
                "entity": "D1Request",
                "field_name": "payment_id",
                "type": "string",
                "length": "",
                "nullable": "true",
                "description": "Payment identifier for router target",
            }
        ],
    )
    for fixture in [source_fixture, target_fixture]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(fixture),
            doc_type="csv",
        )

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="transforms",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
        target_id="ledger-core",
        direction="request",
    )

    assert result.suggestion_count == 1
    suggestion = result.suggestions[0]
    row = store.conn.execute(
        """
        SELECT project_id, suggestion_type, entity_name, field_name, suggestion_payload
        FROM manifest_suggestions
        WHERE suggestion_id = ?
        """,
        (suggestion.suggestion_id,),
    ).fetchone()
    assert row is not None
    assert row["project_id"] == "project-a"
    assert row["suggestion_type"] == "transform"
    assert row["entity_name"] == "D1Request"
    assert row["field_name"] == "payment_id"
    payload = json.loads(row["suggestion_payload"])
    assert payload["payload"]["source"] == "$.paymentId"
    assert payload["payload"]["target"] == "$.payment_id"
    assert payload["payload"]["manifest_path"] == (
        "async_routes.payment_router.router_config.targets.ledger-core.request_transform"
    )


def test_submit_suggestion_decisions_persists_status_and_edited_payload(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    fixture = _write_dictionary_csv(
        tmp_path / "account.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "Primary account identifier",
            }
        ],
    )

    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="csv",
    )
    initial = suggest_fields(store=store, project_id="project-a", field_name_pattern="account_id")
    suggestion = initial.suggestions[0]

    decision_result = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={
                    "manifest_path": "entities.Account.fields.account_id",
                    "field_name": "account_id",
                },
            )
        ],
    )

    assert decision_result.success is True
    assert decision_result.outcome_count == 1
    assert decision_result.outcomes[0].success is True
    refreshed = suggest_fields(store=store, project_id="project-a", field_name_pattern="account_id")
    assert refreshed.suggestions[0].suggestion_id == suggestion.suggestion_id
    assert refreshed.suggestions[0].status == "edited"

    row = store.conn.execute(
        """
        SELECT status, edited_payload, suggestion_payload, reviewed_at
        FROM manifest_suggestions
        WHERE project_id = ? AND suggestion_id = ?
        """,
        ("project-a", suggestion.suggestion_id),
    ).fetchone()
    assert row is not None
    assert row["status"] == "edited"
    assert json.loads(row["edited_payload"]) == {
        "manifest_path": "entities.Account.fields.account_id",
        "field_name": "account_id",
    }
    assert json.loads(row["suggestion_payload"])["status"] == "edited"
    assert row["reviewed_at"] is not None


def test_submit_suggestion_decisions_returns_per_item_failure_for_unknown_ids(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id="missing-suggestion",
                status="rejected",
            )
        ],
    )

    assert result.success is False
    assert result.outcome_count == 1
    assert result.outcomes[0].success is False
    assert "Suggestion not found" in (result.outcomes[0].error or "")


def test_fresh_database_creates_manifest_suggestions_table_only(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    assert _table_exists(store.conn, "manifest_suggestions")
    assert not _table_exists(store.conn, "field_suggestions")


def test_legacy_field_suggestions_table_migrates_with_decisions_preserved(tmp_path: Path) -> None:
    db_path = tmp_path / "ks.sqlite3"
    _create_legacy_field_suggestions_db(db_path)

    store = KnowledgeStore(db_path)

    assert _table_exists(store.conn, "manifest_suggestions")
    assert not _table_exists(store.conn, "field_suggestions")
    row = store.conn.execute(
        """
        SELECT suggestion_id,
               project_id,
               suggestion_type,
               entity_name,
               field_name,
               status,
               edited_payload,
               suggestion_payload,
               created_at,
               updated_at,
               reviewed_at
        FROM manifest_suggestions
        WHERE suggestion_id = 'legacy-suggestion'
        """
    ).fetchone()
    assert row is not None
    assert row["project_id"] == "project-a"
    assert row["suggestion_type"] == "field"
    assert row["entity_name"] == "Account"
    assert row["field_name"] == "account_id"
    assert row["status"] == "edited"
    assert json.loads(row["edited_payload"]) == {
        "manifest_path": "entities.Account.fields.account_id"
    }
    assert json.loads(row["suggestion_payload"])["status"] == "edited"
    assert row["created_at"] == "2026-04-01T00:00:00+00:00"
    assert row["updated_at"] == "2026-04-01T00:01:00+00:00"
    assert row["reviewed_at"] == "2026-04-01T00:02:00+00:00"


def test_suggestion_table_migration_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "ks.sqlite3"
    _create_legacy_field_suggestions_db(db_path)

    first = KnowledgeStore(db_path)
    first.close()
    second = KnowledgeStore(db_path)

    row_count = second.conn.execute(
        "SELECT COUNT(*) AS row_count FROM manifest_suggestions"
    ).fetchone()
    assert row_count["row_count"] == 1
    assert not _table_exists(second.conn, "field_suggestions")


def test_manifest_suggestions_indexes_are_created(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    indexes = {
        row["name"]
        for row in store.conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'index' AND tbl_name = 'manifest_suggestions'
            """
        ).fetchall()
    }
    assert "idx_manifest_suggestions_project" in indexes
    assert "idx_manifest_suggestions_type" in indexes
    assert "idx_manifest_suggestions_scope" in indexes
    assert "idx_field_suggestions_project" not in indexes


def test_empty_legacy_table_is_dropped_when_manifest_suggestions_exists(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "ks.sqlite3"
    with sqlite3.connect(db_path) as conn:
        _create_legacy_suggestion_table(conn, table_name="field_suggestions")
        _create_legacy_suggestion_table(conn, table_name="manifest_suggestions")
        conn.execute(
            """
            INSERT INTO manifest_suggestions (
                suggestion_id,
                project_id,
                suggestion_type,
                entity_name,
                field_name,
                status,
                edited_payload,
                suggestion_payload,
                created_at,
                updated_at,
                reviewed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _legacy_row("current-suggestion", status="accepted"),
        )

    store = KnowledgeStore(db_path)

    assert _table_exists(store.conn, "manifest_suggestions")
    assert not _table_exists(store.conn, "field_suggestions")
    row_count = store.conn.execute(
        "SELECT COUNT(*) AS row_count FROM manifest_suggestions"
    ).fetchone()
    assert row_count["row_count"] == 1


def test_dual_suggestion_tables_with_data_raise_migration_error(tmp_path: Path) -> None:
    db_path = tmp_path / "ks.sqlite3"
    with sqlite3.connect(db_path) as conn:
        _create_legacy_suggestion_table(conn, table_name="field_suggestions")
        _create_legacy_suggestion_table(conn, table_name="manifest_suggestions")
        for table_name, suggestion_id in [
            ("field_suggestions", "legacy-suggestion"),
            ("manifest_suggestions", "current-suggestion"),
        ]:
            conn.execute(
                f"""
                INSERT INTO {table_name} (
                    suggestion_id,
                    project_id,
                    suggestion_type,
                    entity_name,
                    field_name,
                    status,
                    edited_payload,
                    suggestion_payload,
                    created_at,
                    updated_at,
                    reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _legacy_row(suggestion_id),
            )

    with pytest.raises(RuntimeError, match="both field_suggestions and manifest_suggestions"):
        KnowledgeStore(db_path)


def _write_dictionary_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["entity", "field_name", "type", "length", "nullable", "description"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _create_legacy_field_suggestions_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        _create_legacy_suggestion_table(conn, table_name="field_suggestions")
        conn.execute(
            """
            CREATE INDEX idx_field_suggestions_project
            ON field_suggestions(project_id)
            """
        )
        conn.execute(
            """
            INSERT INTO field_suggestions (
                suggestion_id,
                project_id,
                suggestion_type,
                entity_name,
                field_name,
                status,
                edited_payload,
                suggestion_payload,
                created_at,
                updated_at,
                reviewed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _legacy_row("legacy-suggestion", status="edited"),
        )


def _create_legacy_suggestion_table(conn: sqlite3.Connection, *, table_name: str) -> None:
    conn.execute(
        f"""
        CREATE TABLE {table_name} (
            suggestion_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            suggestion_type TEXT NOT NULL,
            entity_name TEXT,
            field_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'edited', 'rejected')),
            edited_payload TEXT,
            suggestion_payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            reviewed_at TEXT
        )
        """
    )


def _legacy_row(suggestion_id: str, *, status: str = "pending") -> tuple[object, ...]:
    edited_payload = (
        json.dumps({"manifest_path": "entities.Account.fields.account_id"})
        if status == "edited"
        else None
    )
    suggestion_payload = json.dumps(
        {
            "suggestion_id": suggestion_id,
            "status": status,
            "field_name": "account_id",
            "entity": "Account",
            "evidence": [{"document_id": "doc-1", "source_location": "row 2"}],
        }
    )
    return (
        suggestion_id,
        "project-a",
        "field",
        "Account",
        "account_id",
        status,
        edited_payload,
        suggestion_payload,
        "2026-04-01T00:00:00+00:00",
        "2026-04-01T00:01:00+00:00",
        "2026-04-01T00:02:00+00:00",
    )
