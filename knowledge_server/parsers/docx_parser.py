from __future__ import annotations

import hashlib
import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from knowledge_server.parsers.markdown_parser import TextChunk
from knowledge_server.safety import enforce_zip_resource_limits

PARSER_VERSION = "docx-v1"


@dataclass(frozen=True)
class DocxParseResult:
    chunks: list[TextChunk]
    parser_version: str = PARSER_VERSION

    @property
    def content_hash(self) -> str:
        full_text = "\n\n".join(chunk.content for chunk in self.chunks)
        return hashlib.sha256(full_text.encode("utf-8")).hexdigest()


def parse_docx(path: Path) -> DocxParseResult:
    docx = _load_docx()
    enforce_zip_resource_limits(path, label="DOCX")
    document = docx.Document(path)
    paragraphs = [paragraph for paragraph in document.paragraphs if paragraph.text.strip()]
    if not paragraphs:
        return DocxParseResult(chunks=[])

    chunks: list[TextChunk] = []
    current_heading = "Document"
    current_lines: list[str] = []
    current_offset = 0
    running_offset = 0
    saw_heading = False

    def flush() -> None:
        if not current_lines:
            return
        content = "\n\n".join(current_lines).strip()
        if not content:
            return
        chunks.append(
            TextChunk(
                section=current_heading,
                heading=current_heading,
                content=content,
                char_offset=current_offset,
                position=len(chunks),
                parser_version=PARSER_VERSION,
            )
        )

    for paragraph in paragraphs:
        text = paragraph.text.strip()
        style_name = getattr(paragraph.style, "name", "") or ""
        if style_name.lower().startswith("heading"):
            saw_heading = True
            flush()
            current_heading = text or "Untitled"
            current_lines = [current_heading]
            current_offset = running_offset
        else:
            if not current_lines:
                current_offset = running_offset
            current_lines.append(text)
        running_offset += len(text) + 2

    flush()

    if saw_heading:
        return DocxParseResult(chunks=chunks)

    full_text = "\n\n".join(paragraph.text.strip() for paragraph in paragraphs)
    return DocxParseResult(
        chunks=[
            TextChunk(
                section="Document",
                heading="Document",
                content=full_text,
                char_offset=0,
                position=0,
                parser_version=PARSER_VERSION,
            )
        ]
    )


def _load_docx() -> Any:
    try:
        return importlib.import_module("docx")
    except ImportError as exc:
        raise ImportError(
            "python-docx is required for DOCX ingestion: pip install python-docx"
        ) from exc
