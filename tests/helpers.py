from __future__ import annotations

import importlib
from collections.abc import Sequence
from pathlib import Path


def make_test_pdf(path: Path, pages: Sequence[str]) -> Path:
    objects: dict[int, bytes] = {}
    page_object_numbers: list[int] = []
    content_object_numbers: list[int] = []
    next_object = 4

    for _ in pages:
        page_object_numbers.append(next_object)
        content_object_numbers.append(next_object + 1)
        next_object += 2

    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)
    objects[2] = f"<< /Type /Pages /Count {len(pages)} /Kids [{kids}] >>".encode("ascii")
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    for page_number, text in enumerate(pages):
        page_object = page_object_numbers[page_number]
        content_object = content_object_numbers[page_number]
        stream = _pdf_text_stream(text)
        objects[page_object] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_object} 0 R >>"
        ).encode("ascii")
        objects[content_object] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
        )

    return _write_pdf(path, objects)


def make_test_docx(path: Path, sections: Sequence[tuple[str | None, str]]) -> Path:
    docx = importlib.import_module("docx")
    document = docx.Document()
    for heading, body in sections:
        if heading:
            document.add_heading(heading, level=1)
        if body:
            for paragraph in body.split("\n\n"):
                document.add_paragraph(paragraph)
    document.save(path)
    return path


def make_empty_docx(path: Path) -> Path:
    docx = importlib.import_module("docx")
    document = docx.Document()
    document.save(path)
    return path


def _pdf_text_stream(text: str) -> bytes:
    commands = ["BT", "/F1 12 Tf", "14 TL", "72 720 Td"]
    lines = text.splitlines() or [""]
    for index, line in enumerate(lines):
        escaped = _escape_pdf_string(line)
        if index == 0:
            commands.append(f"({escaped}) Tj")
        else:
            commands.extend(["T*", f"({escaped}) Tj"])
    commands.append("ET")
    return "\n".join(commands).encode("latin-1")


def _escape_pdf_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_pdf(path: Path, objects: dict[int, bytes]) -> Path:
    max_object = max(objects)
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (max_object + 1)

    for object_number in range(1, max_object + 1):
        offsets[object_number] = len(pdf)
        pdf.extend(f"{object_number} 0 obj\n".encode("ascii"))
        pdf.extend(objects[object_number])
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {max_object + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for object_number in range(1, max_object + 1):
        pdf.extend(f"{offsets[object_number]:010d} 00000 n \n".encode("ascii"))
    pdf.extend(f"trailer\n<< /Size {max_object + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))

    path.write_bytes(bytes(pdf))
    return path
