from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PARSER_VERSION = "csv-v1"


@dataclass(frozen=True)
class CsvField:
    name: str
    type: str | None
    length: int | None
    precision: int | None
    scale: int | None
    nullable: bool | None
    description: str | None
    entity: str | None
    source_location: str
    source_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class CsvParseResult:
    content: str
    fields: list[CsvField]
    parser_version: str = PARSER_VERSION

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def parse_csv(path: Path) -> CsvParseResult:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    fields = [_row_to_field(row, index + 2) for index, row in enumerate(rows)]
    content_lines = [
        "CSV field catalog",
        *[
            " | ".join(
                part
                for part in [
                    field.entity,
                    field.name,
                    field.type,
                    field.description,
                ]
                if part
            )
            for field in fields
        ],
    ]
    return CsvParseResult(content="\n".join(content_lines), fields=fields)


def _row_to_field(row: dict[str, str], row_number: int) -> CsvField:
    normalized = {key.strip().lower().replace(" ", "_"): value.strip() for key, value in row.items()}
    source_metadata = _source_metadata(normalized)
    return CsvField(
        name=_first(normalized, "field_name", "name", "field", "column_name", "column") or "",
        type=_first(normalized, "type", "field_type", "data_type"),
        length=_int_or_none(_first(normalized, "length", "size")),
        precision=_int_or_none(_first(normalized, "precision")),
        scale=_int_or_none(_first(normalized, "scale")),
        nullable=_bool_or_none(_first(normalized, "nullable", "nullability", "required")),
        description=_first(normalized, "description", "desc", "business_description"),
        entity=_first(normalized, "entity", "table", "table_name", "record"),
        source_location=f"row {row_number}",
        source_metadata=source_metadata,
    )


def _first(row: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value:
            return value
    return None


def _int_or_none(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _bool_or_none(value: str | None) -> bool | None:
    if not value:
        return None
    lowered = value.lower()
    if lowered in {"true", "yes", "y", "nullable", "optional"}:
        return True
    if lowered in {"false", "no", "n", "not null", "required"}:
        return False
    return None


def _source_metadata(row: dict[str, str]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    identity_role = _first(row, "identity_role", "identity role")
    if identity_role:
        metadata["identity_role"] = identity_role
    primary_key = _bool_or_none(_first(row, "primary_key", "pk", "is_primary_key"))
    if primary_key is True:
        metadata["primary_key"] = True
    unique = _bool_or_none(_first(row, "unique", "unique_key", "is_unique"))
    if unique is True:
        metadata["unique"] = True
    foreign_key = _bool_or_none(_first(row, "foreign_key", "fk", "is_foreign_key"))
    referenced_entity = _first(row, "referenced_entity", "references_entity", "referenced_table")
    referenced_field = _first(row, "referenced_field", "references_field", "referenced_column")
    if foreign_key is True or referenced_entity or referenced_field:
        metadata["foreign_key"] = True
        if referenced_entity:
            metadata["referenced_entity"] = referenced_entity
        if referenced_field:
            metadata["referenced_field"] = referenced_field
    return metadata
