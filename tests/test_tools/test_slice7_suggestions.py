from __future__ import annotations

import csv
import time
from pathlib import Path

from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.compare import compare_field_definitions
from knowledge_server.tools.delete import delete_document
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.suggest import suggest_fields


def test_suggest_fields_returns_consistent_suggestion_with_evidence(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    csv_fixture = Path("tests/fixtures/data-dictionary.csv").resolve()
    xlsx_fixture = Path("tests/fixtures/data-dictionary.xlsx").resolve()

    ingest_document(
        store=store,
        allowed_roots=[csv_fixture.parent],
        project_id="project-a",
        file_path=str(csv_fixture),
        doc_type="csv",
    )
    ingest_document(
        store=store,
        allowed_roots=[xlsx_fixture.parent],
        project_id="project-a",
        file_path=str(xlsx_fixture),
        doc_type="excel",
    )

    result = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="account_id",
        max_suggestions=10,
    )

    assert result.suggestion_count == len(result.suggestions)
    suggestion = result.suggestions[0]
    assert suggestion.field_name == "account_id"
    assert suggestion.suggestion_id
    assert suggestion.status == "pending"
    assert suggestion.consistency_score == 1.0
    assert suggestion.source_count == 2
    assert suggestion.conflict_hint is None
    assert len(suggestion.evidence) == 2
    assert "account_id" in suggestion.manifest_path_hint


def test_suggest_fields_surfaces_type_conflicts_and_entity_path_hints(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    csv_fixture = Path("tests/fixtures/data-dictionary.csv").resolve()
    conflict_fixture = _write_dictionary_csv(
        tmp_path / "conflict.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "integer",
                "length": "",
                "nullable": "false",
                "description": "Account identifier from downstream core",
            }
        ],
    )

    ingest_document(
        store=store,
        allowed_roots=[csv_fixture.parent],
        project_id="project-a",
        file_path=str(csv_fixture),
        doc_type="csv",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(conflict_fixture),
        doc_type="csv",
    )

    result = suggest_fields(
        store=store,
        project_id="project-a",
        entity="Account",
        field_name_pattern="account_id",
    )

    suggestion = result.suggestions[0]
    assert suggestion.consistency_score < 1.0
    assert suggestion.conflict_hint
    assert "Type conflict" in suggestion.conflict_hint
    assert "Account" in suggestion.manifest_path_hint


def test_suggest_fields_supports_pattern_filter_min_sources_limit_and_sorting(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    fixture_one = _write_dictionary_csv(
        tmp_path / "one.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_code",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "Alpha account code",
            },
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "Primary account identifier",
            },
            {
                "entity": "Account",
                "field_name": "account_status",
                "type": "string",
                "length": "20",
                "nullable": "true",
                "description": "Status from source one",
            },
        ],
    )
    fixture_two = _write_dictionary_csv(
        tmp_path / "two.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_code",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "Alpha account code duplicate",
            },
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "Primary account identifier duplicate",
            },
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

    result = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="account",
        min_source_count=2,
        max_suggestions=2,
    )

    assert [item.field_name for item in result.suggestions] == ["account_code", "account_id"]
    assert all(item.source_count >= 2 for item in result.suggestions)
    assert result.suggestion_count == 2


def test_suggest_fields_keeps_same_field_name_separate_across_entities(tmp_path: Path) -> None:
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

    result = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="account_id",
    )

    assert result.suggestion_count == 2
    assert [(item.entity, item.manifest_path_hint) for item in result.suggestions] == [
        ("Account", "Account.fields[name='account_id']"),
        ("Loan", "Loan.fields[name='account_id']"),
    ]
    assert all(item.source_count == 1 for item in result.suggestions)


def test_suggest_fields_excludes_soft_deleted_documents_and_preserves_project_isolation(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    kept = _write_dictionary_csv(
        tmp_path / "kept.csv",
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
    deleted = _write_dictionary_csv(
        tmp_path / "deleted.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "integer",
                "length": "",
                "nullable": "true",
                "description": "Deleted source should disappear",
            }
        ],
    )
    other_project = _write_dictionary_csv(
        tmp_path / "other.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "Project B definition",
            }
        ],
    )

    kept_result = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(kept),
        doc_type="csv",
    )
    deleted_result = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(deleted),
        doc_type="csv",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-b",
        file_path=str(other_project),
        doc_type="csv",
    )
    delete_document(store=store, project_id="project-a", document_id=deleted_result.document_id)

    project_a = suggest_fields(store=store, project_id="project-a", field_name_pattern="account_id")
    project_b = suggest_fields(store=store, project_id="project-b", field_name_pattern="account_id")

    assert project_a.suggestions[0].source_count == 1
    assert project_a.suggestions[0].evidence[0].document_id == kept_result.document_id
    assert project_b.suggestions[0].source_count == 1
    assert project_b.suggestions[0].evidence[0].description == "Project B definition"


def test_suggest_fields_warns_when_project_has_no_catalog_entries(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = suggest_fields(store=store, project_id="project-a", entity="Account")

    assert result.suggestions == []
    assert result.warnings == ["No field catalog entries found for project 'project-a' and entity 'Account'."]


def test_compare_field_definitions_reports_identical_sources_in_ingest_order(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    csv_fixture = Path("tests/fixtures/data-dictionary.csv").resolve()
    xlsx_fixture = Path("tests/fixtures/data-dictionary.xlsx").resolve()

    first = ingest_document(
        store=store,
        allowed_roots=[csv_fixture.parent],
        project_id="project-a",
        file_path=str(csv_fixture),
        doc_type="csv",
    )
    time.sleep(0.01)
    second = ingest_document(
        store=store,
        allowed_roots=[xlsx_fixture.parent],
        project_id="project-a",
        file_path=str(xlsx_fixture),
        doc_type="excel",
    )

    result = compare_field_definitions(store=store, project_id="project-a", field_name="account_id")

    assert result.definition_count == 2
    assert result.has_conflicts is False
    assert result.conflict_summary is None
    assert [item.document_id for item in result.definitions] == [first.document_id, second.document_id]


def test_compare_field_definitions_reports_type_and_nullable_conflicts(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    base = _write_dictionary_csv(
        tmp_path / "base.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "Primary account identifier",
            },
            {
                "entity": "Account",
                "field_name": "account_status",
                "type": "string",
                "length": "20",
                "nullable": "false",
                "description": "Active status",
            },
        ],
    )
    conflict = _write_dictionary_csv(
        tmp_path / "conflict.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "integer",
                "length": "",
                "nullable": "false",
                "description": "Numeric id",
            },
            {
                "entity": "Account",
                "field_name": "account_status",
                "type": "string",
                "length": "20",
                "nullable": "true",
                "description": "Nullable in a later spec",
            },
        ],
    )

    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(base),
        doc_type="csv",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(conflict),
        doc_type="csv",
    )

    type_result = compare_field_definitions(
        store=store,
        project_id="project-a",
        field_name="account_id",
    )
    nullable_result = compare_field_definitions(
        store=store,
        project_id="project-a",
        field_name="account_status",
    )

    assert type_result.has_conflicts is True
    assert "Type conflict" in (type_result.conflict_summary or "")
    assert nullable_result.has_conflicts is True
    assert "Nullable conflict" in (nullable_result.conflict_summary or "")


def test_compare_field_definitions_handles_missing_entity_filters_soft_delete_case_and_project_isolation(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    csv_fixture = Path("tests/fixtures/data-dictionary.csv").resolve()
    deleted_fixture = _write_dictionary_csv(
        tmp_path / "deleted.csv",
        [
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "integer",
                "length": "",
                "nullable": "false",
                "description": "Deleted source",
            }
        ],
    )
    other_entity = _write_dictionary_csv(
        tmp_path / "loan.csv",
        [
            {
                "entity": "Loan",
                "field_name": "account_id",
                "type": "string",
                "length": "12",
                "nullable": "false",
                "description": "Loan account id",
            }
        ],
    )

    ingest_document(
        store=store,
        allowed_roots=[csv_fixture.parent],
        project_id="project-a",
        file_path=str(csv_fixture),
        doc_type="csv",
    )
    deleted = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(deleted_fixture),
        doc_type="csv",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(other_entity),
        doc_type="csv",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-b",
        file_path=str(other_entity),
        doc_type="csv",
    )
    ingest_document(
        store=store,
        allowed_roots=[csv_fixture.parent],
        project_id="project-b",
        file_path=str(csv_fixture),
        doc_type="csv",
    )
    delete_document(store=store, project_id="project-a", document_id=deleted.document_id)

    missing = compare_field_definitions(store=store, project_id="project-a", field_name="missing_field")
    filtered = compare_field_definitions(
        store=store,
        project_id="project-a",
        field_name="Account_ID",
        entity="Account",
    )
    isolated = compare_field_definitions(
        store=store,
        project_id="project-b",
        field_name="account_id",
        entity="Account",
    )

    assert missing.definition_count == 0
    assert missing.warnings == ["No definitions found for field 'missing_field' in project 'project-a'."]
    assert filtered.definition_count == 1
    assert filtered.definitions[0].entity_name == "Account"
    assert isolated.definition_count == 1
    assert isolated.definitions[0].document_name == "data-dictionary.csv"


def _write_dictionary_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["entity", "field_name", "type", "length", "nullable", "description"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path
