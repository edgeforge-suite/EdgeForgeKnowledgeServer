from pathlib import Path

import pytest

from knowledge_server.safety import DEFAULT_MAX_FILE_BYTES, resolve_allowed_path
from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.field_catalog import read_field_catalog
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.read import read_document
from knowledge_server.tools.search import list_documents, search_documents


def test_allowed_root_enforcement_rejects_outside_path(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside.md"
    allowed.mkdir()
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError, match="allowed root"):
        resolve_allowed_path(str(outside), [allowed.resolve()])


def test_markdown_ingest_search_read_and_citations(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/sample-brd.md").resolve()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = ingest_document(
        store=store,
        allowed_roots=[fixture.parent],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="markdown",
        tags=["brd"],
    )

    docs = list_documents(store=store, project_id="project-a")
    assert len(docs.documents) == 1
    assert docs.documents[0].document_id == result.document_id

    search = search_documents(
        store=store,
        project_id="project-a",
        query="balance",
        max_results=5,
    )
    assert search.results
    assert search.results[0].citation.chunk_id
    assert search.results[0].citation.content_hash
    assert search.results[0].citation.parser_version == "markdown-v1"

    content = read_document(
        store=store,
        project_id="project-a",
        document_id=result.document_id,
        section="Balance Rules",
    )
    assert "memo credits" in content.text
    assert content.citations[0].section == "Balance Rules"


def test_project_id_isolation(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/sample-brd.md").resolve()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    ingest_document(
        store=store,
        allowed_roots=[fixture.parent],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="markdown",
    )

    assert search_documents(store=store, project_id="project-a", query="balance").results
    assert search_documents(store=store, project_id="project-b", query="balance").results == []
    assert list_documents(store=store, project_id="project-b").documents == []


def test_list_documents_filters_by_tags_subset(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/sample-brd.md").resolve()
    notes = tmp_path / "notes.md"
    notes.write_text("# Notes\n\nInternal implementation notes.\n", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    ingest_document(
        store=store,
        allowed_roots=[fixture.parent],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="markdown",
        tags=["brd", "payments"],
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(notes),
        doc_type="markdown",
        tags=["notes"],
    )

    filtered = list_documents(store=store, project_id="project-a", tags=["brd"])
    assert len(filtered.documents) == 1
    assert filtered.documents[0].tags == ["brd", "payments"]

    subset = list_documents(store=store, project_id="project-a", tags=["brd", "payments"])
    assert len(subset.documents) == 1

    assert list_documents(store=store, project_id="project-a", tags=["missing"]).documents == []


def test_csv_ingest_populates_field_catalog(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/data-dictionary.csv").resolve()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = ingest_document(
        store=store,
        allowed_roots=[fixture.parent],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="csv",
        description="Account fields",
    )

    assert result.field_count == 3
    catalog = read_field_catalog(store=store, project_id="project-a", entity="Account")
    assert [field.name for field in catalog.fields] == ["account_id", "available_balance"]
    assert catalog.fields[0].source_document == result.document_id
    assert catalog.fields[0].source_location == "row 2"


def test_search_normalizes_punctuated_queries(tmp_path: Path) -> None:
    """FTS special chars and natural-language questions must not raise errors."""
    fixture = Path("tests/fixtures/sample-brd.md").resolve()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest_document(
        store=store,
        allowed_roots=[fixture.parent],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="markdown",
    )

    # These queries previously raised sqlite3.OperationalError.
    for query in ["balance?", "what is balance?", "account:balance"]:
        result = search_documents(store=store, project_id="project-a", query=query)
        assert result.results, f"expected results for query {query!r}"


def test_doc_type_filter_applied_in_sql(tmp_path: Path) -> None:
    """doc_types=["csv"] must return CSV matches even when Markdown matches exist."""
    md_fixture = Path("tests/fixtures/sample-brd.md").resolve()
    csv_fixture = Path("tests/fixtures/data-dictionary.csv").resolve()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest_document(
        store=store,
        allowed_roots=[md_fixture.parent],
        project_id="project-a",
        file_path=str(md_fixture),
        doc_type="markdown",
    )
    ingest_document(
        store=store,
        allowed_roots=[csv_fixture.parent],
        project_id="project-a",
        file_path=str(csv_fixture),
        doc_type="csv",
    )

    # "account" appears in both; filtering to csv must still return csv results.
    result = search_documents(
        store=store,
        project_id="project-a",
        query="account",
        doc_types=["csv"],
        max_results=5,
    )
    assert result.results
    assert all(r.citation.document_id for r in result.results)
    md_result = search_documents(
        store=store,
        project_id="project-a",
        query="account",
        doc_types=["markdown"],
        max_results=1,
    )
    assert result.results[0].document_id != md_result.results[0].document_id


def test_reingest_replaces_stale_document(tmp_path: Path) -> None:
    """Re-ingesting an edited file must replace the old document, not stack a duplicate."""
    source = tmp_path / "notes.md"
    source.write_text("# Archived Section\n\nOriginal archived content.\n", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(source),
        doc_type="markdown",
    )

    # Verify old content is searchable (unique term: "archived").
    assert search_documents(store=store, project_id="project-a", query="archived").results

    # Edit the file and re-ingest.
    source.write_text("# Revised Section\n\nUpdated revised content.\n", encoding="utf-8")
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(source),
        doc_type="markdown",
    )

    # Old-only term must no longer appear.
    assert not search_documents(store=store, project_id="project-a", query="archived").results
    # New-only term must appear.
    assert search_documents(store=store, project_id="project-a", query="revised").results
    # Only one document for the project.
    docs = list_documents(store=store, project_id="project-a")
    assert len(docs.documents) == 1


def test_ingest_rejects_files_over_max_size(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.md"
    oversized.touch()
    with oversized.open("r+b") as handle:
        handle.truncate(DEFAULT_MAX_FILE_BYTES + 1)
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    with pytest.raises(ValueError, match="maximum allowed size"):
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(oversized),
            doc_type="markdown",
        )
