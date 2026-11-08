from __future__ import annotations

import csv
from pathlib import Path

from knowledge_server.models import SuggestionDecision
from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.decisions import submit_suggestion_decisions
from knowledge_server.tools.evidence_chain import get_suggestion_evidence_chain
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.suggest import suggest_manifest_candidates


def test_transforms_scope_requires_router_context_without_persisting(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    missing_entities = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="transforms",
        route_name="payment_router",
        direction="request",
    )
    _ingest_catalog_pair(
        store,
        tmp_path,
        source_rows=[_field("RORequest", "paymentId", "string")],
        target_rows=[_field("D1Request", "paymentId", "string")],
    )
    missing_route = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="transforms",
        source_entity="RORequest",
        target_entity="D1Request",
        direction="request",
    )
    missing_direction = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="transforms",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
    )
    missing_target_id = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="transforms",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
        direction="request",
    )

    assert missing_entities.suggestions == []
    assert "source_entity and target_entity" in missing_entities.warnings[0]
    assert missing_route.suggestions == []
    assert "route_name and direction" in missing_route.warnings[0]
    assert missing_direction.suggestions == []
    assert "route_name and direction" in missing_direction.warnings[0]
    assert missing_target_id.suggestions == []
    assert "target_id" in missing_target_id.warnings[0]
    assert _transform_row_count(store) == 0


def test_transforms_scope_invalid_direction_warns_without_persisting(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_catalog_pair(
        store,
        tmp_path,
        source_rows=[_field("RORequest", "paymentId", "string")],
        target_rows=[_field("D1Request", "paymentId", "string")],
    )

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="transforms",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
        target_id="ledger-core",
        direction="sideways",
    )

    assert result.suggestions == []
    assert "direction" in result.warnings[0]
    assert _transform_row_count(store) == 0


def test_transforms_scope_suggests_exact_normalized_field_match(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_catalog_pair(
        store,
        tmp_path,
        source_rows=[_field("RORequest", "payment_id", "string")],
        target_rows=[_field("D1Request", "payment_id", "varchar")],
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

    assert result.success is True
    assert result.scope == "transforms"
    assert result.unsupported_scope is False
    assert result.suggestion_count == 1
    suggestion = result.suggestions[0]
    assert suggestion.suggestion_type == "transform"
    assert suggestion.target_step == "kafka_step3"
    assert suggestion.entity == "D1Request"
    assert suggestion.field == "payment_id"
    assert suggestion.manifest_path == (
        "async_routes.payment_router.router_config.targets.ledger-core.request_transform"
    )
    assert suggestion.payload["source"] == "$.payment_id"
    assert suggestion.payload["target"] == "$.payment_id"
    assert suggestion.payload["value_map"] is None
    assert suggestion.payload["type_coercion"] is None
    assert suggestion.payload["target_id"] == "ledger-core"
    assert suggestion.payload["transform_file_suggestion"] == (
        "transforms/payment-router-ledger-core-request.yaml"
    )
    assert result.warnings == []
    assert suggestion.citations
    assert len(suggestion.source_document_ids) == 2


def test_transforms_scope_suggests_camel_snake_equivalent_match(tmp_path: Path) -> None:
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
        scope="transforms",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
        target_id="ledger-core",
        direction="response",
        field_name_pattern="payment",
    )

    suggestion = result.suggestions[0]
    assert suggestion.manifest_path == (
        "async_routes.payment_router.router_config.targets.ledger-core.response_transform"
    )
    assert suggestion.payload["source"] == "$.paymentId"
    assert suggestion.payload["target"] == "$.payment_id"
    assert suggestion.payload["confidence_basis"] == "name_match_and_type_compatible"


def test_transforms_scope_skips_incompatible_field_types_without_evidence(
    tmp_path: Path,
) -> None:
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
        scope="transforms",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
        target_id="ledger-core",
        direction="request",
    )

    assert result.suggestions == []
    assert _transform_row_count(store) == 0


def test_transform_suggestion_ids_and_status_persist_across_regeneration(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_catalog_pair(
        store,
        tmp_path,
        source_rows=[_field("RORequest", "paymentId", "string")],
        target_rows=[_field("D1Request", "paymentId", "string")],
    )
    first = _suggest_transform(store)
    suggestion_id = first.suggestions[0].suggestion_id

    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion_id, status="accepted")],
    )
    accepted = _suggest_transform(store).suggestions[0]
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion_id, status="rejected")],
    )
    rejected = _suggest_transform(store).suggestions[0]
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion_id,
                status="edited",
                edited_payload={
                    "source": "$.paymentId",
                    "target": "$.paymentId",
                    "rationale": "Reviewed for router target.",
                },
            )
        ],
    )
    edited = _suggest_transform(store).suggestions[0]

    assert accepted.suggestion_id == suggestion_id
    assert accepted.status == "accepted"
    assert rejected.status == "rejected"
    assert edited.status == "edited"
    assert edited.edited_payload["target"] == "$.paymentId"
    assert _transform_row_count(store) == 1


def test_transform_edited_payload_validation(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_catalog_pair(
        store,
        tmp_path,
        source_rows=[_field("RORequest", "amount", "decimal")],
        target_rows=[_field("D1Request", "amount", "integer")],
    )
    # Types differ, so persist a compatible suggestion for validation setup separately.
    _ingest_catalog_pair(
        store,
        tmp_path,
        source_rows=[_field("RORequest", "paymentId", "string")],
        target_rows=[_field("D1Request", "paymentId", "string")],
    )
    suggestion = _suggest_transform(store, field_name_pattern="paymentId").suggestions[0]

    valid = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={
                    "source": "$.amount",
                    "target": "$.amountMinor",
                    "type_coercion": "major_to_minor_units",
                    "rationale": "Documented amount unit transform.",
                },
            )
        ],
    )
    missing_target = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={"source": "$.paymentId"},
            )
        ],
    )
    missing_source_or_constant = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={"target": "$.paymentId"},
            )
        ],
    )
    default_value_valid = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={
                    "target": "$.countryCode",
                    "default_value": "US",
                    "rationale": "Default from reviewed router transform.",
                },
            )
        ],
    )
    invalid_value_map = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={
                    "source": "$.status",
                    "target": "$.status",
                    "value_map": "ACTIVE=ACTIVE",
                },
            )
        ],
    )
    invalid_type_coercion = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={
                    "source": "$.amount",
                    "target": "$.amount",
                    "type_coercion": "stringify",
                },
            )
        ],
    )
    constant_valid = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={"target": "$.sourceSystem", "constant": "RO"},
            )
        ],
    )

    assert valid.success is True
    assert valid.outcomes[0].success is True
    assert missing_target.success is False
    assert "target" in (missing_target.outcomes[0].error or "")
    assert missing_source_or_constant.success is False
    assert "source, constant, or default_value" in (
        missing_source_or_constant.outcomes[0].error or ""
    )
    assert invalid_value_map.success is False
    assert "value_map" in (invalid_value_map.outcomes[0].error or "")
    assert invalid_type_coercion.success is False
    assert "type_coercion" in (invalid_type_coercion.outcomes[0].error or "")
    assert constant_valid.success is True
    assert default_value_valid.success is True


def test_transform_evidence_chain_returns_catalog_citations(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_catalog_pair(
        store,
        tmp_path,
        source_rows=[_field("RORequest", "paymentId", "string")],
        target_rows=[_field("D1Request", "paymentId", "string")],
    )
    suggestion = _suggest_transform(store).suggestions[0]

    chain = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=suggestion.suggestion_id,
        scope="transforms",
    )

    assert chain.success is True
    assert chain.scope == "transforms"
    assert chain.suggestion is not None
    assert chain.suggestion.suggestion_id == suggestion.suggestion_id
    assert len(chain.evidence_chunks) == 2


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
    assert _transform_row_count(store) == 0


def _suggest_transform(
    store: KnowledgeStore, *, field_name_pattern: str | None = None
):
    return suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="transforms",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
        target_id="ledger-core",
        direction="request",
        field_name_pattern=field_name_pattern,
    )


def _ingest_catalog_pair(
    store: KnowledgeStore,
    tmp_path: Path,
    *,
    source_rows: list[dict[str, str]],
    target_rows: list[dict[str, str]],
) -> None:
    source = _write_catalog_csv(tmp_path / f"source-{len(source_rows)}.csv", source_rows)
    target = _write_catalog_csv(tmp_path / f"target-{len(target_rows)}.csv", target_rows)
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


def _transform_row_count(store: KnowledgeStore) -> int:
    row = store.conn.execute(
        """
        SELECT COUNT(*) AS row_count
        FROM manifest_suggestions
        WHERE suggestion_type = 'transform'
        """
    ).fetchone()
    return int(row["row_count"])
