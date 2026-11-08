from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    document_id: str
    document_name: str
    chunk_id: str
    content_hash: str
    parser_version: str
    page: int | None = None
    section: str | None = None
    heading: str | None = None
    char_offset: int | None = None
    snippet: str


class IngestResult(BaseModel):
    success: bool = True
    tool_name: str = "ingest_document"
    project_id: str
    document_id: str
    document_name: str
    doc_type: str
    section_count: int
    field_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class DocumentSummary(BaseModel):
    document_id: str
    name: str
    doc_type: str
    section_count: int
    field_count: int = 0
    tags: list[str] = Field(default_factory=list)
    description: str | None = None
    ingested_at: str


class DocumentList(BaseModel):
    success: bool = True
    tool_name: str = "list_documents"
    project_id: str
    documents: list[DocumentSummary]
    warnings: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    document_id: str
    document_name: str
    chunk_id: str
    score: float
    snippet: str
    citation: Citation


class SearchResults(BaseModel):
    success: bool = True
    tool_name: str = "search_documents"
    project_id: str
    query: str
    results: list[SearchResult]
    result_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class EvidenceChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    doc_type: str
    section: str | None
    heading: str | None
    page: int | None
    char_offset: int | None
    content: str
    content_hash: str
    parser_version: str
    score: float
    citation: Citation


class EvidenceResult(BaseModel):
    success: bool = True
    tool_name: str = "get_evidence"
    project_id: str
    query: str
    chunks: list[EvidenceChunk]
    chunk_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class DocumentContent(BaseModel):
    success: bool = True
    tool_name: str = "read_document"
    project_id: str
    document_id: str
    document_name: str
    text: str
    citations: list[Citation]
    warnings: list[str] = Field(default_factory=list)


class FieldCatalogEntry(BaseModel):
    name: str
    type: str | None = None
    length: int | None = None
    precision: int | None = None
    scale: int | None = None
    nullable: bool | None = None
    description: str | None = None
    source_document: str
    source_location: str
    entity: str | None = None


class FieldCatalog(BaseModel):
    success: bool = True
    tool_name: str = "read_field_catalog"
    project_id: str
    fields: list[FieldCatalogEntry]
    warnings: list[str] = Field(default_factory=list)


class DeleteResult(BaseModel):
    success: bool = True
    tool_name: str = "delete_document"
    project_id: str
    document_id: str
    document_name: str
    warnings: list[str] = Field(default_factory=list)


class PurgeResult(BaseModel):
    success: bool = True
    tool_name: str = "purge_document"
    project_id: str
    document_id: str
    document_name: str
    warnings: list[str] = Field(default_factory=list)


class ConflictingChunkPair(BaseModel):
    document_a_id: str
    document_a_name: str
    chunk_a: EvidenceChunk
    document_b_id: str
    document_b_name: str
    chunk_b: EvidenceChunk
    conflict_signal: str


class ConflictResult(BaseModel):
    success: bool = True
    tool_name: str = "find_conflicts"
    project_id: str
    query: str
    conflict_pairs: list[ConflictingChunkPair]
    conflict_count: int = 0
    searched_chunks: int = 0
    warnings: list[str] = Field(default_factory=list)


class ProjectSearchResult(BaseModel):
    project_id: str
    results: list[SearchResult]
    result_count: int = 0


class CrossProjectSearchResults(BaseModel):
    success: bool = True
    tool_name: str = "search_across_projects"
    query: str
    projects_searched: int = 0
    projects_with_results: int = 0
    by_project: list[ProjectSearchResult]
    total_result_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class FieldEvidence(BaseModel):
    document_id: str
    document_name: str
    doc_type: str
    field_type: str | None
    nullable: bool | None
    description: str | None
    source_location: str
    length: int | None = None
    precision: int | None = None
    scale: int | None = None


class FieldSuggestion(BaseModel):
    suggestion_id: str
    status: Literal["pending", "accepted", "edited", "rejected"]
    field_name: str
    entity: str | None
    suggested_type: str | None
    suggested_nullable: bool | None
    suggested_description: str | None
    suggested_length: int | None = None
    suggested_precision: int | None = None
    suggested_scale: int | None = None
    source_count: int
    consistency_score: float
    conflict_hint: str | None
    manifest_path_hint: str
    evidence: list[FieldEvidence]


class ManifestSuggestion(BaseModel):
    suggestion_id: str
    suggestion_type: str
    project_id: str
    status: Literal["pending", "accepted", "edited", "rejected"]
    confidence: float
    confidence_basis: str
    title: str
    summary: str
    rationale: str
    target_step: str
    manifest_path: str
    payload: dict[str, Any]
    citations: list[Citation] = Field(default_factory=list)
    source_document_ids: list[str] = Field(default_factory=list)
    entity: str | None = None
    field: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    edited_payload: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class SuggestFieldsResult(BaseModel):
    success: bool = True
    tool_name: str = "suggest_fields"
    project_id: str
    entity: str | None
    suggestions: list[FieldSuggestion]
    suggestion_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class SuggestManifestCandidatesResult(BaseModel):
    success: bool = True
    tool_name: str = "suggest_manifest_candidates"
    project_id: str
    scope: str
    entity: str | None = None
    suggestions: list[FieldSuggestion | ManifestSuggestion]
    suggestion_count: int = 0
    source_document_count: int = 0
    unsupported_scope: bool = False
    warnings: list[str] = Field(default_factory=list)


class SuggestionDecision(BaseModel):
    suggestion_id: str
    status: Literal["accepted", "edited", "rejected"]
    edited_payload: dict[str, Any] | None = None


class SuggestionDecisionOutcome(BaseModel):
    suggestion_id: str
    status: Literal["accepted", "edited", "rejected"]
    success: bool
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class SubmitSuggestionDecisionsResult(BaseModel):
    success: bool = True
    tool_name: str = "submit_suggestion_decisions"
    project_id: str
    outcomes: list[SuggestionDecisionOutcome]
    outcome_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class FieldDefinitionRow(BaseModel):
    document_id: str
    document_name: str
    doc_type: str
    entity_name: str | None
    field_type: str | None
    nullable: bool | None
    description: str | None
    length: int | None = None
    precision: int | None = None
    scale: int | None = None
    source_location: str
    ingested_at: str


class FieldComparisonResult(BaseModel):
    success: bool = True
    tool_name: str = "compare_field_definitions"
    project_id: str
    field_name: str
    definitions: list[FieldDefinitionRow]
    definition_count: int = 0
    has_conflicts: bool = False
    conflict_summary: str | None = None
    warnings: list[str] = Field(default_factory=list)


class FieldEvidenceChain(BaseModel):
    success: bool = True
    tool_name: str = "get_field_evidence_chain"
    project_id: str
    field_name: str
    entity: str | None = None
    suggestion: FieldSuggestion | None = None
    definitions: list[FieldDefinitionRow] = Field(default_factory=list)
    evidence_chunks: list[EvidenceChunk] = Field(default_factory=list)
    has_conflicts: bool = False
    conflict_summary: str | None = None
    source_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class SuggestionEvidenceChain(BaseModel):
    success: bool = True
    tool_name: str = "get_suggestion_evidence_chain"
    project_id: str
    suggestion_id: str
    scope: str
    field_name: str | None = None
    entity: str | None = None
    suggestion: FieldSuggestion | ManifestSuggestion | None = None
    definitions: list[FieldDefinitionRow] = Field(default_factory=list)
    evidence_chunks: list[EvidenceChunk] = Field(default_factory=list)
    has_conflicts: bool = False
    conflict_summary: str | None = None
    source_count: int = 0
    unsupported_scope: bool = False
    warnings: list[str] = Field(default_factory=list)
