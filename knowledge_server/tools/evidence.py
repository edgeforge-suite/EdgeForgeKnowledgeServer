from __future__ import annotations

from knowledge_server.models import EvidenceResult
from knowledge_server.storage import KnowledgeStore


def get_evidence(
    *,
    store: KnowledgeStore,
    project_id: str,
    query: str,
    doc_types: list[str] | None = None,
    max_chunks: int = 10,
    min_score: float | None = None,
) -> EvidenceResult:
    return store.get_evidence(
        project_id=project_id,
        query=query,
        doc_types=doc_types,
        max_chunks=max_chunks,
        min_score=min_score,
    )
