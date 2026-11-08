from pathlib import Path

import pytest

from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.ingest import ingest_document


def test_unsupported_doc_types_stay_out_of_first_slice(tmp_path: Path) -> None:
    fixture = tmp_path / "future.pptx"
    fixture.write_text("not yet", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    with pytest.raises(ValueError, match="markdown, csv, sql, excel, pdf, and docx"):
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(fixture),
            doc_type="pptx",
        )
