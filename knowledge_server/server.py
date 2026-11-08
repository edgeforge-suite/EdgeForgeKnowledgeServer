"""MCP server registration for the current 16-tool Knowledge Server surface."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import fastmcp
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.exceptions import ValidationError as FastMCPValidationError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from pydantic import ValidationError as PydanticValidationError

from knowledge_server.models import SuggestionDecision
from knowledge_server.safety import allowed_roots_from_env, shared_mode_enabled
from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.compare import (
    compare_field_definitions as compare_field_definitions_tool,
)
from knowledge_server.tools.conflicts import find_conflicts as find_conflicts_tool
from knowledge_server.tools.decisions import (
    submit_suggestion_decisions as submit_suggestion_decisions_tool,
)
from knowledge_server.tools.delete import (
    delete_document as delete_document_tool,
)
from knowledge_server.tools.delete import (
    purge_document as purge_document_tool,
)
from knowledge_server.tools.evidence import get_evidence as get_evidence_tool
from knowledge_server.tools.evidence_chain import (
    get_field_evidence_chain as get_field_evidence_chain_tool,
)
from knowledge_server.tools.evidence_chain import (
    get_suggestion_evidence_chain as get_suggestion_evidence_chain_tool,
)
from knowledge_server.tools.field_catalog import read_field_catalog as read_field_catalog_tool
from knowledge_server.tools.ingest import ingest_document as ingest_document_tool
from knowledge_server.tools.portfolio import (
    search_across_projects as search_across_projects_tool,
)
from knowledge_server.tools.read import read_document as read_document_tool
from knowledge_server.tools.search import (
    list_documents as list_documents_tool,
)
from knowledge_server.tools.search import (
    search_documents as search_documents_tool,
)
from knowledge_server.tools.suggest import (
    suggest_fields as suggest_fields_tool,
)
from knowledge_server.tools.suggest import (
    suggest_manifest_candidates as suggest_manifest_candidates_tool,
)


class _ValidationErrorSanitizingMiddleware(Middleware):
    """Prevent validated tool arguments from being reflected to MCP clients."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        try:
            return await call_next(context)
        except (PydanticValidationError, FastMCPValidationError):
            raise ToolError(f"Invalid arguments for tool {context.message.name!r}") from None


mcp = FastMCP(
    "edgeforge-knowledge-server",
    mask_error_details=True,
    middleware=[_ValidationErrorSanitizingMiddleware()],
)


def _store() -> KnowledgeStore:
    return KnowledgeStore(_resolve_db_path())


def _resolve_db_path() -> str:
    db_path = os.environ.get("EDGEFORGE_KS_DB_PATH")
    if db_path and db_path.strip():
        return db_path
    if shared_mode_enabled():
        raise RuntimeError(
            "EDGEFORGE_KS_DB_PATH is required when EDGEFORGE_SHARED_MODE is enabled; "
            "set a per-session KS database path."
        )
    return str(Path.cwd() / "edgeforge_knowledge.sqlite3")


@mcp.tool()
def ingest_document(
    project_id: str,
    file_path: str,
    doc_type: str,
    tags: list[str] | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Ingest a local Markdown, CSV, SQL, Excel, PDF, or DOCX document into a project knowledge base.

    Data handling notice: submit only synthetic or approved content. Knowledge Server does not
    sanitize, anonymize, or redact sensitive information in submitted documents. Extracted content
    is persisted in the configured local SQLite store.
    """
    store = _store()
    try:
        result = ingest_document_tool(
            store=store,
            allowed_roots=allowed_roots_from_env(),
            project_id=project_id,
            file_path=file_path,
            doc_type=doc_type,
            tags=tags,
            description=description,
        )
        return result.model_dump()
    finally:
        store.close()


@mcp.tool()
def list_documents(
    project_id: str,
    doc_type: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """List project-scoped documents, optionally filtered by type or tags."""
    store = _store()
    try:
        return list_documents_tool(
            store=store, project_id=project_id, doc_type=doc_type, tags=tags
        ).model_dump()
    finally:
        store.close()


@mcp.tool()
def search_documents(
    project_id: str,
    query: str,
    doc_types: list[str] | None = None,
    max_results: int = 20,
    min_score: float | None = None,
) -> dict[str, Any]:
    """Run deterministic SQLite FTS5/BM25 search across project-scoped documents."""
    store = _store()
    try:
        return search_documents_tool(
            store=store,
            project_id=project_id,
            query=query,
            doc_types=doc_types,
            max_results=max_results,
            min_score=min_score,
        ).model_dump()
    finally:
        store.close()


@mcp.tool()
def get_evidence(
    project_id: str,
    query: str,
    doc_types: list[str] | None = None,
    max_chunks: int = 10,
    min_score: float | None = None,
) -> dict[str, Any]:
    """Return full evidence chunks with citations for post-generation traceability."""
    store = _store()
    try:
        return get_evidence_tool(
            store=store,
            project_id=project_id,
            query=query,
            doc_types=doc_types,
            max_chunks=max_chunks,
            min_score=min_score,
        ).model_dump()
    finally:
        store.close()


@mcp.tool()
def find_conflicts(
    project_id: str,
    query: str,
    doc_types: list[str] | None = None,
    max_chunks_to_search: int = 40,
    min_score: float | None = None,
) -> dict[str, Any]:
    """Detect documents that address the same query topic and surface potential contradictions for human review."""
    store = _store()
    try:
        return find_conflicts_tool(
            store=store,
            project_id=project_id,
            query=query,
            doc_types=doc_types,
            max_chunks_to_search=max_chunks_to_search,
            min_score=min_score,
        ).model_dump()
    finally:
        store.close()


@mcp.tool()
def read_document(
    project_id: str,
    document_id: str,
    section: str | None = None,
) -> dict[str, Any]:
    """Return full extracted document text or a named section/page from an ingested document."""
    store = _store()
    try:
        return read_document_tool(
            store=store, project_id=project_id, document_id=document_id, section=section
        ).model_dump()
    finally:
        store.close()


@mcp.tool()
def delete_document(
    project_id: str,
    document_id: str,
) -> dict[str, Any]:
    """Soft-delete a project document while retaining chunk data for audit trail."""
    store = _store()
    try:
        return delete_document_tool(
            store=store,
            project_id=project_id,
            document_id=document_id,
        ).model_dump()
    finally:
        store.close()


@mcp.tool()
def purge_document(
    project_id: str,
    document_id: str,
    confirm_purge: bool = False,
) -> dict[str, Any]:
    """Delete document-scoped records after explicit confirmation, then compact the FTS5
    index and scrub SQLite freelist/WAL storage. Cleanup intent commits with logical deletion
    and remains until cleanup succeeds and intent removal commits. Committed intent survives
    the tested process-interruption scenarios; retry with the same project/document IDs and
    confirmation. Intent removal uses core SQLite zeroing and a checked final checkpoint.
    A process stop between that removal commit and checkpoint can leave ID/time residue
    without same-ID retry state. This is not a power-loss or universal crash-recovery guarantee.
    This does not erase source files, backups, snapshots, or copies held by other processes.
    """
    store = _store()
    try:
        return purge_document_tool(
            store=store,
            project_id=project_id,
            document_id=document_id,
            confirm_purge=confirm_purge,
        ).model_dump()
    finally:
        store.close()


@mcp.tool()
def search_across_projects(
    query: str,
    project_ids: list[str] | None = None,
    doc_types: list[str] | None = None,
    max_results_per_project: int = 5,
    min_score: float | None = None,
) -> dict[str, Any]:
    """Search for relevant content across all indexed projects for portfolio reuse."""
    store = _store()
    try:
        return search_across_projects_tool(
            store=store,
            query=query,
            project_ids=project_ids,
            doc_types=doc_types,
            max_results_per_project=max_results_per_project,
            min_score=min_score,
        ).model_dump()
    finally:
        store.close()


@mcp.tool()
def suggest_fields(
    project_id: str,
    entity: str | None = None,
    field_name_pattern: str | None = None,
    min_source_count: int = 1,
    max_suggestions: int = 50,
) -> dict[str, Any]:
    """Generate deterministic field definition suggestions with evidence and manifest path hints for Studio review."""
    store = _store()
    try:
        return suggest_fields_tool(
            store=store,
            project_id=project_id,
            entity=entity,
            field_name_pattern=field_name_pattern,
            min_source_count=min_source_count,
            max_suggestions=max_suggestions,
        ).model_dump()
    finally:
        store.close()


@mcp.tool()
def suggest_manifest_candidates(
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
) -> dict[str, Any]:
    """Suggest manifest candidates by scope, including identity_role, transforms, mappings, rules, validations, conflicts, and portfolio reuse."""
    store = _store()
    try:
        return suggest_manifest_candidates_tool(
            store=store,
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
        ).model_dump()
    finally:
        store.close()


@mcp.tool()
def submit_suggestion_decisions(
    project_id: str,
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Persist batched manifest-suggestion review decisions for Studio accept/edit/reject flows."""
    store = _store()
    try:
        parsed_decisions = [SuggestionDecision.model_validate(decision) for decision in decisions]
        return submit_suggestion_decisions_tool(
            store=store,
            project_id=project_id,
            decisions=parsed_decisions,
        ).model_dump()
    finally:
        store.close()


@mcp.tool()
def compare_field_definitions(
    project_id: str,
    field_name: str,
    entity: str | None = None,
) -> dict[str, Any]:
    """Compare how a field is defined across all ingested source documents in a project for human review."""
    store = _store()
    try:
        return compare_field_definitions_tool(
            store=store,
            project_id=project_id,
            field_name=field_name,
            entity=entity,
        ).model_dump()
    finally:
        store.close()


@mcp.tool()
def get_field_evidence_chain(
    project_id: str,
    field_name: str,
    entity: str | None = None,
    max_chunks: int = 10,
) -> dict[str, Any]:
    """Return a composed evidence chain for a named field — includes typed suggestion, cross-document definitions, and evidence chunks for Studio review."""
    store = _store()
    try:
        return get_field_evidence_chain_tool(
            store=store,
            project_id=project_id,
            field_name=field_name,
            entity=entity,
            max_chunks=max_chunks,
        ).model_dump()
    finally:
        store.close()


@mcp.tool()
def get_suggestion_evidence_chain(
    project_id: str,
    suggestion_id: str,
    scope: str = "fields",
    max_chunks: int = 10,
) -> dict[str, Any]:
    """Return evidence for a persisted field, validation, rule, cross-entity-rule, mapping, transform, conflict-resolution, portfolio-reuse, or identity-role suggestion."""
    store = _store()
    try:
        return get_suggestion_evidence_chain_tool(
            store=store,
            project_id=project_id,
            suggestion_id=suggestion_id,
            scope=scope,
            max_chunks=max_chunks,
        ).model_dump()
    finally:
        store.close()


@mcp.tool()
def read_field_catalog(
    project_id: str,
    source: str | None = None,
    entity: str | None = None,
) -> dict[str, Any]:
    """Read structured fields extracted from CSV, SQL, or Excel field dictionaries."""
    store = _store()
    try:
        return read_field_catalog_tool(
            store=store, project_id=project_id, source=source, entity=entity
        ).model_dump()
    finally:
        store.close()


def main() -> None:
    """Run the local stdio MCP server."""
    fastmcp.settings.check_for_updates = "off"
    mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
