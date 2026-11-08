from __future__ import annotations

from knowledge_server.models import DocumentContent
from knowledge_server.storage import KnowledgeStore


def read_document(
    *,
    store: KnowledgeStore,
    project_id: str,
    document_id: str,
    section: str | None = None,
) -> DocumentContent:
    return store.read_document(project_id=project_id, document_id=document_id, section=section)
