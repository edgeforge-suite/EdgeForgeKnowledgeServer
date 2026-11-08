from __future__ import annotations

from knowledge_server.models import SuggestFieldsResult, SuggestManifestCandidatesResult
from knowledge_server.storage import KnowledgeStore


def suggest_fields(
    *,
    store: KnowledgeStore,
    project_id: str,
    entity: str | None = None,
    field_name_pattern: str | None = None,
    min_source_count: int = 1,
    max_suggestions: int = 50,
) -> SuggestFieldsResult:
    return store.suggest_fields(
        project_id=project_id,
        entity=entity,
        field_name_pattern=field_name_pattern,
        min_source_count=min_source_count,
        max_suggestions=max_suggestions,
    )


def suggest_manifest_candidates(
    *,
    store: KnowledgeStore,
    project_id: str,
    scope: str = "fields",
    entity: str | None = None,
    route_name: str | None = None,
    source_entity: str | None = None,
    target_entity: str | None = None,
    target_id: str | None = None,
    direction: str | None = None,
    field_name_pattern: str | None = None,
    min_source_count: int = 1,
    max_suggestions: int = 50,
) -> SuggestManifestCandidatesResult:
    return store.suggest_manifest_candidates(
        project_id=project_id,
        scope=scope,
        entity=entity,
        route_name=route_name,
        source_entity=source_entity,
        target_entity=target_entity,
        target_id=target_id,
        direction=direction,
        field_name_pattern=field_name_pattern,
        min_source_count=min_source_count,
        max_suggestions=max_suggestions,
    )
