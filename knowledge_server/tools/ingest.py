from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from knowledge_server.models import IngestResult
from knowledge_server.parsers.csv_parser import parse_csv
from knowledge_server.parsers.ddl_parser import parse_ddl
from knowledge_server.parsers.docx_parser import parse_docx
from knowledge_server.parsers.excel_parser import parse_excel
from knowledge_server.parsers.markdown_parser import TextChunk, parse_markdown
from knowledge_server.parsers.pdf_parser import parse_pdf
from knowledge_server.safety import enforce_file_size, resolve_allowed_path
from knowledge_server.storage.database import KnowledgeStore, stable_document_id

SUPPORTED_DOC_TYPES = {"markdown", "csv", "sql", "excel", "pdf", "docx"}
ALLOWED_EXTENSIONS = {
    "markdown": {".md", ".markdown"},
    "csv": {".csv"},
    "sql": {".sql"},
    "excel": {".xlsx"},
    "pdf": {".pdf"},
    "docx": {".docx"},
}
DocumentSpec = dict[str, object]


def ingest_document(
    *,
    store: KnowledgeStore,
    allowed_roots: list[Path],
    project_id: str,
    file_path: str,
    doc_type: str,
    tags: list[str] | None = None,
    description: str | None = None,
) -> IngestResult:
    normalized_type = doc_type.lower()
    if normalized_type not in SUPPORTED_DOC_TYPES:
        raise ValueError(
            "current implementation supports only markdown, csv, sql, excel, pdf, and docx doc_type values"
        )

    path = resolve_allowed_path(file_path, allowed_roots)
    enforce_file_size(path)
    _validate_extension(path, normalized_type)
    tags = tags or []

    parser = PARSER_REGISTRY[normalized_type]
    document_specs = parser(path, normalized_type, project_id)

    retain_document_ids = {spec["document_id"] for spec in document_specs}
    store.remove_documents_for_path_except(
        project_id=project_id,
        file_path=path,
        retain_document_ids=retain_document_ids,
    )
    for spec in document_specs:
        store.upsert_document(
            project_id=project_id,
            document_id=spec["document_id"],
            name=spec["name"],
            doc_type=spec["doc_type"],
            file_path=path,
            chunks=spec["chunks"],
            tags=tags,
            description=description,
            fields=spec["fields"],
        )

    primary = document_specs[0]
    warnings: list[str] = []
    if normalized_type == "sql" and len(document_specs) > 1:
        warnings.append(
            f"Ingested {len(document_specs)} SQL entities from {path.name}; return value references the first stored document."
        )
    return IngestResult(
        project_id=project_id,
        document_id=primary["document_id"],
        document_name=primary["name"],
        doc_type=normalized_type,
        section_count=sum(len(spec["chunks"]) for spec in document_specs),
        field_count=sum(len(spec["fields"]) for spec in document_specs),
        warnings=warnings,
    )


def _summary_chunk(heading: str, content: str, parser_version: str) -> TextChunk:
    return TextChunk(
        section=heading,
        heading=heading,
        content=content,
        char_offset=0,
        position=0,
        parser_version=parser_version,
    )


def _validate_extension(path: Path, doc_type: str) -> None:
    allowed_suffixes = ALLOWED_EXTENSIONS[doc_type]
    if path.suffix.lower() in allowed_suffixes:
        return
    suffixes = ", ".join(sorted(allowed_suffixes))
    raise ValueError(
        f"file extension mismatch for doc_type '{doc_type}': expected one of {suffixes}, got '{path.suffix or '<none>'}'"
    )


def _parse_markdown_spec(path: Path, doc_type: str, project_id: str) -> list[DocumentSpec]:
    return [
        {
            "document_id": stable_document_id(project_id, path),
            "name": path.name,
            "doc_type": doc_type,
            "chunks": parse_markdown(path),
            "fields": [],
        }
    ]


def _parse_csv_spec(path: Path, doc_type: str, project_id: str) -> list[DocumentSpec]:
    parsed = parse_csv(path)
    return [
        {
            "document_id": stable_document_id(project_id, path),
            "name": path.name,
            "doc_type": doc_type,
            "chunks": [_summary_chunk("CSV Field Catalog", parsed.content, parsed.parser_version)],
            "fields": parsed.fields,
        }
    ]


def _parse_excel_spec(path: Path, doc_type: str, project_id: str) -> list[DocumentSpec]:
    parsed = parse_excel(path)
    return [
        {
            "document_id": stable_document_id(project_id, path),
            "name": path.name,
            "doc_type": doc_type,
            "chunks": [_summary_chunk("Excel Field Catalog", parsed.content, parsed.parser_version)],
            "fields": parsed.fields,
        }
    ]


def _parse_pdf_spec(path: Path, doc_type: str, project_id: str) -> list[DocumentSpec]:
    parsed = parse_pdf(path)
    if not parsed.chunks:
        raise ValueError(f"{path.name}: no extractable text found — PDF may be scanned or image-only")
    return [
        {
            "document_id": stable_document_id(project_id, path),
            "name": path.name,
            "doc_type": doc_type,
            "chunks": parsed.chunks,
            "fields": [],
        }
    ]


def _parse_docx_spec(path: Path, doc_type: str, project_id: str) -> list[DocumentSpec]:
    parsed = parse_docx(path)
    if not parsed.chunks:
        raise ValueError(f"{path.name}: no extractable text found — DOCX appears to be empty")
    return [
        {
            "document_id": stable_document_id(project_id, path),
            "name": path.name,
            "doc_type": doc_type,
            "chunks": parsed.chunks,
            "fields": [],
        }
    ]


def _parse_sql_spec(path: Path, doc_type: str, project_id: str) -> list[DocumentSpec]:
    parsed_results = parse_ddl(path)
    if not parsed_results:
        raise ValueError(f"no supported CREATE TABLE or CREATE VIEW statements found in {path.name}")
    return [
        {
            "document_id": stable_document_id(project_id, path, parsed.entity_name),
            "name": f"{path.name}::{parsed.entity_name}",
            "doc_type": doc_type,
            "chunks": [_summary_chunk(parsed.entity_name, parsed.content, parsed.parser_version)],
            "fields": parsed.fields,
        }
        for parsed in parsed_results
    ]


PARSER_REGISTRY: dict[str, Callable[[Path, str, str], list[DocumentSpec]]] = {
    "markdown": _parse_markdown_spec,
    "csv": _parse_csv_spec,
    "excel": _parse_excel_spec,
    "pdf": _parse_pdf_spec,
    "docx": _parse_docx_spec,
    "sql": _parse_sql_spec,
}
