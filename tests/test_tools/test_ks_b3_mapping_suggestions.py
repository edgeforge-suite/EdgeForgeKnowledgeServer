from __future__ import annotations

import csv
from pathlib import Path

from knowledge_server.models import SuggestionDecision
from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.decisions import submit_suggestion_decisions
from knowledge_server.tools.evidence_chain import get_suggestion_evidence_chain
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.suggest import suggest_manifest_candidates


def test_mappings_scope_suggests_exact_normalized_field_match(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_catalog_pair(
        store,
        tmp_path,
        source_rows=[
            _field("RORequest", "payment_id", "string"),
        ],
        target_rows=[
            _field("D1Request", "payment_id", "varchar"),
        ],
    )

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="mappings",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
        direction="request",
    )

    assert result.success is True
    assert result.scope == "mappings"
    assert result.unsupported_scope is False
    assert result.suggestion_count == 1
    suggestion = result.suggestions[0]
    assert suggestion.suggestion_type == "mapping"
    assert suggestion.target_step == "step4"
    assert suggestion.entity == "D1Request"
    assert suggestion.field == "payment_id"
    assert suggestion.manifest_path == (
        "async_routes.payment_router.transform_mapping.request.payment_id.payment_id"
    )
    assert suggestion.payload == {
        "route_name": "payment_router",
        "direction": "request",
        "source_entity": "RORequest",
        "target_entity": "D1Request",
        "source_field": "payment_id",
        "target_field": "payment_id",
        "mapping_type": "copy",
        "confidence_basis": "exact_name_match_and_type_compatible",
        "value_map": None,
    }
    assert suggestion.citations
    assert len(suggestion.source_document_ids) == 2


def test_mappings_scope_suggests_camel_snake_equivalent_match(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_catalog_pair(
        store,
        tmp_path,
        source_rows=[_field("RORequest", "paymentId", "string")],
        target_rows=[_field("D1Request", "payment_id", "string")],
    )

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="mappings",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
        direction="request",
        field_name_pattern="payment",
    )

    suggestion = result.suggestions[0]
    assert suggestion.entity == "D1Request"
    assert suggestion.field == "payment_id"
    assert suggestion.payload["source_field"] == "paymentId"
    assert suggestion.payload["target_field"] == "payment_id"
    assert suggestion.payload["confidence_basis"] == "name_match_and_type_compatible"


def test_mappings_scope_does_not_suggest_obvious_incompatible_types(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_catalog_pair(
        store,
        tmp_path,
        source_rows=[_field("RORequest", "createdAt", "date")],
        target_rows=[_field("D1Request", "createdAt", "integer")],
    )

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="mappings",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
        direction="request",
    )

    assert result.suggestions == []
    assert _mapping_row_count(store) == 0


def test_mappings_scope_skips_ambiguous_prefix_matches_with_warning(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_catalog_pair(
        store,
        tmp_path,
        source_rows=[_field("RORequest", "accountId", "string")],
        target_rows=[
            _field("D1Request", "accountNumber", "string"),
            _field("D1Request", "accountIdentifier", "string"),
        ],
    )

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="mappings",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
        direction="request",
    )

    assert result.suggestions == []
    assert result.warnings
    assert "Ambiguous mapping for source field RORequest.accountId" in result.warnings[0]
    assert _mapping_row_count(store) == 0


def test_mappings_scope_requires_source_target_route_and_direction_without_persisting(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="mappings",
        source_entity="RORequest",
    )

    assert result.success is True
    assert result.unsupported_scope is False
    assert result.suggestions == []
    assert "source_entity and target_entity" in result.warnings[0]
    assert _mapping_row_count(store) == 0

    _ingest_catalog_pair(
        store,
        tmp_path,
        source_rows=[_field("RORequest", "paymentId", "string")],
        target_rows=[_field("D1Request", "payment_id", "string")],
    )
    missing_route = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="mappings",
        source_entity="RORequest",
        target_entity="D1Request",
        direction="request",
    )
    missing_direction = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="mappings",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
    )

    assert missing_route.suggestions == []
    assert missing_direction.suggestions == []
    assert "route_name and direction" in missing_route.warnings[0]
    assert "route_name and direction" in missing_direction.warnings[0]
    assert _mapping_row_count(store) == 0


def test_mapping_suggestion_ids_and_status_persist_across_regeneration(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_catalog_pair(
        store,
        tmp_path,
        source_rows=[_field("RORequest", "paymentId", "string")],
        target_rows=[_field("D1Request", "paymentId", "string")],
    )

    first = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="mappings",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
        direction="request",
    )
    suggestion_id = first.suggestions[0].suggestion_id
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion_id, status="accepted")],
    )
    second = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="mappings",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
        direction="request",
    )

    assert second.suggestions[0].suggestion_id == suggestion_id
    assert second.suggestions[0].status == "accepted"


def test_mapping_evidence_chain_returns_persisted_mapping_and_citations(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_catalog_pair(
        store,
        tmp_path,
        source_rows=[_field("RORequest", "paymentId", "string")],
        target_rows=[_field("D1Request", "payment_id", "string")],
    )
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="mappings",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
        direction="request",
    ).suggestions[0]

    chain = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=suggestion.suggestion_id,
        scope="mappings",
    )

    assert chain.success is True
    assert chain.scope == "mappings"
    assert chain.suggestion is not None
    assert chain.suggestion.suggestion_id == suggestion.suggestion_id
    assert chain.evidence_chunks
    assert chain.source_count == 2


def test_mapping_edited_payload_validation_accepts_valid_copy_payload(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    suggestion = _persist_one_mapping_suggestion(store, tmp_path)

    result = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={
                    "route_name": "payment_router",
                    "direction": "request",
                    "source_entity": "RORequest",
                    "target_entity": "D1Request",
                    "source_field": "paymentId",
                    "target_field": "payment_id",
                    "mapping_type": "copy",
                    "confidence_basis": "name_match_and_type_compatible",
                    "value_map": None,
                },
            )
        ],
    )

    assert result.success is True
    assert result.outcomes[0].success is True


def test_mapping_edited_payload_validation_rejects_invalid_shapes(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    suggestion = _persist_one_mapping_suggestion(store, tmp_path)

    result = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={
                    "route_name": "payment_router",
                    "direction": "request",
                    "source_entity": "RORequest",
                    "target_entity": "D1Request",
                    "source_field": "paymentId",
                    "mapping_type": "copy",
                    "confidence_basis": "name_match_and_type_compatible",
                },
            ),
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={
                    "route_name": "payment_router",
                    "direction": "request",
                    "source_entity": "RORequest",
                    "target_entity": "D1Request",
                    "source_field": "paymentId",
                    "target_field": "payment_id",
                    "mapping_type": "value_map",
                    "confidence_basis": "manual",
                },
            ),
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={
                    "route_name": "payment_router",
                    "direction": "request",
                    "source_entity": "RORequest",
                    "target_entity": "D1Request",
                    "source_field": "paymentId",
                    "target_field": "payment_id",
                    "mapping_type": "copy",
                    "confidence_basis": "manual",
                    "value_map": {"A": "B"},
                },
            ),
        ],
    )

    assert result.success is False
    assert result.outcome_count == 3
    errors = [outcome.error or "" for outcome in result.outcomes]
    assert any("target_field" in error for error in errors)
    assert any("mapping_type" in error for error in errors)
    assert any("value_map" in error for error in errors)


def test_unsupported_random_scope_still_does_not_persist_fake_suggestions(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="not_a_scope",
    )

    assert result.success is False
    assert result.unsupported_scope is True
    assert result.suggestions == []
    assert _mapping_row_count(store) == 0


def _persist_one_mapping_suggestion(store: KnowledgeStore, tmp_path: Path):
    _ingest_catalog_pair(
        store,
        tmp_path,
        source_rows=[_field("RORequest", "paymentId", "string")],
        target_rows=[_field("D1Request", "payment_id", "string")],
    )
    return suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="mappings",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
        direction="request",
    ).suggestions[0]


def _ingest_catalog_pair(
    store: KnowledgeStore,
    tmp_path: Path,
    *,
    source_rows: list[dict[str, str]],
    target_rows: list[dict[str, str]],
) -> None:
    source = _write_catalog_csv(tmp_path / "source.csv", source_rows)
    target = _write_catalog_csv(tmp_path / "target.csv", target_rows)
    for path in [source, target]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(path),
            doc_type="csv",
        )


def _write_catalog_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["entity", "field_name", "type", "nullable", "description"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def _field(entity: str, field_name: str, field_type: str) -> dict[str, str]:
    return {
        "entity": entity,
        "field_name": field_name,
        "type": field_type,
        "nullable": "true",
        "description": f"{entity}.{field_name}",
    }


def _mapping_row_count(store: KnowledgeStore) -> int:
    row = store.conn.execute(
        """
        SELECT COUNT(*) AS row_count
        FROM manifest_suggestions
        WHERE suggestion_type = 'mapping'
        """
    ).fetchone()
    return int(row["row_count"])
