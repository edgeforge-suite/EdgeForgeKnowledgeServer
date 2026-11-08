from pathlib import Path

import pytest

from knowledge_server.parsers import pdf_parser
from knowledge_server.parsers.pdf_parser import parse_pdf
from tests.helpers import make_test_pdf


def test_pdf_parser_extracts_page_based_chunks(tmp_path: Path) -> None:
    fixture = make_test_pdf(
        tmp_path / "sample.pdf",
        [
            "Balance rules page one.\nMemo credits are included.",
            "Customer rules page two.\nClosed accounts cannot transact.",
        ],
    )

    result = parse_pdf(fixture)

    assert result.page_count == 2
    assert [chunk.section for chunk in result.chunks] == ["Page 1", "Page 2"]
    assert result.chunks[0].parser_version == "pdf-v1"
    assert result.chunks[1].parser_version == "pdf-v1"
    assert result.chunks[1].char_offset == len(result.chunks[0].content) + 1
    assert "Memo credits are included." in result.chunks[0].content


def test_pdf_parser_raises_clear_error_when_pdfplumber_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import(name: str):  # type: ignore[no-untyped-def]
        if name == "pdfplumber":
            raise ImportError("missing")
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr("knowledge_server.parsers.pdf_parser.importlib.import_module", fake_import)

    with pytest.raises(
        ImportError,
        match="pdfplumber is required for PDF ingestion: pip install pdfplumber",
    ):
        parse_pdf(Path("missing.pdf"))


def test_pdf_parser_rejects_excessive_page_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pdf_parser, "_load_pdfplumber", lambda: _FakePdfPlumber(["one", "two"]))
    monkeypatch.setattr(pdf_parser, "DEFAULT_MAX_PDF_PAGES", 1)

    with pytest.raises(ValueError, match="PDF parser resource limit exceeded: page count"):
        parse_pdf(tmp_path / "too-many-pages.pdf")


def test_pdf_parser_rejects_excessive_extracted_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pdf_parser, "_load_pdfplumber", lambda: _FakePdfPlumber(["0123456789"]))
    monkeypatch.setattr(pdf_parser, "DEFAULT_MAX_PDF_EXTRACTED_TEXT_CHARS", 5)

    with pytest.raises(ValueError, match="PDF parser resource limit exceeded: extracted text size"):
        parse_pdf(tmp_path / "too-much-text.pdf")


class _FakePdfPlumber:
    def __init__(self, page_texts: list[str]) -> None:
        self._page_texts = page_texts

    def open(self, _path: Path) -> "_FakePdf":
        return _FakePdf(self._page_texts)


class _FakePdf:
    def __init__(self, page_texts: list[str]) -> None:
        self.pages = [_FakePage(text) for text in page_texts]

    def __enter__(self) -> "_FakePdf":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


class _FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text
