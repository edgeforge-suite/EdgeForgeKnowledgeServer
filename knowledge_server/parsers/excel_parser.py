from __future__ import annotations

import hashlib
import importlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from knowledge_server.parsers.csv_parser import CsvField
from knowledge_server.safety import enforce_zip_resource_limits

PARSER_VERSION = "excel-v1"
_HEADER_ALIASES = {
    "field_name": {"field", "column", "name", "field_name", "column_name"},
    "field_type": {"type", "data_type", "datatype", "dtype"},
    "entity_name": {"table", "entity", "object", "table_name"},
    "length": {"length", "size", "max_length"},
    "nullable": {"nullable", "null", "required", "optional"},
    "description": {"description", "desc", "notes", "comment"},
}


@dataclass(frozen=True)
class ExcelParseResult:
    content: str
    fields: list[CsvField]
    parser_version: str = PARSER_VERSION

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def parse_excel(path: Path) -> ExcelParseResult:
    openpyxl = _load_openpyxl()
    enforce_zip_resource_limits(path, label="Excel")
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        fields: list[CsvField] = []
        for sheet in workbook.worksheets:
            fields.extend(_parse_sheet(sheet))
    finally:
        workbook.close()

    content_lines = [
        "Excel field catalog",
        *[
            " | ".join(
                part
                for part in [field.entity, field.name, field.type, field.description]
                if part
            )
            for field in fields
        ],
    ]
    return ExcelParseResult(content="\n".join(content_lines), fields=fields)


def _load_openpyxl() -> Any:
    try:
        return importlib.import_module("openpyxl")
    except ImportError as exc:
        raise ImportError("openpyxl is required for Excel ingestion: pip install openpyxl") from exc


def _parse_sheet(sheet: Any) -> list[CsvField]:
    rows = list(sheet.iter_rows(values_only=True))
    header_row_index, header_row = _find_header_row(rows)
    if header_row is None:
        return []

    mapping = _map_headers(header_row)
    fields: list[CsvField] = []
    for row_number, row in enumerate(rows[header_row_index:], start=header_row_index + 1):
        if _is_empty(row):
            continue
        field = _row_to_field(row, row_number, mapping)
        if field.name:
            fields.append(field)
    return fields


def _find_header_row(rows: list[tuple[Any, ...]]) -> tuple[int, tuple[Any, ...] | None]:
    for index, row in enumerate(rows):
        if not _is_empty(row):
            return index + 1, row
    return 0, None


def _map_headers(header_row: tuple[Any, ...]) -> dict[str, tuple[int, str]]:
    mapping: dict[str, tuple[int, str]] = {}
    for index, value in enumerate(header_row):
        normalized = _normalize_header(value)
        if not normalized:
            continue
        for attribute, aliases in _HEADER_ALIASES.items():
            if (
                normalized in {_normalize_header(alias) for alias in aliases}
                and attribute not in mapping
            ):
                mapping[attribute] = (index, normalized)
    return mapping


def _row_to_field(
    row: tuple[Any, ...], row_number: int, mapping: dict[str, tuple[int, str]]
) -> CsvField:
    return CsvField(
        name=_value(row, mapping.get("field_name")) or "",
        type=_value(row, mapping.get("field_type")),
        length=_int_or_none(_value(row, mapping.get("length"))),
        precision=None,
        scale=None,
        nullable=_nullable_value(row, mapping.get("nullable")),
        description=_value(row, mapping.get("description")),
        entity=_value(row, mapping.get("entity_name")),
        source_location=f"row {row_number}",
    )


def _value(row: tuple[Any, ...], column: tuple[int, str] | None) -> str | None:
    if column is None:
        return None
    index, _ = column
    if index >= len(row):
        return None
    value = row[index]
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _nullable_value(row: tuple[Any, ...], column: tuple[int, str] | None) -> bool | None:
    if column is None:
        return None
    value = _value(row, column)
    if value is None:
        return None
    _, header = column
    lowered = value.lower()
    truthy = lowered in {"true", "yes", "y", "1", "required", "optional", "nullable"}
    falsy = lowered in {"false", "no", "n", "0", "not null"}
    if header == "required":
        if truthy:
            return False
        if falsy:
            return True
    elif header == "optional":
        if truthy:
            return True
        if falsy:
            return False
    else:
        if truthy:
            return True
        if falsy:
            return False
    return None


def _normalize_header(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[\s_]+", "", str(value).strip().lower())


def _int_or_none(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _is_empty(row: tuple[Any, ...]) -> bool:
    return not any(value is not None and str(value).strip() for value in row)
