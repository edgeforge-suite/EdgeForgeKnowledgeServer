import zipfile
from pathlib import Path

import pytest

from knowledge_server.parsers.docx_parser import parse_docx
from tests.helpers import make_empty_docx, make_test_docx


def test_docx_parser_splits_chunks_by_heading(tmp_path: Path) -> None:
    fixture = make_test_docx(
        tmp_path / "sample.docx",
        [
            ("Balance Rules", "Memo credits are included in available balance."),
            ("Customer Rules", "Closed accounts cannot accept new transactions."),
        ],
    )

    result = parse_docx(fixture)

    assert [chunk.section for chunk in result.chunks] == ["Balance Rules", "Customer Rules"]
    assert "Memo credits are included" in result.chunks[0].content
    assert result.chunks[0].parser_version == "docx-v1"
    assert result.chunks[1].char_offset > result.chunks[0].char_offset


def test_docx_parser_without_headings_returns_single_document_chunk(tmp_path: Path) -> None:
    fixture = make_test_docx(
        tmp_path / "no-headings.docx",
        [
            (None, "First paragraph without headings."),
            (None, "Second paragraph in the same document."),
        ],
    )

    result = parse_docx(fixture)

    assert len(result.chunks) == 1
    assert result.chunks[0].section == "Document"
    assert "Second paragraph" in result.chunks[0].content


def test_docx_parser_empty_document_returns_no_chunks(tmp_path: Path) -> None:
    fixture = make_empty_docx(tmp_path / "empty.docx")

    result = parse_docx(fixture)

    assert result.chunks == []


def test_docx_parser_raises_clear_error_when_python_docx_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import(name: str):  # type: ignore[no-untyped-def]
        if name == "docx":
            raise ImportError("missing")
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr("knowledge_server.parsers.docx_parser.importlib.import_module", fake_import)

    with pytest.raises(
        ImportError,
        match="python-docx is required for DOCX ingestion: pip install python-docx",
    ):
        parse_docx(Path("missing.docx"))


def test_docx_parser_rejects_too_many_zip_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = tmp_path / "too-many-entries.docx"
    _write_zip(fixture, [("[Content_Types].xml", b""), ("word/document.xml", b"")])
    monkeypatch.setattr("knowledge_server.safety.DEFAULT_MAX_ZIP_ENTRIES", 1)

    with pytest.raises(
        ValueError, match="DOCX parser resource limit exceeded: ZIP entry count"
    ):
        parse_docx(fixture)


def test_docx_parser_rejects_excessive_uncompressed_size(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = tmp_path / "too-large.docx"
    _write_zip(fixture, [("[Content_Types].xml", b"0123456789")])
    monkeypatch.setattr("knowledge_server.safety.DEFAULT_MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES", 5)

    with pytest.raises(ValueError, match="DOCX parser resource limit exceeded"):
        parse_docx(fixture)


def test_docx_parser_rejects_suspicious_zip_paths(tmp_path: Path) -> None:
    fixture = tmp_path / "bad-path.docx"
    _write_zip(fixture, [("word/../evil.xml", b"nope")])

    with pytest.raises(ValueError, match="suspicious ZIP entry path"):
        parse_docx(fixture)


def _write_zip(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
