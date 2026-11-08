from __future__ import annotations

from knowledge_server.models import SubmitSuggestionDecisionsResult, SuggestionDecision
from knowledge_server.storage import KnowledgeStore


def submit_suggestion_decisions(
    *,
    store: KnowledgeStore,
    project_id: str,
    decisions: list[SuggestionDecision],
) -> SubmitSuggestionDecisionsResult:
    return store.submit_suggestion_decisions(project_id=project_id, decisions=decisions)
