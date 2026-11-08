from __future__ import annotations

from knowledge_server.models import CrossProjectSearchResults
from knowledge_server.storage import KnowledgeStore


def search_across_projects(
    *,
    store: KnowledgeStore,
    query: str,
    project_ids: list[str] | None = None,
    doc_types: list[str] | None = None,
    max_results_per_project: int = 5,
    min_score: float | None = None,
) -> CrossProjectSearchResults:
    return store.search_across_projects(
        query=query,
        project_ids=project_ids,
        doc_types=doc_types,
        max_results_per_project=max_results_per_project,
        min_score=min_score,
    )
