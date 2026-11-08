from pathlib import Path

import pytest

from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.read import read_document
from knowledge_server.tools.search import list_documents, search_documents
from tests.helpers import make_empty_docx, make_test_docx, make_test_pdf


def test_ingest_pdf_populates_searchable_chunks(tmp_path: Path) -> None:
    fixture = make_test_pdf(
        tmp_path / "guide.pdf",
        [
            "Balance memo rules are documented here.",
            "Customer alerts appear on the second page.",
        ],
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="pdf",
    )

    assert result.section_count == 2
    search = search_documents(store=store, project_id="project-a", query="memo")
    assert search.result_count == 1
    assert search.results[0].citation.page == 1
    assert search.results[0].citation.section == "Page 1"


def test_ingest_docx_populates_searchable_chunks(tmp_path: Path) -> None:
    fixture = make_test_docx(
        tmp_path / "guide.docx",
        [
            ("Balance Rules", "Memo credits affect available balance."),
            ("Customer Rules", "Closed accounts cannot transact."),
        ],
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="docx",
    )

    assert result.section_count == 2
    search = search_documents(store=store, project_id="project-a", query="transact")
    assert search.result_count == 1
    assert search.results[0].citation.section == "Customer Rules"


def test_ingest_rejects_pdf_docx_extension_mismatch(tmp_path: Path) -> None:
    pdf_fixture = make_test_pdf(tmp_path / "guide.pdf", ["Balance rules page."])
    docx_fixture = make_test_docx(tmp_path / "guide.docx", [("Section One", "Docx body text.")])
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    with pytest.raises(ValueError, match="file extension mismatch"):
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(docx_fixture),
            doc_type="pdf",
        )

    with pytest.raises(ValueError, match="file extension mismatch"):
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(pdf_fixture),
            doc_type="docx",
        )


def test_ingest_rejects_pdf_without_extractable_text(tmp_path: Path) -> None:
    fixture = make_test_pdf(tmp_path / "blank.pdf", [""])
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    with pytest.raises(ValueError, match="no extractable text found"):
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(fixture),
            doc_type="pdf",
        )


def test_ingest_rejects_empty_docx(tmp_path: Path) -> None:
    fixture = make_empty_docx(tmp_path / "empty.docx")
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    with pytest.raises(ValueError, match="DOCX appears to be empty"):
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(fixture),
            doc_type="docx",
        )


def test_read_document_returns_page_based_pdf_citations(tmp_path: Path) -> None:
    fixture = make_test_pdf(
        tmp_path / "manual.pdf",
        [
            "First page guidance.",
            "Second page guidance.",
        ],
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    result = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="pdf",
    )

    content = read_document(store=store, project_id="project-a", document_id=result.document_id)

    assert "First page guidance." in content.text
    assert content.citations[0].page == 1
    assert content.citations[1].page == 2
    assert content.citations[0].section == "Page 1"


def test_read_document_returns_section_based_docx_citations(tmp_path: Path) -> None:
    fixture = make_test_docx(
        tmp_path / "manual.docx",
        [
            ("Section One", "Alpha section body."),
            ("Section Two", "Beta section body."),
        ],
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    result = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="docx",
    )

    content = read_document(
        store=store,
        project_id="project-a",
        document_id=result.document_id,
        section="Section Two",
    )

    assert "Beta section body." in content.text
    assert content.citations[0].section == "Section Two"


def test_project_isolation_holds_for_pdf_and_docx(tmp_path: Path) -> None:
    pdf_fixture = make_test_pdf(tmp_path / "guide.pdf", ["Balance rules page."])
    docx_fixture = make_test_docx(
        tmp_path / "guide.docx",
        [("Balance Rules", "Memo credits affect available balance.")],
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(pdf_fixture),
        doc_type="pdf",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(docx_fixture),
        doc_type="docx",
    )

    assert search_documents(store=store, project_id="project-a", query="balance").result_count > 0
    assert search_documents(store=store, project_id="project-b", query="balance").result_count == 0
    assert list_documents(store=store, project_id="project-b", doc_type="pdf").documents == []
    assert list_documents(store=store, project_id="project-b", doc_type="docx").documents == []
