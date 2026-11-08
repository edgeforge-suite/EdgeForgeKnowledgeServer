from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

PARSER_VERSION = "markdown-v1"


@dataclass(frozen=True)
class TextChunk:
    section: str
    heading: str
    content: str
    char_offset: int
    position: int
    parser_version: str = PARSER_VERSION

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def parse_markdown(path: Path) -> list[TextChunk]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    chunks: list[TextChunk] = []
    current_heading = "Document"
    current_lines: list[str] = []
    current_offset = 0
    running_offset = 0

    def flush() -> None:
        if not current_lines:
            return
        content = "\n".join(current_lines).strip()
        if not content:
            return
        chunks.append(
            TextChunk(
                section=current_heading,
                heading=current_heading,
                content=content,
                char_offset=current_offset,
                position=len(chunks),
            )
        )

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            flush()
            current_heading = stripped.lstrip("#").strip() or "Untitled"
            current_lines = [line]
            current_offset = running_offset
        else:
            if not current_lines:
                current_offset = running_offset
            current_lines.append(line)
        running_offset += len(line) + 1
    flush()

    if not chunks and text.strip():
        chunks.append(
            TextChunk(
                section="Document",
                heading="Document",
                content=text.strip(),
                char_offset=0,
                position=0,
            )
        )
    return chunks
