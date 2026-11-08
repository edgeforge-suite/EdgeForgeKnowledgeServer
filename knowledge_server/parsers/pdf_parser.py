from __future__ import annotations

import hashlib
import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from knowledge_server.parsers.markdown_parser import TextChunk
from knowledge_server.safety import DEFAULT_MAX_PDF_EXTRACTED_TEXT_CHARS, DEFAULT_MAX_PDF_PAGES

PARSER_VERSION = "pdf-v1"


@dataclass(frozen=True)
class PdfParseResult:
    chunks: list[TextChunk]
    page_count: int
    parser_version: str = PARSER_VERSION

    @property
    def content_hash(self) -> str:
        full_text = "\n".join(chunk.content for chunk in self.chunks)
        return hashlib.sha256(full_text.encode("utf-8")).hexdigest()


def parse_pdf(path: Path) -> PdfParseResult:
    pdfplumber = _load_pdfplumber()
    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        if page_count > DEFAULT_MAX_PDF_PAGES:
            raise ValueError(
                f"PDF parser resource limit exceeded: page count {page_count} "
                f"exceeds maximum {DEFAULT_MAX_PDF_PAGES}"
            )
        chunks: list[TextChunk] = []
        char_offset = 0
        extracted_chars = 0
        for page_number, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            extracted_chars += len(text)
            if extracted_chars > DEFAULT_MAX_PDF_EXTRACTED_TEXT_CHARS:
                raise ValueError(
                    f"PDF parser resource limit exceeded: extracted text size {extracted_chars} "
                    f"exceeds maximum {DEFAULT_MAX_PDF_EXTRACTED_TEXT_CHARS} characters"
                )
            chunks.append(
                TextChunk(
                    section=f"Page {page_number}",
                    heading=f"Page {page_number}",
                    content=text,
                    char_offset=char_offset,
                    position=page_number - 1,
                    parser_version=PARSER_VERSION,
                )
            )
            char_offset += len(text) + 1
        return PdfParseResult(chunks=chunks, page_count=page_count)


def _load_pdfplumber() -> Any:
    try:
        return importlib.import_module("pdfplumber")
    except ImportError as exc:
        raise ImportError(
            "pdfplumber is required for PDF ingestion: pip install pdfplumber"
        ) from exc
