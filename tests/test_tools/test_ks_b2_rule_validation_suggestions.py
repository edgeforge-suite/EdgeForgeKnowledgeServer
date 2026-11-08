from __future__ import annotations

import csv
from pathlib import Path

from knowledge_server.models import SuggestionDecision
from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.decisions import submit_suggestion_decisions
from knowledge_server.tools.evidence_chain import get_suggestion_evidence_chain
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.suggest import suggest_manifest_candidates


def test_validations_scope_persists_catalog_constraints_with_stable_ids(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    fixture = _write_catalog_csv(
        tmp_path / "account.csv",
        [
            {
                "entity": "Account",
                "field_name": "sortCode",
                "type": "string",
                "length": "6",
                "precision": "",
                "scale": "",
                "nullable": "false",
                "description": "Branch sort code",
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
        scope="validations",
        entity="Account",
        field_name_pattern="sortCode",
    )
    second = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="validations",
        entity="Account",
        field_name_pattern="sortCode",
    )

    assert first.success is True
    assert first.scope == "validations"
    validation_types = {suggestion.payload["validation_type"] for suggestion in first.suggestions}
    assert {"not_null", "max_length"}.issubset(validation_types)
    assert [suggestion.suggestion_id for suggestion in first.suggestions] == [
        suggestion.suggestion_id for suggestion in second.suggestions
    ]
    assert all(suggestion.suggestion_type == "validation" for suggestion in first.suggestions)
    assert all(suggestion.status == "pending" for suggestion in first.suggestions)
    row = store.conn.execute(
        """
        SELECT COUNT(*) AS row_count
        FROM manifest_suggestions
        WHERE suggestion_type = 'validation'
        """
    ).fetchone()
    assert row["row_count"] == len(first.suggestions)


def test_validations_scope_extracts_explicit_pattern_evidence(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    catalog = _write_catalog_csv(
        tmp_path / "account.csv",
        [
            {
                "entity": "Account",
                "field_name": "sortCode",
                "type": "string",
                "length": "",
                "precision": "",
                "scale": "",
                "nullable": "true",
                "description": "Branch sort code",
            }
        ],
    )
    notes = tmp_path / "rules.md"
    notes.write_text(
        "# Account Rules\n\nAccount sortCode format must be NN-NN-NN.\n",
        encoding="utf-8",
    )
    for path, doc_type in [(catalog, "csv"), (notes, "markdown")]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(path),
            doc_type=doc_type,
        )

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="validations",
        entity="Account",
        field_name_pattern="sortCode",
    )

    pattern = next(
        suggestion
        for suggestion in result.suggestions
        if suggestion.payload["validation_type"] == "pattern"
    )
    assert pattern.payload["pattern"] == r"^\d{2}-\d{2}-\d{2}$"
    assert pattern.citations
    assert pattern.target_step == "step3"


def test_rules_scope_extracts_allowed_values_and_preserves_decision_status(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    catalog = _write_catalog_csv(
        tmp_path / "account.csv",
        [
            {
                "entity": "Account",
                "field_name": "status",
                "type": "string",
                "length": "",
                "precision": "",
                "scale": "",
                "nullable": "false",
                "description": "Account status",
            }
        ],
    )
    notes = tmp_path / "rules.md"
    notes.write_text(
        "# Account Rules\n\nAccount status must be one of: ACTIVE, SUSPENDED, CLOSED.\n",
        encoding="utf-8",
    )
    for path, doc_type in [(catalog, "csv"), (notes, "markdown")]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(path),
            doc_type=doc_type,
        )

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="rules",
        entity="Account",
        field_name_pattern="status",
    )
    suggestion = result.suggestions[0]

    assert suggestion.suggestion_type == "rule"
    assert suggestion.target_step == "step6"
    assert suggestion.payload["rule_type"] == "allowed_values"
    assert suggestion.payload["constraint"]["values"] == ["ACTIVE", "SUSPENDED", "CLOSED"]
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="accepted")],
    )
    refreshed = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="rules",
        entity="Account",
        field_name_pattern="status",
    )
    assert refreshed.suggestions[0].suggestion_id == suggestion.suggestion_id
    assert refreshed.suggestions[0].status == "accepted"


def test_cross_entity_rules_scope_extracts_supported_state_check(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    catalog = _write_catalog_csv(
        tmp_path / "entities.csv",
        [
            {
                "entity": "Payment",
                "field_name": "accountId",
                "type": "string",
                "length": "",
                "precision": "",
                "scale": "",
                "nullable": "false",
                "description": "Referenced account",
            },
            {
                "entity": "Account",
                "field_name": "id",
                "type": "string",
                "length": "",
                "precision": "",
                "scale": "",
                "nullable": "false",
                "description": "Account id",
            },
            {
                "entity": "Account",
                "field_name": "status",
                "type": "string",
                "length": "",
                "precision": "",
                "scale": "",
                "nullable": "false",
                "description": "Account status",
            },
        ],
    )
    notes = tmp_path / "relationships.md"
    notes.write_text(
        "# Payment Rules\n\n"
        "Payment.accountId references Account.id. Account.status must be ACTIVE.\n",
        encoding="utf-8",
    )
    for path, doc_type in [(catalog, "csv"), (notes, "markdown")]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(path),
            doc_type=doc_type,
        )

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="cross_entity_rules",
        entity="Payment",
    )
    suggestion = result.suggestions[0]

    assert suggestion.suggestion_type == "cross_entity_rule"
    assert suggestion.target_step == "step6"
    assert suggestion.payload["rule_type"] == "cross-entity-field-check"
    assert suggestion.payload["source_entity"] == "Payment"
    assert suggestion.payload["source_field"] == "accountId"
    assert suggestion.payload["target_entity"] == "Account"
    assert suggestion.payload["target_field"] == "status"
    assert suggestion.payload["expected_value"] == "ACTIVE"
    assert suggestion.warnings


def test_cross_entity_rules_skip_unknown_target_state_field(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    catalog = _write_catalog_csv(
        tmp_path / "entities.csv",
        [
            {
                "entity": "Payment",
                "field_name": "accountId",
                "type": "string",
                "length": "",
                "precision": "",
                "scale": "",
                "nullable": "false",
                "description": "Referenced account",
            },
            {
                "entity": "Account",
                "field_name": "id",
                "type": "string",
                "length": "",
                "precision": "",
                "scale": "",
                "nullable": "false",
                "description": "Account id",
            },
        ],
    )
    notes = tmp_path / "relationships.md"
    notes.write_text(
        "# Payment Rules\n\n"
        "Payment.accountId references Account.id. Account.state must be ACTIVE.\n",
        encoding="utf-8",
    )
    for path, doc_type in [(catalog, "csv"), (notes, "markdown")]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(path),
            doc_type=doc_type,
        )

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="cross_entity_rules",
        entity="Payment",
    )

    assert result.suggestions == []
    assert any(
        "Account.state is not present in field_catalog" in warning
        for warning in result.warnings
    )
    row = store.conn.execute(
        """
        SELECT COUNT(*) AS row_count
        FROM manifest_suggestions
        WHERE suggestion_type = 'cross_entity_rule'
        """
    ).fetchone()
    assert row["row_count"] == 0


def test_generic_evidence_chain_returns_manifest_suggestion_evidence_for_wave1_types(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_wave1_fixture(store, tmp_path)

    for scope in ["validations", "rules", "cross_entity_rules"]:
        suggestions = suggest_manifest_candidates(
            store=store,
            project_id="project-a",
            scope=scope,
        )
        suggestion = suggestions.suggestions[0]

        chain = get_suggestion_evidence_chain(
            store=store,
            project_id="project-a",
            suggestion_id=suggestion.suggestion_id,
            scope=scope,
        )

        assert chain.success is True
        assert chain.scope == scope
        assert chain.suggestion is not None
        assert chain.suggestion.suggestion_id == suggestion.suggestion_id
        assert chain.evidence_chunks
        assert chain.source_count >= 1


def test_submit_suggestion_decisions_validates_wave1_edited_payloads(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_wave1_fixture(store, tmp_path)
    by_scope = {
        scope: suggest_manifest_candidates(
            store=store,
            project_id="project-a",
            scope=scope,
        ).suggestions[0]
        for scope in ["validations", "rules", "cross_entity_rules"]
    }

    valid_result = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=by_scope["validations"].suggestion_id,
                status="edited",
                edited_payload={
                    "entity": "Account",
                    "field": "sortCode",
                    "validation_type": "pattern",
                    "pattern": r"^\d{2}-\d{2}-\d{2}$",
                },
            ),
            SuggestionDecision(
                suggestion_id=by_scope["rules"].suggestion_id,
                status="edited",
                edited_payload={
                    "entity": "Account",
                    "rule_id": "account-status-allowed-values",
                    "rule_type": "allowed_values",
                    "field": "status",
                    "constraint": {"values": ["ACTIVE", "SUSPENDED", "CLOSED"]},
                    "source_excerpt": "Account status must be one of: ACTIVE, SUSPENDED, CLOSED.",
                },
            ),
            SuggestionDecision(
                suggestion_id=by_scope["cross_entity_rules"].suggestion_id,
                status="edited",
                edited_payload={
                    "rule_id": "payment-accountid-account-status",
                    "rule_type": "cross-entity-field-check",
                    "source_entity": "Payment",
                    "source_field": "accountId",
                    "target_entity": "Account",
                    "target_field": "status",
                    "operator": "eq",
                    "expected_value": "ACTIVE",
                    "description": "Account.status must equal ACTIVE.",
                },
            ),
        ],
    )

    assert valid_result.success is True
    assert all(outcome.success for outcome in valid_result.outcomes)
    invalid_result = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=by_scope["rules"].suggestion_id,
                status="edited",
                edited_payload={"entity": "Account"},
            )
        ],
    )
    assert invalid_result.success is False
    assert invalid_result.outcomes[0].success is False
    assert "edited_payload.rule_id" in (invalid_result.outcomes[0].error or "")


def test_submit_suggestion_decisions_rejects_incomplete_cross_entity_payloads(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_wave1_fixture(store, tmp_path)
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="cross_entity_rules",
    ).suggestions[0]

    result = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={
                    "rule_id": "payment-accountid-account-status",
                    "rule_type": "cross-entity-field-check",
                    "source_entity": "Payment",
                    "source_field": "accountId",
                    "target_entity": "Account",
                    "target_field": "status",
                    "operator": "eq",
                    "description": "Account.status must equal ACTIVE.",
                },
            ),
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={
                    "rule_id": "payment-accountid-account-status",
                    "rule_type": "cross-entity-field-in",
                    "source_entity": "Payment",
                    "source_field": "accountId",
                    "target_entity": "Account",
                    "target_field": "status",
                    "operator": "in",
                    "description": "Account.status must be allowed.",
                },
            ),
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={
                    "rule_id": "payment-accountid-account-balance",
                    "rule_type": "cross-entity-field-compare",
                    "source_entity": "Payment",
                    "source_field": "accountId",
                    "target_entity": "Account",
                    "target_field": "availableBalance",
                    "operator": "lte",
                    "description": "Payment.amount must be lte Account.availableBalance.",
                },
            ),
        ],
    )

    assert result.success is False
    assert result.outcome_count == 3
    assert all(not outcome.success for outcome in result.outcomes)
    errors = [outcome.error or "" for outcome in result.outcomes]
    assert any("expected_value" in error for error in errors)
    assert any("allowed_values" in error for error in errors)
    assert any("compare_source_field" in error for error in errors)


def test_unsupported_scope_still_does_not_persist_fake_suggestions(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="not_a_scope",
    )

    assert result.success is False
    assert result.unsupported_scope is True
    assert result.suggestions == []
    row = store.conn.execute(
        "SELECT COUNT(*) AS row_count FROM manifest_suggestions"
    ).fetchone()
    assert row["row_count"] == 0


def _ingest_wave1_fixture(store: KnowledgeStore, tmp_path: Path) -> None:
    catalog = _write_catalog_csv(
        tmp_path / "wave1.csv",
        [
            {
                "entity": "Account",
                "field_name": "sortCode",
                "type": "string",
                "length": "6",
                "precision": "",
                "scale": "",
                "nullable": "false",
                "description": "Branch sort code",
            },
            {
                "entity": "Account",
                "field_name": "status",
                "type": "string",
                "length": "",
                "precision": "",
                "scale": "",
                "nullable": "false",
                "description": "Account status",
            },
            {
                "entity": "Payment",
                "field_name": "accountId",
                "type": "string",
                "length": "",
                "precision": "",
                "scale": "",
                "nullable": "false",
                "description": "Referenced account",
            },
            {
                "entity": "Account",
                "field_name": "id",
                "type": "string",
                "length": "",
                "precision": "",
                "scale": "",
                "nullable": "false",
                "description": "Account id",
            },
        ],
    )
    notes = tmp_path / "wave1.md"
    notes.write_text(
        "# Rules\n\n"
        "Account sortCode format must be NN-NN-NN.\n"
        "Account status must be one of: ACTIVE, SUSPENDED, CLOSED.\n"
        "Payment.accountId references Account.id. Account.status must be ACTIVE.\n",
        encoding="utf-8",
    )
    for path, doc_type in [(catalog, "csv"), (notes, "markdown")]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(path),
            doc_type=doc_type,
        )


def _write_catalog_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "entity",
                "field_name",
                "type",
                "length",
                "precision",
                "scale",
                "nullable",
                "description",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path
