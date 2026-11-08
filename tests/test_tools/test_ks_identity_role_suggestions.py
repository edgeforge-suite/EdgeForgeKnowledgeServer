from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from knowledge_server.models import SuggestionDecision
from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.decisions import submit_suggestion_decisions
from knowledge_server.tools.evidence_chain import get_suggestion_evidence_chain
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.suggest import suggest_manifest_candidates


def test_identity_role_scope_suggests_structural_and_documentary_roles(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_identity_fixture(store, tmp_path)

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="TransactionPosting",
    )

    by_field = {suggestion.field: suggestion for suggestion in result.suggestions}
    assert result.success is True
    assert result.unsupported_scope is False
    assert by_field["postingRowId"].payload["suggested_role"] == "persistence_id"
    assert "ddl_primary_key" in by_field["postingRowId"].payload["signals"]
    assert by_field["accountId"].payload["suggested_role"] == "parent_reference"
    assert "ddl_foreign_key" in by_field["accountId"].payload["signals"]
    assert by_field["transactionId"].payload["suggested_role"] == "idempotency_key"
    assert "brd_identity_language" in by_field["transactionId"].payload["signals"]
    assert by_field["correlationId"].payload["suggested_role"] == "correlation_id"
    assert by_field["providerReference"].payload["suggested_role"] == "external_reference"
    assert by_field["postingRowId"].manifest_path == (
        "entities.TransactionPosting.fields.postingRowId.identity_role"
    )
    assert by_field["postingRowId"].source_document_ids
    assert by_field["postingRowId"].payload["source_document_names"]
    assert by_field["postingRowId"].payload["review_needed"] is False


def test_identity_role_event_parent_reference_is_not_persistence_without_pk(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_catalog(
        store,
        tmp_path / "events.csv",
        [
            _row("Account", "accountId", "string", "Primary account identifier"),
            _row("TransactionPosting", "accountId", "string", "Owning account identifier"),
            _row("TransactionPosting", "transactionId", "string", "Transaction identifier"),
        ],
    )

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="TransactionPosting",
        field_name_pattern="accountId",
    )

    assert result.suggestion_count == 1
    suggestion = result.suggestions[0]
    assert suggestion.field == "accountId"
    assert suggestion.payload["suggested_role"] == "parent_reference"
    assert "event_entity_guard" in suggestion.payload["signals"]
    assert suggestion.payload["suggested_role"] != "persistence_id"


def test_identity_role_field_catalog_description_can_provide_evidence(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_catalog(
        store,
        tmp_path / "catalog.csv",
        [
            _row(
                "LedgerEntry",
                "ledgerEntryId",
                "string",
                "Surrogate row id and primary key for the ledger entry.",
            )
        ],
    )

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="LedgerEntry",
    )

    suggestion = result.suggestions[0]
    assert suggestion.payload["suggested_role"] == "persistence_id"
    assert suggestion.payload["signals"] == ["field_catalog_identity_hint"]


def test_identity_role_suggestions_have_stable_ids_and_preserve_status(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_identity_fixture(store, tmp_path)
    first = _suggest_identity_roles(store)
    suggestion = first.suggestions[0]

    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="accepted")],
    )
    accepted = _suggest_identity_roles(store).suggestions[0]
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={
                    "entity": suggestion.entity,
                    "field": suggestion.field,
                    "role": suggestion.payload["suggested_role"],
                    "rationale": "Reviewed with source owner.",
                },
            )
        ],
    )
    edited = _suggest_identity_roles(store).suggestions[0]

    assert accepted.suggestion_id == suggestion.suggestion_id
    assert accepted.status == "accepted"
    assert edited.suggestion_id == suggestion.suggestion_id
    assert edited.status == "edited"
    assert edited.edited_payload["role"] == suggestion.payload["suggested_role"]
    assert _suggestion_count(store, "identity_role") == first.suggestion_count


def test_identity_role_id_stays_stable_when_stronger_evidence_arrives(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_catalog(
        store,
        tmp_path / "catalog.csv",
        [
            _row(
                "TransactionPosting",
                "postingRowId",
                "string",
                "Primary key row id for transaction posting.",
            )
        ],
    )
    first = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="TransactionPosting",
    )
    suggestion = first.suggestions[0]
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="accepted")],
    )
    ddl = tmp_path / "posting.sql"
    ddl.write_text(
        """
        CREATE TABLE TRANSACTION_POSTING (
            posting_row_id VARCHAR2(36) PRIMARY KEY
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

    refreshed = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="TransactionPosting",
    )

    refreshed_suggestion = refreshed.suggestions[0]
    assert refreshed_suggestion.suggestion_id == suggestion.suggestion_id
    assert refreshed_suggestion.status == "accepted"
    assert refreshed_suggestion.payload["suggested_role"] == "persistence_id"
    assert "ddl_primary_key" in refreshed_suggestion.payload["signals"]
    assert _suggestion_count(store, "identity_role") == 1


def test_identity_role_reingest_preserves_status_for_still_valid_suggestion(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ddl = tmp_path / "identity.sql"
    _write_identity_reingest_ddl(ddl, include_posting_row=True)
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(ddl),
        doc_type="sql",
    )
    first = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="TRANSACTION_POSTING",
    )
    by_field = {suggestion.field: suggestion for suggestion in first.suggestions}
    posting_suggestion_id = by_field["posting_row_id"].suggestion_id
    account_suggestion = by_field["account_id"]
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=account_suggestion.suggestion_id,
                status="accepted",
            )
        ],
    )

    _write_identity_reingest_ddl(ddl, include_posting_row=False)
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
        entity="TRANSACTION_POSTING",
    )
    refreshed_by_field = {suggestion.field: suggestion for suggestion in refreshed.suggestions}
    stale_chain = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=posting_suggestion_id,
        scope="identity_role",
    )

    assert "posting_row_id" not in refreshed_by_field
    assert refreshed_by_field["account_id"].suggestion_id == account_suggestion.suggestion_id
    assert refreshed_by_field["account_id"].status == "accepted"
    assert stale_chain.success is False
    assert "suggestion not found" in stale_chain.warnings[0]


def test_identity_role_reingest_preserves_edited_and_rejected_state(
    tmp_path: Path,
) -> None:
    cases = [
        (
            "edited",
            "edited",
            {
                "entity": "TRANSACTION_POSTING",
                "field": "account_id",
                "role": "parent_reference",
                "rationale": "Confirmed by source owner.",
            },
        ),
        ("rejected", "rejected", None),
    ]

    for case_name, status, edited_payload in cases:
        case_dir = tmp_path / case_name
        case_dir.mkdir()
        store = KnowledgeStore(case_dir / "ks.sqlite3")
        ddl = case_dir / "identity.sql"
        _write_identity_reingest_ddl(ddl, include_posting_row=False, comment="initial")
        ingest_document(
            store=store,
            allowed_roots=[case_dir],
            project_id="project-a",
            file_path=str(ddl),
            doc_type="sql",
        )
        suggestion = suggest_manifest_candidates(
            store=store,
            project_id="project-a",
            scope="identity_role",
            entity="TRANSACTION_POSTING",
        ).suggestions[0]
        submit_suggestion_decisions(
            store=store,
            project_id="project-a",
            decisions=[
                SuggestionDecision(
                    suggestion_id=suggestion.suggestion_id,
                    status=status,
                    edited_payload=edited_payload,
                )
            ],
        )

        _write_identity_reingest_ddl(ddl, include_posting_row=False, comment="changed")
        ingest_document(
            store=store,
            allowed_roots=[case_dir],
            project_id="project-a",
            file_path=str(ddl),
            doc_type="sql",
        )
        refreshed = suggest_manifest_candidates(
            store=store,
            project_id="project-a",
            scope="identity_role",
            entity="TRANSACTION_POSTING",
        ).suggestions[0]

        assert refreshed.suggestion_id == suggestion.suggestion_id
        assert refreshed.status == status
        if status == "edited":
            assert refreshed.edited_payload == edited_payload


def test_identity_role_unique_event_field_defaults_to_business_key(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ddl = tmp_path / "posting.sql"
    ddl.write_text(
        """
        CREATE TABLE TRANSACTION_POSTING (
            transaction_id VARCHAR2(64) UNIQUE
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

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="TRANSACTION_POSTING",
    )

    suggestion = result.suggestions[0]
    assert suggestion.payload["suggested_role"] == "business_key"
    assert "ddl_unique_constraint" in suggestion.payload["signals"]
    assert suggestion.payload["suggested_role"] != "event_id"


def test_identity_role_evidence_chain_and_wrong_scope(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_identity_fixture(store, tmp_path)
    suggestion = _suggest_identity_roles(store).suggestions[0]

    chain = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=suggestion.suggestion_id,
        scope="identity_role",
    )
    wrong_scope = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=suggestion.suggestion_id,
        scope="fields",
    )

    assert chain.success is True
    assert chain.scope == "identity_role"
    assert chain.suggestion.suggestion_id == suggestion.suggestion_id
    assert chain.evidence_chunks
    assert wrong_scope.success is False
    assert "not scope 'fields'" in wrong_scope.warnings[0]


def test_identity_role_edited_payload_validation(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_identity_fixture(store, tmp_path)
    suggestion = _suggest_identity_roles(store).suggestions[0]

    invalid_role = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={
                    "entity": suggestion.entity,
                    "field": suggestion.field,
                    "role": "primary_key",
                },
            )
        ],
    )
    missing_field = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={"entity": suggestion.entity, "role": "persistence_id"},
            )
        ],
    )
    unknown_only = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={"foo": "bar"},
            )
        ],
    )

    assert invalid_role.success is False
    assert "must be one of" in invalid_role.outcomes[0].error
    assert missing_field.success is False
    assert "field" in missing_field.outcomes[0].error
    assert unknown_only.success is False
    assert "unsupported keys" in unknown_only.outcomes[0].error


def test_identity_role_no_evidence_returns_warning_without_persisting(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_catalog(
        store,
        tmp_path / "catalog.csv",
        [_row("Account", "displayName", "string", "Display name")],
    )

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="Account",
    )

    assert result.suggestions == []
    assert "No evidence-backed identity_role suggestions" in result.warnings[0]
    assert _suggestion_count(store, "identity_role") == 0


def test_identity_roles_plural_scope_remains_unsupported(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_roles",
    )

    assert result.success is False
    assert result.unsupported_scope is True
    assert result.suggestions == []


def test_field_catalog_source_metadata_column_migrates_legacy_db(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE field_catalog (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            entity_name TEXT,
            field_name TEXT NOT NULL,
            field_type TEXT,
            length INTEGER,
            precision INTEGER,
            scale INTEGER,
            nullable INTEGER,
            description TEXT,
            source_location TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO field_catalog (
            id, project_id, document_id, entity_name, field_name, field_type,
            length, precision, scale, nullable, description, source_location
        ) VALUES ('f1', 'project-a', 'doc-a', 'Account', 'accountId', 'string',
            NULL, NULL, NULL, 0, 'Primary account id', 'row 2')
        """
    )
    conn.commit()
    conn.close()

    store = KnowledgeStore(db_path)

    columns = {
        row["name"]: row
        for row in store.conn.execute("PRAGMA table_info(field_catalog)").fetchall()
    }
    row = store.conn.execute("SELECT source_metadata FROM field_catalog WHERE id = 'f1'").fetchone()
    assert "source_metadata" in columns
    assert columns["source_metadata"]["dflt_value"] == "'{}'"
    assert row["source_metadata"] == "{}"


def _suggest_identity_roles(store: KnowledgeStore):
    return suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="TransactionPosting",
    )


def _ingest_identity_fixture(store: KnowledgeStore, tmp_path: Path) -> None:
    ddl = tmp_path / "identity.sql"
    ddl.write_text(
        """
        CREATE TABLE ACCOUNT (
            account_id VARCHAR2(36) PRIMARY KEY
        );

        CREATE TABLE TRANSACTION_POSTING (
            posting_row_id VARCHAR2(36) PRIMARY KEY,
            account_id VARCHAR2(36) NOT NULL,
            transaction_id VARCHAR2(64) NOT NULL,
            correlation_id VARCHAR2(64),
            provider_reference VARCHAR2(64),
            CONSTRAINT fk_posting_account FOREIGN KEY (account_id) REFERENCES ACCOUNT(account_id),
            CONSTRAINT uq_transaction_id UNIQUE (transaction_id)
        );
        """,
        encoding="utf-8",
    )
    _ingest_catalog(
        store,
        tmp_path / "catalog.csv",
        [
            _row("TransactionPosting", "postingRowId", "string", "Posting row identifier"),
            _row("TransactionPosting", "accountId", "string", "Owning account identifier"),
            _row("TransactionPosting", "transactionId", "string", "Externally supplied transaction ID"),
            _row("TransactionPosting", "correlationId", "string", "Request correlation identifier"),
            _row("TransactionPosting", "providerReference", "string", "Payment gateway provider reference"),
        ],
    )
    brd = tmp_path / "identity-brd.md"
    brd.write_text(
        """
        # Transaction identity

        Transaction ID is used for duplicate detection and retry safety.
        Correlation ID traces the request workflow across systems.
        Provider reference comes from the external payment gateway.
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
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(brd),
        doc_type="markdown",
    )


def _write_identity_reingest_ddl(
    path: Path,
    *,
    include_posting_row: bool,
    comment: str = "source",
) -> None:
    posting_row = (
        "posting_row_id VARCHAR2(36) PRIMARY KEY,\n"
        if include_posting_row
        else ""
    )
    path.write_text(
        f"""
        -- {comment}
        CREATE TABLE ACCOUNT (
            account_id VARCHAR2(36) PRIMARY KEY
        );

        CREATE TABLE TRANSACTION_POSTING (
            {posting_row}
            account_id VARCHAR2(36) NOT NULL,
            CONSTRAINT fk_posting_account FOREIGN KEY (account_id) REFERENCES ACCOUNT(account_id)
        );
        """,
        encoding="utf-8",
    )


def _ingest_catalog(store: KnowledgeStore, path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["entity", "field_name", "type", "nullable", "description"],
        )
        writer.writeheader()
        writer.writerows(rows)
    ingest_document(
        store=store,
        allowed_roots=[path.parent],
        project_id="project-a",
        file_path=str(path),
        doc_type="csv",
    )


def _row(entity: str, field_name: str, field_type: str, description: str) -> dict[str, str]:
    return {
        "entity": entity,
        "field_name": field_name,
        "type": field_type,
        "nullable": "false",
        "description": description,
    }


def _suggestion_count(store: KnowledgeStore, suggestion_type: str) -> int:
    row = store.conn.execute(
        "SELECT COUNT(*) AS row_count FROM manifest_suggestions WHERE suggestion_type = ?",
        (suggestion_type,),
    ).fetchone()
    return int(row["row_count"])
