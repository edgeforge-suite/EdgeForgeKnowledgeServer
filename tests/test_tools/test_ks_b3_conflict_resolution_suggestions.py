from __future__ import annotations

import csv
import json
from pathlib import Path

from knowledge_server.models import SuggestionDecision
from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.decisions import submit_suggestion_decisions
from knowledge_server.tools.evidence_chain import get_suggestion_evidence_chain
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.suggest import suggest_manifest_candidates


def test_conflict_resolution_scope_returns_compatible_normalization_delta(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_customer_id_sources(store, tmp_path)

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern="customerId",
    )

    assert result.success is True
    assert result.scope == "conflict_resolution"
    assert result.unsupported_scope is False
    assert result.suggestion_count == 1
    suggestion = result.suggestions[0]
    assert suggestion.suggestion_type == "conflict_resolution"
    assert suggestion.target_step == "step7"
    assert suggestion.manifest_path == ""
    assert suggestion.entity == "CUSTOMER"
    assert suggestion.field in {"CUSTOMER_ID", "customerId"}
    assert suggestion.payload["query"] == "customerId"
    assert suggestion.payload["scope"] == "conflict_resolution"
    assert suggestion.payload["difference_category"] == "compatible normalization"
    assert suggestion.payload["delta_summary"]
    assert suggestion.payload["source_a_document_name"] == "legacy.sql::CUSTOMER"
    assert suggestion.payload["source_b_document_name"] == "catalog.csv"
    assert suggestion.payload["source_a_field"] == "CUSTOMER_ID"
    assert suggestion.payload["source_b_field"] == "customerId"
    assert suggestion.payload["source_a_type"] == "VARCHAR"
    assert suggestion.payload["source_b_type"] == "string"
    assert suggestion.payload["normalized_field_mapping"] == {
        "source_a": "CUSTOMER_ID",
        "source_b": "customerId",
        "normalized_key": "customer_id",
    }
    assert "not a blocking conflict" in suggestion.payload["suggested_action"]
    assert suggestion.payload["document_a_id"]
    assert suggestion.payload["document_b_id"]
    assert suggestion.payload["chunk_a_id"]
    assert suggestion.payload["chunk_b_id"]
    assert len(suggestion.citations) == 2
    assert len(suggestion.source_document_ids) == 2


def test_conflict_resolution_scope_returns_type_difference_delta(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_customer_id_sources(store, tmp_path, csv_type="integer")

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern="customerId",
    )

    suggestion = result.suggestions[0]
    assert suggestion.payload["difference_category"] == "type difference"
    assert suggestion.payload["source_a_type"] == "VARCHAR"
    assert suggestion.payload["source_b_type"] == "integer"
    assert "incompatible type families" in suggestion.payload["interpretation"]


def test_conflict_resolution_entity_scope_still_filters_by_field_query(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_customer_id_sources(
        store,
        tmp_path,
        extra_ddl_column="    ACCOUNT_STATUS VARCHAR2(20),",
        extra_csv_rows=[
            {
                "entity": "Customer",
                "field_name": "accountStatus",
                "type": "integer",
                "nullable": "true",
                "description": "Unrelated status shape mismatch",
            }
        ],
    )

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern="customerId",
        entity="Customer",
    )

    assert result.suggestion_count == 1
    suggestion = result.suggestions[0]
    assert suggestion.payload["difference_category"] == "compatible normalization"
    assert suggestion.payload["source_a_field"] == "CUSTOMER_ID"
    assert suggestion.payload["source_b_field"] == "customerId"


def test_conflict_resolution_scope_returns_numeric_scale_delta(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_amount_sources(store, tmp_path, ddl_type="NUMBER(18,0)", csv_precision="18", csv_scale="2")

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern="AMOUNT_MINOR",
    )

    suggestion = result.suggestions[0]
    assert suggestion.payload["difference_category"] == "catalog shape difference"
    assert suggestion.payload["source_a_precision"] == 18
    assert suggestion.payload["source_a_scale"] == 0
    assert suggestion.payload["source_b_precision"] == 18
    assert suggestion.payload["source_b_scale"] == 2
    assert "precision, or scale" in suggestion.payload["interpretation"]


def test_conflict_resolution_scope_returns_varchar_length_delta(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_name_sources(store, tmp_path, ddl_type="VARCHAR2(36)", csv_length="64")

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern="customerName",
    )

    suggestion = result.suggestions[0]
    assert suggestion.payload["difference_category"] == "catalog shape difference"
    assert suggestion.payload["source_a_length"] == 36
    assert suggestion.payload["source_b_length"] == 64


def test_conflict_resolution_shape_delta_takes_precedence_over_normalization(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_customer_id_sources(store, tmp_path, csv_length="64")

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern="customerId",
    )

    suggestion = result.suggestions[0]
    assert suggestion.payload["difference_category"] == "catalog shape difference"
    assert suggestion.payload["source_a_field"] == "CUSTOMER_ID"
    assert suggestion.payload["source_a_length"] == 36
    assert suggestion.payload["source_b_field"] == "customerId"
    assert suggestion.payload["source_b_length"] == 64


def test_conflict_resolution_scope_returns_missing_field_delta(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_customer_id_sources(store, tmp_path, extra_ddl_column="    EMAIL VARCHAR2(255),")

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern="email",
    )

    suggestion = result.suggestions[0]
    assert suggestion.payload["difference_category"] == "missing field in one source"
    assert suggestion.payload["source_a_document_name"] == "legacy.sql::CUSTOMER"
    assert suggestion.payload["source_a_field"] == "EMAIL"
    assert suggestion.payload["source_b_document_name"] == "catalog.csv"
    assert suggestion.payload["source_b_field"] is None
    assert suggestion.payload["source_b_type"] is None


def test_conflict_resolution_blank_query_warns_without_persisting(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern=" ",
    )

    assert result.success is True
    assert result.suggestions == []
    assert "field_name_pattern" in result.warnings[0]
    assert _conflict_resolution_row_count(store) == 0


def test_conflict_resolution_repeated_calls_are_stable_without_duplicates(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_customer_id_sources(store, tmp_path)

    first = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern="customerId",
    )
    second = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern="customerId",
    )

    assert first.suggestions[0].suggestion_id == second.suggestions[0].suggestion_id
    assert _conflict_resolution_row_count(store) == 1


def test_conflict_resolution_status_persists_after_decision(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_customer_id_sources(store, tmp_path)
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern="customerId",
    ).suggestions[0]

    decision_result = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="accepted")],
    )
    refreshed = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern="customerId",
    )

    assert decision_result.success is True
    assert decision_result.outcomes[0].success is True
    assert refreshed.suggestions[0].suggestion_id == suggestion.suggestion_id
    assert refreshed.suggestions[0].status == "accepted"


def test_conflict_resolution_evidence_chain_returns_both_sides(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_customer_id_sources(store, tmp_path)
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern="customerId",
    ).suggestions[0]

    chain = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=suggestion.suggestion_id,
        scope="conflict_resolution",
    )

    assert chain.success is True
    assert chain.scope == "conflict_resolution"
    assert chain.suggestion is not None
    assert chain.suggestion.suggestion_id == suggestion.suggestion_id
    assert len(chain.evidence_chunks) == 2
    assert {
        chunk.document_id for chunk in chain.evidence_chunks
    } == set(suggestion.source_document_ids)
    assert chain.source_count == 2


def test_conflict_resolution_project_isolation(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_conflict_docs(store, tmp_path, project_id="project-a")
    other = tmp_path / "project-b.md"
    other.write_text("# Balance\n\nThe balance includes memo credits.\n", encoding="utf-8")
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-b",
        file_path=str(other),
        doc_type="markdown",
    )

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-b",
        scope="conflict_resolution",
        field_name_pattern="balance",
    )

    assert result.suggestions == []
    assert _conflict_resolution_row_count(store) == 0


def test_conflict_resolution_broad_overlap_without_delta_does_not_persist(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_conflict_docs(store, tmp_path, project_id="project-a")

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern="balance",
    )

    assert result.suggestions == []
    assert "Broad source overlap" in result.warnings[0]
    assert _conflict_resolution_row_count(store) == 0


def test_conflict_resolution_edited_payload_validation(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_customer_id_sources(store, tmp_path)
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern="customerId",
    ).suggestions[0]
    preferred_document_id = suggestion.payload["document_a_id"]

    valid = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={
                    "preferred_document_id": preferred_document_id,
                    "resolution_note": "Prefer the newer balance policy.",
                    "rationale": "Reviewer confirmed the policy owner.",
                },
            )
        ],
    )
    missing_payload = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="edited")],
    )
    invalid_preference = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={"preferred_document_id": "other-doc"},
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

    assert valid.success is True
    assert valid.outcomes[0].success is True
    stored_payload = _stored_conflict_payload(store, suggestion.suggestion_id)
    assert stored_payload["status"] == "edited"
    assert stored_payload["edited_payload"]["preferred_document_id"] == preferred_document_id
    assert missing_payload.success is False
    assert "edited_payload is required" in (missing_payload.outcomes[0].error or "")
    assert invalid_preference.success is False
    assert "conflicting document IDs" in (invalid_preference.outcomes[0].error or "")
    assert unknown_only.success is False
    assert "unsupported keys" in (unknown_only.outcomes[0].error or "")


def test_conflict_resolutions_plural_scope_remains_unsupported(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolutions",
        field_name_pattern="balance",
    )

    assert result.success is False
    assert result.unsupported_scope is True
    assert result.suggestions == []
    assert _conflict_resolution_row_count(store) == 0


def _ingest_conflict_docs(store: KnowledgeStore, tmp_path: Path, *, project_id: str) -> None:
    first = tmp_path / f"{project_id}-balance-a.md"
    second = tmp_path / f"{project_id}-balance-b.md"
    first.write_text("# Balance Rules\n\nThe balance includes memo credits.\n", encoding="utf-8")
    second.write_text("# Balance Exceptions\n\nThe balance excludes memo credits.\n", encoding="utf-8")
    for source in [first, second]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id=project_id,
            file_path=str(source),
            doc_type="markdown",
        )


def _ingest_customer_id_sources(
    store: KnowledgeStore,
    tmp_path: Path,
    *,
    csv_type: str = "string",
    csv_length: str = "",
    extra_ddl_column: str | None = None,
    extra_csv_rows: list[dict[str, str]] | None = None,
) -> None:
    ddl_lines = [
        "-- Oracle customer table",
        "CREATE TABLE CUSTOMER (",
        "    CUSTOMER_ID VARCHAR2(36) NOT NULL,",
    ]
    if extra_ddl_column:
        ddl_lines.append(extra_ddl_column)
    ddl_lines.extend(
        [
            "    CREATED_AT TIMESTAMP NOT NULL,",
            "    CONSTRAINT PK_CUSTOMER PRIMARY KEY (CUSTOMER_ID)",
            ");",
            "COMMENT ON COLUMN CUSTOMER.CUSTOMER_ID IS 'UUID primary key';",
        ]
    )
    ddl = tmp_path / "legacy.sql"
    ddl.write_text("\n".join(ddl_lines), encoding="utf-8")
    csv_path = tmp_path / "catalog.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["entity", "field_name", "type", "length", "nullable", "description"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "entity": "Customer",
                "field_name": "customerId",
                "type": csv_type,
                "length": csv_length,
                "nullable": "false",
                "description": "Customer identifier",
            }
        )
        for row in extra_csv_rows or []:
            writer.writerow(row)

    for path, doc_type in [(ddl, "sql"), (csv_path, "csv")]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(path),
            doc_type=doc_type,
        )


def _ingest_amount_sources(
    store: KnowledgeStore,
    tmp_path: Path,
    *,
    ddl_type: str,
    csv_precision: str,
    csv_scale: str,
) -> None:
    ddl = tmp_path / "amount-ddl.sql"
    ddl.write_text(
        "\n".join(
            [
                "CREATE TABLE PAYMENT_ORDER (",
                f"    AMOUNT_MINOR {ddl_type} NOT NULL",
                ");",
            ]
        ),
        encoding="utf-8",
    )
    csv_path = tmp_path / "amount-catalog.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "entity",
                "field_name",
                "type",
                "precision",
                "scale",
                "nullable",
                "description",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "entity": "PAYMENT_ORDER",
                "field_name": "AMOUNT_MINOR",
                "type": "decimal",
                "precision": csv_precision,
                "scale": csv_scale,
                "nullable": "false",
                "description": "Payment amount",
            }
        )
    for path, doc_type in [(ddl, "sql"), (csv_path, "csv")]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(path),
            doc_type=doc_type,
        )


def _ingest_name_sources(
    store: KnowledgeStore,
    tmp_path: Path,
    *,
    ddl_type: str,
    csv_length: str,
) -> None:
    ddl = tmp_path / "name-ddl.sql"
    ddl.write_text(
        "\n".join(
            [
                "CREATE TABLE CUSTOMER (",
                f"    CUSTOMER_NAME {ddl_type}",
                ");",
            ]
        ),
        encoding="utf-8",
    )
    csv_path = tmp_path / "name-catalog.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "entity",
                "field_name",
                "type",
                "length",
                "nullable",
                "description",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "entity": "CUSTOMER",
                "field_name": "CUSTOMER_NAME",
                "type": "VARCHAR",
                "length": csv_length,
                "nullable": "true",
                "description": "Customer name",
            }
        )
    for path, doc_type in [(ddl, "sql"), (csv_path, "csv")]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(path),
            doc_type=doc_type,
        )


def _conflict_resolution_row_count(store: KnowledgeStore) -> int:
    row = store.conn.execute(
        """
        SELECT COUNT(*) AS row_count
        FROM manifest_suggestions
        WHERE suggestion_type = 'conflict_resolution'
        """
    ).fetchone()
    return int(row["row_count"])


def _stored_conflict_payload(store: KnowledgeStore, suggestion_id: str) -> dict:
    row = store.conn.execute(
        """
        SELECT suggestion_payload
        FROM manifest_suggestions
        WHERE suggestion_id = ?
        """,
        (suggestion_id,),
    ).fetchone()
    assert row is not None
    return json.loads(row["suggestion_payload"])
