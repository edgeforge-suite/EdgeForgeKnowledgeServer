from __future__ import annotations

from knowledge_server.models import DeleteResult, PurgeResult
from knowledge_server.storage import KnowledgeStore


def delete_document(
    *,
    store: KnowledgeStore,
    project_id: str,
    document_id: str,
) -> DeleteResult:
    return store.delete_document(project_id=project_id, document_id=document_id)


def purge_document(
    *,
    store: KnowledgeStore,
    project_id: str,
    document_id: str,
    confirm_purge: bool = False,
) -> PurgeResult:
    return store.purge_document(
        project_id=project_id,
        document_id=document_id,
        confirm_purge=confirm_purge,
    )
