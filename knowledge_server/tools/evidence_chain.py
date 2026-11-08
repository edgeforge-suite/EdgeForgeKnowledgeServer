from __future__ import annotations

from knowledge_server.models.documents import FieldEvidenceChain, SuggestionEvidenceChain
from knowledge_server.storage import KnowledgeStore


def get_field_evidence_chain(
    *,
    store: KnowledgeStore,
    project_id: str,
    field_name: str,
    entity: str | None = None,
    max_chunks: int = 10,
) -> FieldEvidenceChain:
    return store.get_field_evidence_chain(
        project_id=project_id,
        field_name=field_name,
        entity=entity,
        max_chunks=max_chunks,
    )


def get_suggestion_evidence_chain(
    *,
    store: KnowledgeStore,
    project_id: str,
    suggestion_id: str,
    scope: str = "fields",
    max_chunks: int = 10,
) -> SuggestionEvidenceChain:
    return store.get_suggestion_evidence_chain(
        project_id=project_id,
        suggestion_id=suggestion_id,
        scope=scope,
        max_chunks=max_chunks,
    )
