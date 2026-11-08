from __future__ import annotations

from knowledge_server.models import FieldComparisonResult
from knowledge_server.storage import KnowledgeStore


def compare_field_definitions(
    *,
    store: KnowledgeStore,
    project_id: str,
    field_name: str,
    entity: str | None = None,
) -> FieldComparisonResult:
    return store.compare_field_definitions(
        project_id=project_id,
        field_name=field_name,
        entity=entity,
    )
