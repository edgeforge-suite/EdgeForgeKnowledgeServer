from __future__ import annotations

from knowledge_server.models import DocumentList, SearchResults
from knowledge_server.storage import KnowledgeStore


def list_documents(
    *,
    store: KnowledgeStore,
    project_id: str,
    doc_type: str | None = None,
    tags: list[str] | None = None,
) -> DocumentList:
    return store.list_documents(project_id=project_id, doc_type=doc_type, tags=tags)


def search_documents(
    *,
    store: KnowledgeStore,
    project_id: str,
    query: str,
    doc_types: list[str] | None = None,
    max_results: int = 20,
    min_score: float | None = None,
) -> SearchResults:
    return store.search_documents(
        project_id=project_id,
        query=query,
        doc_types=doc_types,
        max_results=max_results,
        min_score=min_score,
    )
