from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from pathlib import Path

from knowledge_server.parsers.csv_parser import CsvField

PARSER_VERSION = "ddl-v1"
_IDENTIFIER = r'(?:[A-Za-z_][\w$]*|"[^"]+"|`[^`]+`|\[[^\]]+\])'
_CREATE_RE = re.compile(
    rf"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?P<kind>TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>{_IDENTIFIER}(?:\s*\.\s*{_IDENTIFIER})?)",
    re.IGNORECASE | re.DOTALL,
)
_CONSTRAINT_PREFIXES = ("CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK")
_TYPE_STOPWORDS = {
    "NOT",
    "NULL",
    "DEFAULT",
    "PRIMARY",
    "UNIQUE",
    "REFERENCES",
    "CHECK",
    "CONSTRAINT",
    "COLLATE",
    "COMMENT",
    "GENERATED",
    "AS",
}
_COMMENT_ON_COLUMN_RE = re.compile(
    rf"^\s*COMMENT\s+ON\s+COLUMN\s+"
    rf"(?P<table>{_IDENTIFIER}(?:\s*\.\s*{_IDENTIFIER})?)\s*\.\s*"
    rf"(?P<column>{_IDENTIFIER})\s+IS\s+'(?P<comment>(?:''|[^'])*)'\s*;?\s*$",
    re.IGNORECASE | re.DOTALL,
)
_TYPE_ALIASES = {
    "VARCHAR2": "VARCHAR",
    "NVARCHAR2": "VARCHAR",
    "NUMBER": "DECIMAL",
}


@dataclass(frozen=True)
class DdlParseResult:
    entity_name: str
    fields: list[CsvField]
    content: str
    parser_version: str = PARSER_VERSION

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def parse_ddl(path: Path) -> list[DdlParseResult]:
    text = path.read_text(encoding="utf-8")
    results: list[DdlParseResult] = []
    column_comments: dict[tuple[str, str], str] = {}
    for statement, line_number in _split_sql_statements(text):
        comment = _parse_column_comment(statement)
        if comment is not None:
            table_name, column_name, description = comment
            column_comments[(_identifier_key(table_name), _identifier_key(column_name))] = description
            continue
        parsed = _parse_statement(statement, line_number)
        if parsed is not None:
            results.append(parsed)
    if column_comments:
        results = [_apply_column_comments(result, column_comments) for result in results]
    return results


def _parse_statement(statement: str, line_number: int) -> DdlParseResult | None:
    statement, line_number = _strip_leading_sql_comments(statement, line_number)
    if not statement:
        return None
    match = _CREATE_RE.match(statement)
    if match is None:
        return None

    entity_name = _normalize_identifier(match.group("name").split(".")[-1])
    kind = match.group("kind").upper()
    if kind == "TABLE":
        open_paren = statement.find("(", match.end())
        if open_paren == -1:
            return None
        close_paren = _find_matching_paren(statement, open_paren)
        if close_paren == -1:
            return None
        block = statement[open_paren + 1 : close_paren]
        block_line = line_number + statement[: open_paren + 1].count("\n")
        fields = _parse_table_columns(block, block_line, entity_name)
    else:
        fields = _parse_view_columns(statement, line_number, entity_name, match.end())

    return DdlParseResult(
        entity_name=entity_name,
        fields=fields,
        content=_summary(entity_name, kind, fields),
    )


def _split_sql_statements(text: str) -> list[tuple[str, int]]:
    statements: list[tuple[str, int]] = []
    start = 0
    depth = 0
    in_single = False
    in_double = False
    i = 0
    while i < len(text):
        chunk = text[i : i + 2]
        char = text[i]
        if not in_single and not in_double and chunk == "--":
            newline = text.find("\n", i)
            i = len(text) if newline == -1 else newline
            continue
        if not in_single and not in_double and chunk == "/*":
            end = text.find("*/", i + 2)
            i = len(text) if end == -1 else end + 2
            continue
        if char == "'" and not in_double:
            if in_single and i + 1 < len(text) and text[i + 1] == "'":
                i += 2
                continue
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if char == "(":
                depth += 1
            elif char == ")" and depth > 0:
                depth -= 1
            elif char == ";" and depth == 0:
                statement = text[start : i + 1]
                stripped = statement.strip()
                if stripped:
                    content_start = start + len(statement) - len(statement.lstrip())
                    statements.append((stripped, text.count("\n", 0, content_start) + 1))
                start = i + 1
        i += 1

    trailing = text[start:]
    stripped = trailing.strip()
    if stripped:
        content_start = start + len(trailing) - len(trailing.lstrip())
        statements.append((stripped, text.count("\n", 0, content_start) + 1))
    return statements


def _parse_table_columns(block: str, base_line: int, entity_name: str) -> list[CsvField]:
    fields: list[CsvField] = []
    metadata_by_column: dict[str, dict[str, object]] = {}
    for raw_column, offset in _split_block_items(block):
        constraint_metadata = _parse_table_constraint(raw_column)
        for column_name, metadata in constraint_metadata.items():
            existing = metadata_by_column.setdefault(column_name, {})
            existing.update(metadata)
        if constraint_metadata:
            continue
        parsed = _parse_column(raw_column, base_line + block.count("\n", 0, offset), entity_name)
        if parsed is not None:
            fields.append(parsed)
    return [_merge_field_metadata(field, metadata_by_column.get(_identifier_key(field.name))) for field in fields]


def _split_block_items(block: str) -> list[tuple[str, int]]:
    items: list[tuple[str, int]] = []
    start = 0
    depth = 0
    in_single = False
    in_double = False
    i = 0
    while i < len(block):
        chunk = block[i : i + 2]
        char = block[i]
        if not in_single and not in_double and chunk == "--":
            newline = block.find("\n", i)
            if newline == -1:
                i = len(block)
                break
            i = newline
            continue
        if not in_single and not in_double and chunk == "/*":
            end = block.find("*/", i + 2)
            if end == -1:
                i = len(block)
                break
            i = end + 2
            continue
        if char == "'" and not in_double:
            if in_single and i + 1 < len(block) and block[i + 1] == "'":
                i += 2
                continue
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if char == "(":
                depth += 1
            elif char == ")" and depth > 0:
                depth -= 1
            elif char == "," and depth == 0:
                item_end = i
                next_index = i + 1
                while next_index < len(block) and block[next_index] in " \t":
                    next_index += 1
                if block.startswith("--", next_index):
                    newline = block.find("\n", next_index)
                    item_end = len(block) if newline == -1 else newline
                    items.append((block[start:item_end], start))
                    if newline == -1:
                        return items
                    start = newline + 1
                    i = newline
                    continue
                items.append((block[start:i], start))
                start = i + 1
        i += 1
    items.append((block[start:], start))
    return items


def _parse_column(raw_column: str, base_line: int, entity_name: str) -> CsvField | None:
    column = raw_column.strip()
    if not column:
        return None

    leading_comments: list[str] = []
    definition_lines: list[str] = []
    for line in raw_column.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not definition_lines and stripped.startswith("--"):
            leading_comments.append(stripped[2:].strip())
            continue
        definition_lines.append(line)
    definition = "\n".join(definition_lines).strip()
    if not definition:
        return None
    if definition.upper().startswith(_CONSTRAINT_PREFIXES):
        return None

    line_offset = raw_column.find(definition_lines[0])
    source_line = base_line + raw_column[:line_offset].count("\n")

    definition, inline_comment = _split_inline_comment(definition)
    definition, comment_clause = _strip_comment_clause(definition)

    match = re.match(rf"^\s*(?P<name>{_IDENTIFIER})\s+(?P<rest>.+)$", definition, re.DOTALL)
    if match is None:
        return None

    name = _normalize_identifier(match.group("name"))
    rest = " ".join(match.group("rest").split())
    data_type = _extract_data_type(rest)
    field_type, length, precision, scale = _type_metadata(data_type)
    description = " ".join(part for part in [*leading_comments, comment_clause, inline_comment] if part) or None
    source_metadata = _inline_constraint_metadata(rest)

    return CsvField(
        name=name,
        type=field_type,
        length=length,
        precision=precision,
        scale=scale,
        nullable=not bool(re.search(r"\bNOT\s+NULL\b", rest, re.IGNORECASE)),
        description=description,
        entity=entity_name,
        source_location=f"line {source_line}",
        source_metadata=source_metadata,
    )


def _parse_table_constraint(raw_column: str) -> dict[str, dict[str, object]]:
    definition = " ".join(raw_column.strip().split())
    if not definition:
        return {}
    upper = definition.upper()
    if upper.startswith("CONSTRAINT "):
        parts = definition.split(maxsplit=2)
        definition = parts[2] if len(parts) == 3 else ""
        upper = definition.upper()
    metadata_by_column: dict[str, dict[str, object]] = {}

    pk_match = re.search(r"\bPRIMARY\s+KEY\s*\((?P<columns>[^)]*)\)", definition, re.IGNORECASE)
    if pk_match:
        for column_name in _constraint_columns(pk_match.group("columns")):
            metadata_by_column.setdefault(_identifier_key(column_name), {})["primary_key"] = True

    unique_match = re.search(r"\bUNIQUE\s*\((?P<columns>[^)]*)\)", definition, re.IGNORECASE)
    if unique_match:
        for column_name in _constraint_columns(unique_match.group("columns")):
            metadata_by_column.setdefault(_identifier_key(column_name), {})["unique"] = True

    fk_match = re.search(
        rf"\bFOREIGN\s+KEY\s*\((?P<columns>[^)]*)\)\s+REFERENCES\s+"
        rf"(?P<table>{_IDENTIFIER}(?:\s*\.\s*{_IDENTIFIER})?)"
        rf"(?:\s*\((?P<ref_columns>[^)]*)\))?",
        definition,
        re.IGNORECASE,
    )
    if fk_match:
        referenced_entity = _normalize_identifier(fk_match.group("table").split(".")[-1])
        referenced_columns = _constraint_columns(fk_match.group("ref_columns") or "")
        for index, column_name in enumerate(_constraint_columns(fk_match.group("columns"))):
            metadata = metadata_by_column.setdefault(_identifier_key(column_name), {})
            metadata["foreign_key"] = True
            metadata["referenced_entity"] = referenced_entity
            if index < len(referenced_columns):
                metadata["referenced_field"] = referenced_columns[index]
    return metadata_by_column


def _constraint_columns(columns: str) -> list[str]:
    return [
        _normalize_identifier(column.strip())
        for column in columns.split(",")
        if column.strip()
    ]


def _inline_constraint_metadata(rest: str) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if re.search(r"\bPRIMARY\s+KEY\b", rest, re.IGNORECASE):
        metadata["primary_key"] = True
    if re.search(r"\bUNIQUE\b", rest, re.IGNORECASE):
        metadata["unique"] = True
    references_match = re.search(
        rf"\bREFERENCES\s+(?P<table>{_IDENTIFIER}(?:\s*\.\s*{_IDENTIFIER})?)"
        rf"(?:\s*\((?P<column>{_IDENTIFIER})\))?",
        rest,
        re.IGNORECASE,
    )
    if references_match:
        metadata["foreign_key"] = True
        metadata["referenced_entity"] = _normalize_identifier(references_match.group("table").split(".")[-1])
        referenced_field = references_match.group("column")
        if referenced_field:
            metadata["referenced_field"] = _normalize_identifier(referenced_field)
    return metadata


def _merge_field_metadata(field: CsvField, metadata: dict[str, object] | None) -> CsvField:
    if not metadata:
        return field
    merged = dict(field.source_metadata or {})
    merged.update(metadata)
    return replace(field, source_metadata=merged)


def _parse_view_columns(statement: str, base_line: int, entity_name: str, offset: int) -> list[CsvField]:
    trailing = statement[offset:]
    explicit = re.search(r"\((?P<columns>.*?)\)\s+AS\b", trailing, re.IGNORECASE | re.DOTALL)
    if explicit:
        return _view_fields_from_list(explicit.group("columns"), base_line, entity_name, trailing)

    select_match = re.search(r"\bAS\s+SELECT\s+(?P<select>.*?)\bFROM\b", statement, re.IGNORECASE | re.DOTALL)
    if select_match is None:
        return []

    fields: list[CsvField] = []
    select_list = select_match.group("select")
    for raw_item, _offset in _split_block_items(select_list):
        expression = raw_item.strip()
        if not expression:
            continue
        alias_match = re.search(rf"\bAS\s+(?P<alias>{_IDENTIFIER})\s*$", expression, re.IGNORECASE)
        alias = alias_match.group("alias") if alias_match else expression.split()[-1]
        fields.append(
            CsvField(
                name=_normalize_identifier(alias),
                type=None,
                length=None,
                precision=None,
                scale=None,
                nullable=True,
                description=None,
                entity=entity_name,
                source_location=f"line {base_line + statement.count(chr(10), 0, statement.find(expression))}",
            )
        )
    return fields


def _view_fields_from_list(columns: str, base_line: int, entity_name: str, trailing: str) -> list[CsvField]:
    fields: list[CsvField] = []
    for raw_column, _offset in _split_block_items(columns):
        name = raw_column.strip()
        if not name:
            continue
        relative = trailing.find(raw_column)
        source_line = base_line + trailing.count("\n", 0, relative)
        fields.append(
            CsvField(
                name=_normalize_identifier(name),
                type=None,
                length=None,
                precision=None,
                scale=None,
                nullable=True,
                description=None,
                entity=entity_name,
                source_location=f"line {source_line}",
            )
        )
    return fields


def _split_inline_comment(text: str) -> tuple[str, str | None]:
    in_single = False
    in_double = False
    i = 0
    while i < len(text) - 1:
        chunk = text[i : i + 2]
        char = text[i]
        if char == "'" and not in_double:
            if in_single and i + 1 < len(text) and text[i + 1] == "'":
                i += 2
                continue
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double and chunk == "--":
            return text[:i].rstrip(), text[i + 2 :].strip()
        i += 1
    return text, None


def _strip_leading_sql_comments(statement: str, line_number: int) -> tuple[str, int]:
    index = 0
    current_line = line_number
    while index < len(statement):
        whitespace_match = re.match(r"\s*", statement[index:])
        if whitespace_match:
            whitespace = whitespace_match.group(0)
            current_line += whitespace.count("\n")
            index += len(whitespace)

        if statement.startswith("--", index):
            newline = statement.find("\n", index)
            if newline == -1:
                return "", current_line
            index = newline + 1
            current_line += 1
            continue

        if statement.startswith("/*", index):
            end = statement.find("*/", index + 2)
            if end == -1:
                return "", current_line
            comment = statement[index : end + 2]
            current_line += comment.count("\n")
            index = end + 2
            continue

        break
    return statement[index:].strip(), current_line


def _parse_column_comment(statement: str) -> tuple[str, str, str] | None:
    statement, _ = _strip_leading_sql_comments(statement, 1)
    match = _COMMENT_ON_COLUMN_RE.match(statement)
    if match is None:
        return None
    table_name = _normalize_identifier(match.group("table").split(".")[-1])
    column_name = _normalize_identifier(match.group("column"))
    description = match.group("comment").replace("''", "'").strip()
    return table_name, column_name, description


def _apply_column_comments(
    result: DdlParseResult,
    column_comments: dict[tuple[str, str], str],
) -> DdlParseResult:
    fields: list[CsvField] = []
    changed = False
    for field in result.fields:
        comment = column_comments.get((_identifier_key(result.entity_name), _identifier_key(field.name)))
        if not comment:
            fields.append(field)
            continue
        description = _merge_descriptions(field.description, comment)
        fields.append(replace(field, description=description))
        changed = True
    if not changed:
        return result
    return replace(result, fields=fields, content=_summary(result.entity_name, "TABLE", fields))


def _merge_descriptions(existing: str | None, additional: str) -> str:
    if not existing:
        return additional
    if existing == additional or additional in existing:
        return existing
    return f"{existing} {additional}"


def _strip_comment_clause(text: str) -> tuple[str, str | None]:
    match = re.search(r"\bCOMMENT\s+'(?P<comment>(?:''|[^'])*)'", text, re.IGNORECASE)
    if match is None:
        return text, None
    comment = match.group("comment").replace("''", "'").strip()
    return (text[: match.start()] + text[match.end() :]).strip(), comment


def _extract_data_type(rest: str) -> str | None:
    tokens = _split_tokens(rest)
    collected: list[str] = []
    for token in tokens:
        if token.upper() in _TYPE_STOPWORDS:
            break
        collected.append(token)
    value = " ".join(collected).strip()
    return value or None


def _split_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        if char.isspace() and depth == 0:
            if current:
                tokens.append("".join(current))
                current = []
            continue
        current.append(char)
    if current:
        tokens.append("".join(current))
    return tokens


def _type_metadata(data_type: str | None) -> tuple[str | None, int | None, int | None, int | None]:
    if not data_type:
        return None, None, None, None
    match = re.match(r"^(?P<base>[A-Za-z][A-Za-z0-9_ ]*)(?:\((?P<args>[^)]*)\))?$", data_type.strip())
    if match is None:
        return data_type.upper(), None, None, None

    raw_field_type = " ".join(match.group("base").split()).upper()
    field_type = _TYPE_ALIASES.get(raw_field_type, raw_field_type)
    args = match.group("args")
    if not args:
        return field_type, None, None, None

    parts = [part.strip() for part in args.split(",")]
    numbers = [int(part) for part in parts if part.isdigit()]
    if field_type in {"DECIMAL", "NUMERIC"}:
        precision = numbers[0] if numbers else None
        scale = numbers[1] if len(numbers) > 1 else None
        return field_type, None, precision, scale
    length = numbers[0] if numbers else None
    return field_type, length, None, None


def _find_matching_paren(text: str, start: int) -> int:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _normalize_identifier(identifier: str) -> str:
    cleaned = identifier.strip()
    if cleaned.startswith('"') and cleaned.endswith('"'):
        return cleaned[1:-1]
    if cleaned.startswith("`") and cleaned.endswith("`"):
        return cleaned[1:-1]
    if cleaned.startswith("[") and cleaned.endswith("]"):
        return cleaned[1:-1]
    return cleaned


def _identifier_key(identifier: str) -> str:
    return _normalize_identifier(identifier).lower()


def _summary(entity_name: str, kind: str, fields: list[CsvField]) -> str:
    lines = [f"{kind.title()} {entity_name}"]
    for field in fields:
        metadata = field.source_metadata or {}
        signals: list[str] = []
        if metadata.get("primary_key"):
            signals.append("primary key")
        if metadata.get("unique"):
            signals.append("unique")
        if metadata.get("foreign_key"):
            reference = ".".join(
                str(value)
                for value in [metadata.get("referenced_entity"), metadata.get("referenced_field")]
                if value
            )
            signals.append(f"foreign key references {reference}" if reference else "foreign key")
        parts = [field.entity, field.name, field.type, field.description, "; ".join(signals)]
        lines.append(" | ".join(part for part in parts if part))
    return "\n".join(lines)
