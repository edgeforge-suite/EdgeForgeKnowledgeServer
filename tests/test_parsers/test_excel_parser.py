import zipfile
from pathlib import Path

import pytest

from knowledge_server.parsers.excel_parser import parse_excel


def test_excel_parser_extracts_field_catalog_rows() -> None:
    result = parse_excel(Path("tests/fixtures/data-dictionary.xlsx"))

    assert len(result.fields) == 3
    account_id = result.fields[0]
    assert account_id.entity == "Account"
    assert account_id.name == "account_id"
    assert account_id.type == "string"
    assert account_id.length == 12
    assert account_id.nullable is False
    assert account_id.source_location == "row 2"


def test_excel_parser_supports_flexible_header_matching(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Column Name", "Datatype", "Table", "Size", "Required", "Notes"])
    sheet.append(["external_id", "string", "Account", 64, "yes", "External reference"])
    sheet.append(["nickname", "string", "Account", 32, "no", "Optional nickname"])
    fixture = tmp_path / "headers.xlsx"
    workbook.save(fixture)
    workbook.close()

    result = parse_excel(fixture)

    assert [field.name for field in result.fields] == ["external_id", "nickname"]
    assert result.fields[0].nullable is False
    assert result.fields[1].nullable is True
    assert result.fields[0].description == "External reference"


def test_excel_parser_raises_clear_error_when_openpyxl_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import(name: str):  # type: ignore[no-untyped-def]
        if name == "openpyxl":
            raise ImportError("missing")
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(
        "knowledge_server.parsers.excel_parser.importlib.import_module", fake_import
    )

    with pytest.raises(
        ImportError,
        match="openpyxl is required for Excel ingestion: pip install openpyxl",
    ):
        parse_excel(Path("tests/fixtures/data-dictionary.xlsx"))


def test_excel_parser_rejects_too_many_zip_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = tmp_path / "too-many-entries.xlsx"
    _write_zip(fixture, [("[Content_Types].xml", b""), ("xl/workbook.xml", b"")])
    monkeypatch.setattr("knowledge_server.safety.DEFAULT_MAX_ZIP_ENTRIES", 1)

    with pytest.raises(
        ValueError, match="Excel parser resource limit exceeded: ZIP entry count"
    ):
        parse_excel(fixture)


def test_excel_parser_rejects_excessive_uncompressed_size(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = tmp_path / "too-large.xlsx"
    _write_zip(fixture, [("[Content_Types].xml", b"0123456789")])
    monkeypatch.setattr("knowledge_server.safety.DEFAULT_MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES", 5)

    with pytest.raises(ValueError, match="Excel parser resource limit exceeded"):
        parse_excel(fixture)


def test_excel_parser_rejects_suspicious_zip_paths(tmp_path: Path) -> None:
    fixture = tmp_path / "bad-path.xlsx"
    _write_zip(fixture, [("../evil.xml", b"nope")])

    with pytest.raises(ValueError, match="suspicious ZIP entry path"):
        parse_excel(fixture)


def _write_zip(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
