from __future__ import annotations

from knowledge_server.models import FieldCatalog
from knowledge_server.storage import KnowledgeStore


def read_field_catalog(
    *,
    store: KnowledgeStore,
    project_id: str,
    source: str | None = None,
    entity: str | None = None,
) -> FieldCatalog:
    return store.read_field_catalog(project_id=project_id, source=source, entity=entity)
