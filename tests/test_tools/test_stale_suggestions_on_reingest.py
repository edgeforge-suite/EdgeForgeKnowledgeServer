from __future__ import annotations

import csv
import json
from pathlib import Path

from knowledge_server.models import SuggestionDecision
from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.decisions import submit_suggestion_decisions
from knowledge_server.tools.evidence_chain import get_suggestion_evidence_chain
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.suggest import suggest_fields, suggest_manifest_candidates


def test_changed_reingest_invalidates_accepted_field_suggestion_then_regenerates_pending(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    fixture = tmp_path / "account.csv"
    _write_catalog(
        fixture,
        [
            _row(
                "Account",
                "account_id",
                "string",
                "Primary account identifier from v1.",
            )
        ],
    )
    _ingest(store, tmp_path, fixture)
    first = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="account_id",
    )
    suggestion_id = first.suggestions[0].suggestion_id
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion_id, status="accepted")],
    )

    _write_catalog(
        fixture,
        [
            _row(
                "Account",
                "account_id",
                "string",
                "Primary account identifier from v2.",
            )
        ],
    )
    _ingest(store, tmp_path, fixture)

    stale_chain = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=suggestion_id,
        scope="fields",
    )
    regenerated = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="account_id",
    )

    assert stale_chain.success is False
    assert "suggestion not found" in stale_chain.warnings[0]
    assert regenerated.suggestions[0].suggestion_id == suggestion_id
    assert regenerated.suggestions[0].status == "pending"
    assert regenerated.suggestions[0].suggested_description == "Primary account identifier from v2."


def test_changed_reingest_refreshes_manifest_suggestion_citation_hash(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ddl = tmp_path / "identity.sql"
    ddl.write_text(
        """
        CREATE TABLE ACCOUNT (
            account_id VARCHAR2(36) PRIMARY KEY
        );
        """,
        encoding="utf-8",
    )
    _ingest(store, tmp_path, ddl, doc_type="sql")
    first = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="ACCOUNT",
    )
    suggestion = first.suggestions[0]
    original_hash = suggestion.citations[0].content_hash
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="accepted")],
    )

    ddl.write_text(
        """
        CREATE TABLE ACCOUNT (
            -- changed source evidence
            account_id VARCHAR2(36) PRIMARY KEY
        );
        """,
        encoding="utf-8",
    )
    _ingest(store, tmp_path, ddl, doc_type="sql")

    stale_chain = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=suggestion.suggestion_id,
        scope="identity_role",
    )
    refreshed = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="ACCOUNT",
    ).suggestions[0]

    assert stale_chain.success is False
    assert refreshed.suggestion_id == suggestion.suggestion_id
    assert refreshed.status == "accepted"
    assert refreshed.citations[0].content_hash != original_hash
    assert "changed source evidence" in refreshed.citations[0].snippet


def test_removed_field_reingest_removes_old_field_suggestion(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    fixture = tmp_path / "account.csv"
    _write_catalog(
        fixture,
        [_row("Account", "account_id", "string", "Primary account identifier.")],
    )
    _ingest(store, tmp_path, fixture)
    suggestion = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="account_id",
    ).suggestions[0]

    _write_catalog(
        fixture,
        [_row("Account", "display_name", "string", "Display name.")],
    )
    _ingest(store, tmp_path, fixture)

    assert _suggestion_row(store, suggestion.suggestion_id) is None
    assert not suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="account_id",
    ).suggestions


def test_field_catalog_shape_only_change_invalidates_dependent_validation(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    fixture = tmp_path / "account.csv"
    _write_catalog(
        fixture,
        [
            _row(
                "Account",
                "account_id",
                "string",
                "Primary account identifier.",
                length="12",
            )
        ],
    )
    _ingest(store, tmp_path, fixture)
    first = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="validations",
        field_name_pattern="account_id",
    )
    suggestion = next(
        item
        for item in first.suggestions
        if item.payload["validation_type"] == "max_length"
    )
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="accepted")],
    )

    _write_catalog(
        fixture,
        [
            _row(
                "Account",
                "account_id",
                "string",
                "Primary account identifier.",
                length="16",
            )
        ],
    )
    _ingest(store, tmp_path, fixture)

    assert _suggestion_row(store, suggestion.suggestion_id) is None
    refreshed = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="validations",
        field_name_pattern="account_id",
    )
    max_length = next(
        item
        for item in refreshed.suggestions
        if item.payload["validation_type"] == "max_length"
    )
    assert max_length.status == "pending"
    assert max_length.payload["max_length"] == 16


def test_changed_reingest_preserves_unrelated_suggestion_status(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    account = tmp_path / "account.csv"
    loan = tmp_path / "loan.csv"
    _write_catalog(
        account,
        [_row("Account", "account_id", "string", "Primary account identifier v1.")],
    )
    _write_catalog(
        loan,
        [_row("Loan", "loan_id", "string", "Primary loan identifier.")],
    )
    _ingest(store, tmp_path, account)
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

    _write_catalog(
        account,
        [_row("Account", "account_id", "string", "Primary account identifier v2.")],
    )
    _ingest(store, tmp_path, account)

    assert _suggestion_row(store, account_suggestion.suggestion_id) is None
    loan_row = _suggestion_row(store, loan_suggestion.suggestion_id)
    assert loan_row is not None
    assert loan_row["status"] == "accepted"
    assert suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="loan_id",
    ).suggestions[0].status == "accepted"


def test_identical_reingest_preserves_suggestion_status(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    fixture = tmp_path / "account.csv"
    _write_catalog(
        fixture,
        [_row("Account", "account_id", "string", "Primary account identifier.")],
    )
    _ingest(store, tmp_path, fixture)
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

    _ingest(store, tmp_path, fixture)

    row = _suggestion_row(store, suggestion.suggestion_id)
    assert row is not None
    assert row["status"] == "accepted"
    assert suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="account_id",
    ).suggestions[0].status == "accepted"


def test_identical_multi_field_reingest_preserves_suggestion_status(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    fixture = tmp_path / "account.csv"
    _write_catalog(
        fixture,
        [
            _row("Account", "a", "string", "Field a."),
            _row("Account", "b", "string", "Field b."),
            _row("Account", "z", "string", "Field z."),
        ],
    )
    _ingest(store, tmp_path, fixture)
    suggestion = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="z",
    ).suggestions[0]
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="accepted")],
    )

    _ingest(store, tmp_path, fixture)

    row = _suggestion_row(store, suggestion.suggestion_id)
    assert row is not None
    assert row["status"] == "accepted"
    assert suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="z",
    ).suggestions[0].status == "accepted"


def test_removed_sql_entity_invalidates_dependent_suggestions(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ddl = tmp_path / "schema.sql"
    ddl.write_text(
        """
        CREATE TABLE ACCOUNT (
            account_id VARCHAR2(36) PRIMARY KEY
        );
        CREATE TABLE LOAN (
            loan_id VARCHAR2(36) PRIMARY KEY
        );
        """,
        encoding="utf-8",
    )
    _ingest(store, tmp_path, ddl, doc_type="sql")
    account_suggestion = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="ACCOUNT",
    ).suggestions[0]
    loan_suggestion = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="LOAN",
    ).suggestions[0]
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=loan_suggestion.suggestion_id, status="accepted")],
    )

    ddl.write_text(
        """
        CREATE TABLE ACCOUNT (
            account_id VARCHAR2(36) PRIMARY KEY
        );
        """,
        encoding="utf-8",
    )
    _ingest(store, tmp_path, ddl, doc_type="sql")

    assert _suggestion_row(store, loan_suggestion.suggestion_id) is None
    account_row = _suggestion_row(store, account_suggestion.suggestion_id)
    assert account_row is not None
    assert json.loads(account_row["suggestion_payload"])["status"] == "pending"


def _ingest(
    store: KnowledgeStore,
    tmp_path: Path,
    path: Path,
    *,
    doc_type: str = "csv",
) -> None:
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(path),
        doc_type=doc_type,
    )


def _write_catalog(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["entity", "field_name", "type", "length", "nullable", "description"],
        )
        writer.writeheader()
        writer.writerows(rows)


def _row(
    entity: str,
    field_name: str,
    field_type: str,
    description: str,
    *,
    length: str = "",
) -> dict[str, str]:
    return {
        "entity": entity,
        "field_name": field_name,
        "type": field_type,
        "length": length,
        "nullable": "false",
        "description": description,
    }


def _suggestion_row(store: KnowledgeStore, suggestion_id: str):
    return store.conn.execute(
        """
        SELECT status, suggestion_payload
        FROM manifest_suggestions
        WHERE suggestion_id = ?
        """,
        (suggestion_id,),
    ).fetchone()
