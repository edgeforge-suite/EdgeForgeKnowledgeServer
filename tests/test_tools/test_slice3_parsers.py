from pathlib import Path

import pytest

from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.field_catalog import read_field_catalog
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.read import read_document
from knowledge_server.tools.search import list_documents, search_documents


def test_ingest_sql_populates_field_catalog_and_multiple_documents(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/sample-schema.sql").resolve()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = ingest_document(
        store=store,
        allowed_roots=[fixture.parent],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="sql",
    )

    assert result.field_count == 7
    assert result.warnings
    docs = list_documents(store=store, project_id="project-a", doc_type="sql")
    assert sorted(doc.name for doc in docs.documents) == [
        "sample-schema.sql::accounts",
        "sample-schema.sql::users",
    ]
    catalog = read_field_catalog(store=store, project_id="project-a", entity="accounts")
    assert [field.name for field in catalog.fields] == [
        "account_id",
        "available_balance",
        "owner_id",
        "status",
    ]


def test_ingest_oracle_sql_with_leading_comments_populates_four_documents(
    tmp_path: Path,
) -> None:
    fixture = Path("tests/fixtures/oracle-legacy-payments-ddl.sql").resolve()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = ingest_document(
        store=store,
        allowed_roots=[fixture.parent],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="sql",
    )

    assert result.field_count > 0
    assert result.warnings == [
        (
            "Ingested 4 SQL entities from oracle-legacy-payments-ddl.sql; "
            "return value references the first stored document."
        )
    ]
    docs = list_documents(store=store, project_id="project-a", doc_type="sql")
    assert sorted(doc.name for doc in docs.documents) == [
        "oracle-legacy-payments-ddl.sql::ACCOUNT",
        "oracle-legacy-payments-ddl.sql::CUSTOMER",
        "oracle-legacy-payments-ddl.sql::PAYMENT_LIMIT",
        "oracle-legacy-payments-ddl.sql::PAYMENT_ORDER",
    ]
    account_catalog = read_field_catalog(store=store, project_id="project-a", entity="ACCOUNT")
    balance = next(field for field in account_catalog.fields if field.name == "BALANCE_MINOR")
    assert balance.type == "DECIMAL"
    assert balance.precision == 18
    assert balance.scale == 0
    assert "minor currency units" in (balance.description or "")


def test_ingest_excel_populates_field_catalog(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/data-dictionary.xlsx").resolve()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = ingest_document(
        store=store,
        allowed_roots=[fixture.parent],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="excel",
    )

    assert result.field_count == 3
    catalog = read_field_catalog(store=store, project_id="project-a", entity="Account")
    assert [field.name for field in catalog.fields] == ["account_id", "available_balance"]


def test_ingest_rejects_doc_type_and_extension_mismatch(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/data-dictionary.csv").resolve()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    with pytest.raises(ValueError, match="file extension mismatch"):
        ingest_document(
            store=store,
            allowed_roots=[fixture.parent],
            project_id="project-a",
            file_path=str(fixture),
            doc_type="markdown",
        )


def test_search_documents_applies_min_score_filter(tmp_path: Path) -> None:
    strong = tmp_path / "strong.md"
    weak = tmp_path / "weak.md"
    strong.write_text("# Strong\n\nbalance balance balance balance balance\n", encoding="utf-8")
    weak.write_text("# Weak\n\nbalance once\n", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    for source in [strong, weak]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(source),
            doc_type="markdown",
        )

    baseline = search_documents(store=store, project_id="project-a", query="balance", max_results=5)
    assert baseline.result_count >= 2
    threshold = (baseline.results[0].score + baseline.results[1].score) / 2

    filtered = search_documents(
        store=store,
        project_id="project-a",
        query="balance",
        max_results=5,
        min_score=threshold,
    )

    assert filtered.result_count == 1
    assert filtered.results[0].score == baseline.results[0].score


def test_search_documents_warns_on_all_punctuation_query(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/sample-brd.md").resolve()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest_document(
        store=store,
        allowed_roots=[fixture.parent],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="markdown",
    )

    result = search_documents(store=store, project_id="project-a", query="!!!")

    assert result.results == []
    assert result.result_count == 0
    assert result.warnings == ["Query contained no searchable tokens; returning empty results."]


def test_read_document_returns_structured_warning_for_missing_document(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = read_document(store=store, project_id="project-a", document_id="missing-doc")

    assert result.success is False
    assert result.text == ""
    assert result.warnings == ["document not found for project_id project-a: missing-doc"]


def test_read_field_catalog_returns_structured_warning_for_missing_source(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = read_field_catalog(store=store, project_id="project-a", source="missing-doc")

    assert result.success is False
    assert result.fields == []
    assert result.warnings == ["document not found for project_id project-a: missing-doc"]


def test_project_isolation_holds_for_sql_and_excel(tmp_path: Path) -> None:
    sql_fixture = Path("tests/fixtures/sample-schema.sql").resolve()
    xlsx_fixture = Path("tests/fixtures/data-dictionary.xlsx").resolve()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    ingest_document(
        store=store,
        allowed_roots=[sql_fixture.parent],
        project_id="project-a",
        file_path=str(sql_fixture),
        doc_type="sql",
    )
    ingest_document(
        store=store,
        allowed_roots=[xlsx_fixture.parent],
        project_id="project-a",
        file_path=str(xlsx_fixture),
        doc_type="excel",
    )

    assert search_documents(store=store, project_id="project-a", query="account").result_count > 0
    assert search_documents(store=store, project_id="project-b", query="account").result_count == 0
    assert list_documents(store=store, project_id="project-b", doc_type="sql").documents == []
    assert read_field_catalog(store=store, project_id="project-b", entity="accounts").fields == []
