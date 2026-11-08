from __future__ import annotations

from knowledge_server.models import ConflictResult
from knowledge_server.storage import KnowledgeStore


def find_conflicts(
    *,
    store: KnowledgeStore,
    project_id: str,
    query: str,
    doc_types: list[str] | None = None,
    max_chunks_to_search: int = 40,
    min_score: float | None = None,
) -> ConflictResult:
    return store.find_conflicts(
        project_id=project_id,
        query=query,
        doc_types=doc_types,
        max_chunks_to_search=max_chunks_to_search,
        min_score=min_score,
    )
