from __future__ import annotations

import csv
from pathlib import Path

from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.delete import delete_document
from knowledge_server.tools.evidence_chain import (
    get_field_evidence_chain,
    get_suggestion_evidence_chain,
)
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.suggest import suggest_fields, suggest_manifest_candidates


def test_evidence_chain_returns_all_three_components(tmp_path: Path) -> None:
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

    result = get_field_evidence_chain(
        store=store,
        project_id="project-a",
        field_name="account_id",
    )

    assert result.suggestion is not None
    assert result.definitions
    assert result.evidence_chunks
    assert result.has_conflicts is False


def test_evidence_chain_sets_has_conflicts_true_when_type_disagrees(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    fixture_one = _write_dictionary_csv(
        tmp_path / "one.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "String identifier",
            }
        ],
    )
    fixture_two = _write_dictionary_csv(
        tmp_path / "two.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "integer",
                "length": "",
                "nullable": "false",
                "description": "Numeric identifier",
            }
        ],
    )

    for fixture in [fixture_one, fixture_two]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(fixture),
            doc_type="csv",
        )

    result = get_field_evidence_chain(
        store=store,
        project_id="project-a",
        field_name="account_id",
    )

    assert result.has_conflicts is True
    assert result.conflict_summary is not None


def test_evidence_chain_conflict_summary_dedupes_and_truncates_noise(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    duplicate_fixture = _write_dictionary_csv(
        tmp_path / "duplicate.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "String identifier",
            },
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "Repeated source row",
            },
        ],
    )
    long_type_fixture = _write_dictionary_csv(
        tmp_path / "long-type.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "very_long_legacy_identifier_type_name_" * 4,
                "length": "",
                "nullable": "false",
                "description": "Noisy legacy type label",
            }
        ],
    )

    for fixture in [duplicate_fixture, long_type_fixture]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(fixture),
            doc_type="csv",
        )

    result = get_field_evidence_chain(
        store=store,
        project_id="project-a",
        field_name="account_id",
        entity="Account",
    )

    assert result.conflict_summary is not None
    assert result.conflict_summary.count("duplicate.csv") == 1
    assert "..." in result.conflict_summary


def test_evidence_chain_source_count_deduplicates_documents(tmp_path: Path) -> None:
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

    result = get_field_evidence_chain(
        store=store,
        project_id="project-a",
        field_name="account_id",
    )

    assert result.source_count == 1


def test_evidence_chain_returns_empty_gracefully_for_unknown_field(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = get_field_evidence_chain(
        store=store,
        project_id="project-a",
        field_name="unknown_field",
    )

    assert result.suggestion is None
    assert result.definitions == []
    assert result.evidence_chunks == []
    assert result.source_count == 0
    assert result.warnings


def test_evidence_chain_respects_project_isolation(tmp_path: Path) -> None:
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

    result = get_field_evidence_chain(
        store=store,
        project_id="project-b",
        field_name="account_id",
    )

    assert result.suggestion is None
    assert result.definitions == []
    assert result.evidence_chunks == []
    assert result.source_count == 0


def test_evidence_chain_excludes_soft_deleted_documents(tmp_path: Path) -> None:
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

    ingest = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="csv",
    )
    delete_document(store=store, project_id="project-a", document_id=ingest.document_id)

    result = get_field_evidence_chain(
        store=store,
        project_id="project-a",
        field_name="account_id",
    )

    assert result.suggestion is None
    assert result.definitions == []
    assert result.evidence_chunks == []


def test_evidence_chain_entity_scoping(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    fixture = _write_dictionary_csv(
        tmp_path / "entities.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "Account identifier",
            },
            {
                "entity": "Loan",
                "field_name": "account_id",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "Linked account identifier",
            },
        ],
    )

    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="csv",
    )

    result = get_field_evidence_chain(
        store=store,
        project_id="project-a",
        field_name="account_id",
        entity="Account",
    )

    assert result.suggestion is not None
    assert result.suggestion.entity == "Account"
    assert all(definition.entity_name == "Account" for definition in result.definitions)


def _write_dictionary_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["entity", "field_name", "type", "length", "nullable", "description"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_evidence_chain_entity_scope_excludes_other_entity_chunks(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    account_fixture = _write_dictionary_csv(
        tmp_path / "account.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "Account identifier",
            }
        ],
    )
    loan_fixture = _write_dictionary_csv(
        tmp_path / "loan.csv",
        [
            {
                "entity": "Loan",
                "field_name": "account_id",
                "type": "integer",
                "length": "",
                "nullable": "false",
                "description": "Loan-linked account identifier",
            }
        ],
    )

    account_ingest = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(account_fixture),
        doc_type="csv",
    )
    loan_ingest = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(loan_fixture),
        doc_type="csv",
    )

    result = get_field_evidence_chain(
        store=store,
        project_id="project-a",
        field_name="account_id",
        entity="Account",
    )

    assert result.suggestion is not None
    assert result.suggestion.entity == "Account"
    assert all(definition.entity_name == "Account" for definition in result.definitions)
    assert result.evidence_chunks
    assert all(chunk.document_id == account_ingest.document_id for chunk in result.evidence_chunks)
    assert all(chunk.document_id != loan_ingest.document_id for chunk in result.evidence_chunks)
    assert result.has_conflicts is False


def test_evidence_chain_no_entity_returns_chunks_from_all_entities(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    account_fixture = _write_dictionary_csv(
        tmp_path / "account.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "Account identifier",
            }
        ],
    )
    loan_fixture = _write_dictionary_csv(
        tmp_path / "loan.csv",
        [
            {
                "entity": "Loan",
                "field_name": "account_id",
                "type": "integer",
                "length": "",
                "nullable": "false",
                "description": "Loan-linked account identifier",
            }
        ],
    )

    account_ingest = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(account_fixture),
        doc_type="csv",
    )
    loan_ingest = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(loan_fixture),
        doc_type="csv",
    )

    result = get_field_evidence_chain(
        store=store,
        project_id="project-a",
        field_name="account_id",
    )

    assert result.suggestion is not None
    assert result.evidence_chunks
    document_ids = {chunk.document_id for chunk in result.evidence_chunks}
    assert account_ingest.document_id in document_ids
    assert loan_ingest.document_id in document_ids


def test_evidence_chain_entity_scope_without_scoped_definitions_returns_no_chunks(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    loan_fixture = _write_dictionary_csv(
        tmp_path / "loan.csv",
        [
            {
                "entity": "Loan",
                "field_name": "account_id",
                "type": "integer",
                "length": "",
                "nullable": "false",
                "description": "Loan-linked account identifier",
            }
        ],
    )
    notes_fixture = tmp_path / "notes.md"
    notes_fixture.write_text(
        "# Account Notes\n\nAccount onboarding guidance.\n",
        encoding="utf-8",
    )

    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(loan_fixture),
        doc_type="csv",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(notes_fixture),
        doc_type="markdown",
    )

    result = get_field_evidence_chain(
        store=store,
        project_id="project-a",
        field_name="unknown_field",
        entity="Account",
    )

    assert result.suggestion is None
    assert result.definitions == []
    assert result.evidence_chunks == []
    assert result.source_count == 0


def test_suggestion_evidence_chain_fields_scope_matches_field_chain(tmp_path: Path) -> None:
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
    suggestion = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="account_id",
    ).suggestions[0]

    generic = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=suggestion.suggestion_id,
        scope="fields",
    )
    legacy = get_field_evidence_chain(
        store=store,
        project_id="project-a",
        field_name="account_id",
        entity="Account",
    )

    assert generic.tool_name == "get_suggestion_evidence_chain"
    assert generic.scope == "fields"
    assert generic.suggestion_id == suggestion.suggestion_id
    assert generic.suggestion is not None
    assert legacy.suggestion is not None
    assert generic.suggestion.suggestion_id == legacy.suggestion.suggestion_id
    assert generic.definitions == legacy.definitions
    assert generic.evidence_chunks == legacy.evidence_chunks
    assert generic.source_count == legacy.source_count


def test_suggestion_evidence_chain_unknown_id_returns_empty_warning(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id="missing-suggestion",
        scope="fields",
    )

    assert result.success is False
    assert result.scope == "fields"
    assert result.suggestion is None
    assert result.definitions == []
    assert result.evidence_chunks == []
    assert result.warnings


def test_suggestion_evidence_chain_unsupported_scope_returns_warning(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id="any-suggestion",
        scope="not_a_scope",
    )

    assert result.success is False
    assert result.scope == "not_a_scope"
    assert result.unsupported_scope is True
    assert result.evidence_chunks == []
    assert "Unsupported suggestion scope" in result.warnings[0]


def test_suggestion_evidence_chain_conflict_resolution_scope(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_conflict_field_catalog_pair(store, tmp_path)
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern="customerId",
    ).suggestions[0]

    result = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=suggestion.suggestion_id,
        scope="conflict_resolution",
    )

    assert result.success is True
    assert result.scope == "conflict_resolution"
    assert result.suggestion is not None
    assert result.suggestion.suggestion_type == "conflict_resolution"
    assert len(result.evidence_chunks) == 2


def test_suggestion_evidence_chain_conflict_resolution_wrong_scope_warns(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_conflict_field_catalog_pair(store, tmp_path)
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="conflict_resolution",
        field_name_pattern="customerId",
    ).suggestions[0]

    result = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=suggestion.suggestion_id,
        scope="rules",
    )

    assert result.success is False
    assert result.scope == "rules"
    assert result.evidence_chunks == []
    assert "has type 'conflict_resolution'" in result.warnings[0]


def test_suggestion_evidence_chain_portfolio_reuse_scope(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    matched_document_id = _ingest_portfolio_docs(store, tmp_path)
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="portfolio_reuse",
        field_name_pattern="balance",
    ).suggestions[0]

    result = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=suggestion.suggestion_id,
        scope="portfolio_reuse",
    )

    assert result.success is True
    assert result.scope == "portfolio_reuse"
    assert result.suggestion is not None
    assert result.suggestion.suggestion_type == "portfolio_reuse"
    assert len(result.evidence_chunks) == 1
    assert result.evidence_chunks[0].document_id == matched_document_id


def test_suggestion_evidence_chain_portfolio_reuse_wrong_scope_warns(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_portfolio_docs(store, tmp_path)
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="portfolio_reuse",
        field_name_pattern="balance",
    ).suggestions[0]

    result = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=suggestion.suggestion_id,
        scope="rules",
    )

    assert result.success is False
    assert result.scope == "rules"
    assert result.evidence_chunks == []
    assert "has type 'portfolio_reuse'" in result.warnings[0]


def test_suggestion_evidence_chain_transform_scope(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_transform_catalog_pair(store, tmp_path)
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="transforms",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
        target_id="ledger-core",
        direction="request",
    ).suggestions[0]

    result = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=suggestion.suggestion_id,
        scope="transforms",
    )

    assert result.success is True
    assert result.scope == "transforms"
    assert result.suggestion is not None
    assert result.suggestion.suggestion_type == "transform"
    assert result.suggestion.payload["source"] == "$.paymentId"
    assert result.suggestion.payload["target"] == "$.payment_id"
    assert len(result.evidence_chunks) == 2


def test_suggestion_evidence_chain_transform_wrong_scope_warns(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_transform_catalog_pair(store, tmp_path)
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="transforms",
        route_name="payment_router",
        source_entity="RORequest",
        target_entity="D1Request",
        target_id="ledger-core",
        direction="request",
    ).suggestions[0]

    result = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=suggestion.suggestion_id,
        scope="mappings",
    )

    assert result.success is False
    assert result.scope == "mappings"
    assert result.evidence_chunks == []
    assert "has type 'transform'" in result.warnings[0]


def _ingest_conflict_docs(store: KnowledgeStore, tmp_path: Path) -> None:
    first = tmp_path / "balance-a.md"
    second = tmp_path / "balance-b.md"
    first.write_text("# Balance Rules\n\nThe balance includes memo credits.\n", encoding="utf-8")
    second.write_text("# Balance Exceptions\n\nThe balance excludes memo credits.\n", encoding="utf-8")
    for source in [first, second]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(source),
            doc_type="markdown",
        )


def _ingest_conflict_field_catalog_pair(store: KnowledgeStore, tmp_path: Path) -> None:
    ddl_like = _write_dictionary_csv(
        tmp_path / "legacy-ddl.csv",
        [
            {
                "entity": "CUSTOMER",
                "field_name": "CUSTOMER_ID",
                "type": "VARCHAR",
                "length": "36",
                "nullable": "false",
                "description": "Customer identifier",
            }
        ],
    )
    catalog = _write_dictionary_csv(
        tmp_path / "catalog.csv",
        [
            {
                "entity": "Customer",
                "field_name": "customerId",
                "type": "string",
                "length": "",
                "nullable": "false",
                "description": "Customer identifier",
            }
        ],
    )
    for fixture in [ddl_like, catalog]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(fixture),
            doc_type="csv",
        )


def _ingest_portfolio_docs(store: KnowledgeStore, tmp_path: Path) -> str:
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
    matched = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-b",
        file_path=str(source),
        doc_type="markdown",
    )
    return matched.document_id


def _ingest_transform_catalog_pair(store: KnowledgeStore, tmp_path: Path) -> None:
    source = _write_dictionary_csv(
        tmp_path / "transform-source.csv",
        [
            {
                "entity": "RORequest",
                "field_name": "paymentId",
                "type": "string",
                "length": "",
                "nullable": "true",
                "description": "Payment identifier from router source",
            }
        ],
    )
    target = _write_dictionary_csv(
        tmp_path / "transform-target.csv",
        [
            {
                "entity": "D1Request",
                "field_name": "payment_id",
                "type": "string",
                "length": "",
                "nullable": "true",
                "description": "Payment identifier on router target",
            }
        ],
    )
    for fixture in [source, target]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(fixture),
            doc_type="csv",
        )
