from __future__ import annotations

import hashlib
import itertools
import json
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge_server.models import (
    Citation,
    ConflictingChunkPair,
    ConflictResult,
    CrossProjectSearchResults,
    DeleteResult,
    DocumentContent,
    DocumentList,
    DocumentSummary,
    EvidenceChunk,
    EvidenceResult,
    FieldCatalog,
    FieldCatalogEntry,
    FieldComparisonResult,
    FieldDefinitionRow,
    FieldEvidence,
    FieldEvidenceChain,
    FieldSuggestion,
    ManifestSuggestion,
    ProjectSearchResult,
    PurgeResult,
    SearchResult,
    SearchResults,
    SubmitSuggestionDecisionsResult,
    SuggestFieldsResult,
    SuggestionDecision,
    SuggestionDecisionOutcome,
    SuggestionEvidenceChain,
    SuggestManifestCandidatesResult,
)
from knowledge_server.parsers.csv_parser import CsvField
from knowledge_server.parsers.markdown_parser import TextChunk


class KnowledgeStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.row_factory = sqlite3.Row
        self._initialize()

    def close(self) -> None:
        self.conn.close()

    def _initialize(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                file_path TEXT,
                ingested_at TEXT NOT NULL,
                section_count INTEGER NOT NULL,
                field_count INTEGER NOT NULL DEFAULT 0,
                tags TEXT NOT NULL DEFAULT '[]',
                description TEXT,
                deleted_at TEXT
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks USING fts5(
                chunk_id,
                document_id,
                project_id UNINDEXED,
                section UNINDEXED,
                heading UNINDEXED,
                char_offset UNINDEXED,
                content_hash UNINDEXED,
                parser_version UNINDEXED,
                content,
                tokenize = 'porter unicode61'
            );

            CREATE TABLE IF NOT EXISTS field_catalog (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                entity_name TEXT,
                field_name TEXT NOT NULL,
                field_type TEXT,
                length INTEGER,
                precision INTEGER,
                scale INTEGER,
                nullable INTEGER,
                description TEXT,
                source_location TEXT,
                source_metadata TEXT NOT NULL DEFAULT '{}'
            );
            """
        )
        self._ensure_field_catalog_metadata_column()
        self._ensure_suggestion_table()
        self._ensure_purge_scrub_pending_table()
        self.conn.commit()

    def _ensure_field_catalog_metadata_column(self) -> None:
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(field_catalog)").fetchall()
        }
        if "source_metadata" not in columns:
            self.conn.execute(
                "ALTER TABLE field_catalog ADD COLUMN source_metadata TEXT NOT NULL DEFAULT '{}'"
            )

    def _ensure_suggestion_table(self) -> None:
        legacy_exists = self._table_exists("field_suggestions")
        current_exists = self._table_exists("manifest_suggestions")

        if legacy_exists and not current_exists:
            self.conn.execute("ALTER TABLE field_suggestions RENAME TO manifest_suggestions")
        elif not legacy_exists and not current_exists:
            self._create_manifest_suggestions_table()
        elif legacy_exists and current_exists:
            legacy_count = self._table_row_count("field_suggestions")
            current_count = self._table_row_count("manifest_suggestions")
            if legacy_count == 0:
                self.conn.execute("DROP TABLE field_suggestions")
            elif current_count == 0:
                self.conn.execute("DROP TABLE manifest_suggestions")
                self.conn.execute("ALTER TABLE field_suggestions RENAME TO manifest_suggestions")
            else:
                raise RuntimeError(
                    "Cannot migrate suggestion storage: both field_suggestions and "
                    "manifest_suggestions contain data."
                )

        self.conn.execute("DROP INDEX IF EXISTS idx_field_suggestions_project")
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_manifest_suggestions_project
            ON manifest_suggestions(project_id)
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_manifest_suggestions_type
            ON manifest_suggestions(suggestion_type)
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_manifest_suggestions_scope
            ON manifest_suggestions(project_id, suggestion_type, entity_name)
            """
        )
        self._ensure_manifest_suggestion_review_state_table()

    def _create_manifest_suggestions_table(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE manifest_suggestions (
                suggestion_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                suggestion_type TEXT NOT NULL,
                entity_name TEXT,
                field_name TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'edited', 'rejected')),
                edited_payload TEXT,
                suggestion_payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                reviewed_at TEXT
            )
            """
        )

    def _ensure_manifest_suggestion_review_state_table(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS manifest_suggestion_review_state (
                suggestion_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                suggestion_type TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('accepted', 'edited', 'rejected')),
                edited_payload TEXT,
                source_document_ids TEXT NOT NULL DEFAULT '[]',
                reviewed_at TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (project_id, suggestion_id)
            )
            """
        )
        columns = {
            row["name"]
            for row in self.conn.execute(
                "PRAGMA table_info(manifest_suggestion_review_state)"
            ).fetchall()
        }
        if "source_document_ids" not in columns:
            self.conn.execute(
                """
                ALTER TABLE manifest_suggestion_review_state
                ADD COLUMN source_document_ids TEXT NOT NULL DEFAULT '[]'
                """
            )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_manifest_suggestion_review_state_type
            ON manifest_suggestion_review_state(project_id, suggestion_type)
            """
        )

    def _ensure_purge_scrub_pending_table(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS purge_scrub_pending (
                project_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_warning TEXT,
                PRIMARY KEY (project_id, document_id)
            )
            """
        )

    def _table_exists(self, table_name: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    def _table_row_count(self, table_name: str) -> int:
        row = self.conn.execute(f"SELECT COUNT(*) AS row_count FROM {table_name}").fetchone()
        return int(row["row_count"])

    def _document_exists(self, *, project_id: str, document_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1
            FROM documents
            WHERE project_id = ? AND id = ?
            """,
            (project_id, document_id),
        ).fetchone()
        return row is not None

    def _document_content_fingerprint(self, document_id: str) -> tuple[str, ...]:
        chunk_rows = self.conn.execute(
            """
            SELECT content_hash
            FROM document_chunks
            WHERE document_id = ?
            ORDER BY rowid
            """,
            (document_id,),
        ).fetchall()
        field_rows = self.conn.execute(
            """
            SELECT
                entity_name,
                field_name,
                field_type,
                length,
                precision,
                scale,
                nullable,
                description,
                source_location,
                source_metadata
            FROM field_catalog
            WHERE document_id = ?
            ORDER BY entity_name, field_name, source_location, id
            """,
            (document_id,),
        ).fetchall()
        chunk_fingerprint = tuple(f"chunk:{row['content_hash']}" for row in chunk_rows)
        field_fingerprint = tuple(
            f"field:{_stable_json_hash(_stored_field_fingerprint_payload(row))}"
            for row in field_rows
        )
        return (*chunk_fingerprint, *field_fingerprint)

    def _invalidate_manifest_suggestions_for_document_change(
        self,
        document_id: str,
        *,
        preserve_review_state: bool = True,
    ) -> None:
        rows = self.conn.execute(
            """
            SELECT
                suggestion_id,
                project_id,
                suggestion_type,
                status,
                edited_payload,
                reviewed_at,
                suggestion_payload
            FROM manifest_suggestions
            """
        ).fetchall()
        stale_ids: list[str] = []
        for row in rows:
            try:
                payload = json.loads(row["suggestion_payload"])
            except (TypeError, json.JSONDecodeError):
                continue
            if _suggestion_payload_references_document(payload, document_id):
                if preserve_review_state:
                    self._preserve_identity_role_review_state(row, payload)
                stale_ids.append(row["suggestion_id"])
        if not stale_ids:
            return
        placeholders = ",".join("?" * len(stale_ids))
        self.conn.execute(
            f"DELETE FROM manifest_suggestions WHERE suggestion_id IN ({placeholders})",
            stale_ids,
        )
        if not preserve_review_state:
            self.conn.execute(
                f"DELETE FROM manifest_suggestion_review_state WHERE suggestion_id IN ({placeholders})",
                stale_ids,
            )

    def _delete_identity_role_review_state_for_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> None:
        rows = self.conn.execute(
            """
            SELECT suggestion_id, source_document_ids
            FROM manifest_suggestion_review_state
            WHERE project_id = ? AND suggestion_type = 'identity_role'
            """,
            (project_id,),
        ).fetchall()
        stale_ids: list[str] = []
        for row in rows:
            try:
                source_document_ids = json.loads(row["source_document_ids"])
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(source_document_ids, list) and document_id in source_document_ids:
                stale_ids.append(row["suggestion_id"])
        if not stale_ids:
            return
        placeholders = ",".join("?" * len(stale_ids))
        self.conn.execute(
            f"""
            DELETE FROM manifest_suggestion_review_state
            WHERE project_id = ? AND suggestion_id IN ({placeholders})
            """,
            [project_id, *stale_ids],
        )

    def _preserve_identity_role_review_state(
        self,
        row: sqlite3.Row,
        payload: dict[str, Any],
    ) -> None:
        if row["suggestion_type"] != "identity_role" or row["status"] == "pending":
            return
        self._upsert_identity_role_review_state(
            project_id=row["project_id"],
            suggestion_id=row["suggestion_id"],
            status=row["status"],
            edited_payload=row["edited_payload"],
            reviewed_at=row["reviewed_at"],
            source_document_ids=sorted(_document_ids_from_suggestion_payload(payload)),
        )

    def _upsert_identity_role_review_state(
        self,
        *,
        project_id: str,
        suggestion_id: str,
        status: str,
        edited_payload: str | None,
        reviewed_at: str | None,
        source_document_ids: list[str] | None = None,
    ) -> None:
        if status == "pending":
            return
        now = datetime.now(timezone.utc).isoformat()
        reviewed_at = reviewed_at or now
        source_document_ids = sorted(set(source_document_ids or []))
        self.conn.execute(
            """
            INSERT INTO manifest_suggestion_review_state (
                suggestion_id,
                project_id,
                suggestion_type,
                status,
                edited_payload,
                source_document_ids,
                reviewed_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, suggestion_id) DO UPDATE SET
                suggestion_type = excluded.suggestion_type,
                status = excluded.status,
                edited_payload = excluded.edited_payload,
                source_document_ids = excluded.source_document_ids,
                reviewed_at = excluded.reviewed_at,
                updated_at = excluded.updated_at
            """,
            (
                suggestion_id,
                project_id,
                "identity_role",
                status,
                edited_payload,
                json.dumps(source_document_ids),
                reviewed_at,
                now,
            ),
        )

    def upsert_document(
        self,
        *,
        project_id: str,
        document_id: str,
        name: str,
        doc_type: str,
        file_path: Path,
        chunks: list[TextChunk],
        tags: list[str],
        description: str | None,
        fields: list[CsvField] | None = None,
    ) -> None:
        fields = fields or []
        now = datetime.now(timezone.utc).isoformat()
        existing_document = self._document_exists(project_id=project_id, document_id=document_id)
        old_fingerprint = self._document_content_fingerprint(document_id)
        new_fingerprint = _document_content_fingerprint(chunks, fields)
        with self.conn:
            if existing_document and old_fingerprint != new_fingerprint:
                self._invalidate_manifest_suggestions_for_document_change(document_id)
            self.conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
            self.conn.execute("DELETE FROM field_catalog WHERE document_id = ?", (document_id,))
            self.conn.execute(
                """
                INSERT OR REPLACE INTO documents (
                    id, project_id, name, doc_type, file_path, ingested_at, section_count,
                    field_count, tags, description, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    document_id,
                    project_id,
                    name,
                    doc_type,
                    str(file_path),
                    now,
                    len(chunks),
                    len(fields),
                    json.dumps(tags),
                    description,
                ),
            )
            for chunk in chunks:
                self.conn.execute(
                    """
                    INSERT INTO document_chunks (
                        chunk_id, document_id, project_id, section, heading, char_offset,
                        content_hash, parser_version, content
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stable_chunk_id(document_id, chunk.position),
                        document_id,
                        project_id,
                        chunk.section,
                        chunk.heading,
                        chunk.char_offset,
                        chunk.content_hash,
                        chunk.parser_version,
                        chunk.content,
                    ),
                )
            for index, field in enumerate(fields):
                self.conn.execute(
                    """
                    INSERT INTO field_catalog (
                        id, project_id, document_id, entity_name, field_name, field_type,
                        length, precision, scale, nullable, description, source_location,
                        source_metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stable_field_id(document_id, index, field.name),
                        project_id,
                        document_id,
                        field.entity,
                        field.name,
                        field.type,
                        field.length,
                        field.precision,
                        field.scale,
                        None if field.nullable is None else int(field.nullable),
                        field.description,
                        field.source_location,
                        json.dumps(field.source_metadata or {}),
                    ),
                )

    def remove_documents_for_path_except(
        self, *, project_id: str, file_path: Path, retain_document_ids: set[str]
    ) -> None:
        with self.conn:
            rows = self.conn.execute(
                "SELECT id FROM documents WHERE project_id = ? AND file_path = ?",
                (project_id, str(file_path)),
            ).fetchall()
            for row in rows:
                document_id = row["id"]
                if document_id in retain_document_ids:
                    continue
                self._invalidate_manifest_suggestions_for_document_change(document_id)
                self.conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
                self.conn.execute("DELETE FROM field_catalog WHERE document_id = ?", (document_id,))
                self.conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    def list_documents(
        self, project_id: str, doc_type: str | None = None, tags: list[str] | None = None
    ) -> DocumentList:
        clauses = ["project_id = ?", "deleted_at IS NULL"]
        params: list[Any] = [project_id]
        if doc_type:
            clauses.append("doc_type = ?")
            params.append(doc_type)
        rows = self.conn.execute(
            f"SELECT * FROM documents WHERE {' AND '.join(clauses)} ORDER BY ingested_at DESC",
            params,
        ).fetchall()
        docs = []
        for row in rows:
            doc_tags = json.loads(row["tags"])
            if tags and not set(tags).issubset(doc_tags):
                continue
            docs.append(
                DocumentSummary(
                    document_id=row["id"],
                    name=row["name"],
                    doc_type=row["doc_type"],
                    section_count=row["section_count"],
                    field_count=row["field_count"],
                    tags=doc_tags,
                    description=row["description"],
                    ingested_at=row["ingested_at"],
                )
            )
        return DocumentList(project_id=project_id, documents=docs)

    def search_documents(
        self,
        project_id: str,
        query: str,
        doc_types: list[str] | None = None,
        max_results: int = 20,
        min_score: float | None = None,
    ) -> SearchResults:
        max_results = max(1, min(max_results, 100))
        safe_query = _normalize_fts_query(query)
        if not safe_query:
            return SearchResults(
                project_id=project_id,
                query=query,
                results=[],
                result_count=0,
                warnings=["Query contained no searchable tokens; returning empty results."],
            )

        rows = self._search_chunk_rows(
            project_id=project_id,
            safe_query=safe_query,
            doc_types=doc_types,
            limit=max_results,
            include_snippet=True,
        )
        results = [
            SearchResult(
                document_id=row["document_id"],
                document_name=row["name"],
                chunk_id=row["chunk_id"],
                score=float(row["score"]),
                snippet=row["snippet"],
                citation=_citation(row, row["snippet"]),
            )
            for row in rows
            if min_score is None or float(row["score"]) <= min_score
        ]
        return SearchResults(
            project_id=project_id,
            query=query,
            results=results,
            result_count=len(results),
        )

    def get_evidence(
        self,
        project_id: str,
        query: str,
        doc_types: list[str] | None = None,
        max_chunks: int = 10,
        min_score: float | None = None,
    ) -> EvidenceResult:
        max_chunks = max(1, min(max_chunks, 50))
        safe_query = _normalize_fts_query(query)
        if not safe_query:
            return EvidenceResult(
                project_id=project_id,
                query=query,
                chunks=[],
                chunk_count=0,
                warnings=["Query contained no searchable tokens; returning empty results."],
            )

        rows = self._search_chunk_rows(
            project_id=project_id,
            safe_query=safe_query,
            doc_types=doc_types,
            limit=max_chunks,
            include_snippet=False,
        )
        chunks = [
            EvidenceChunk(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                document_name=row["name"],
                doc_type=row["doc_type"],
                section=row["section"],
                heading=row["heading"],
                page=_page_from_section(row["section"], row["parser_version"]),
                char_offset=row["char_offset"],
                content=row["content"],
                content_hash=row["content_hash"],
                parser_version=row["parser_version"],
                score=float(row["score"]),
                citation=_citation(row, row["content"]),
            )
            for row in rows
            if min_score is None or float(row["score"]) <= min_score
        ]
        return EvidenceResult(
            project_id=project_id,
            query=query,
            chunks=chunks,
            chunk_count=len(chunks),
        )

    def read_document(
        self, project_id: str, document_id: str, section: str | None = None
    ) -> DocumentContent:
        doc = self._find_document(project_id, document_id)
        if doc is None:
            return DocumentContent(
                success=False,
                project_id=project_id,
                document_id=document_id,
                document_name="",
                text="",
                citations=[],
                warnings=[f"document not found for project_id {project_id}: {document_id}"],
            )
        clauses = ["document_id = ?", "project_id = ?"]
        params: list[Any] = [document_id, project_id]
        if section:
            clauses.append("section = ?")
            params.append(section)
        rows = self.conn.execute(
            f"SELECT * FROM document_chunks WHERE {' AND '.join(clauses)} ORDER BY rowid",
            params,
        ).fetchall()
        if section and not rows:
            return DocumentContent(
                success=False,
                project_id=project_id,
                document_id=document_id,
                document_name=doc["name"],
                text="",
                citations=[],
                warnings=[f"section not found for document_id {document_id}: {section}"],
            )
        citations = [_citation({**dict(row), "name": doc["name"]}, row["content"]) for row in rows]
        return DocumentContent(
            project_id=project_id,
            document_id=document_id,
            document_name=doc["name"],
            text="\n\n".join(row["content"] for row in rows),
            citations=citations,
        )

    def read_field_catalog(
        self, project_id: str, source: str | None = None, entity: str | None = None
    ) -> FieldCatalog:
        if source:
            doc = self._find_document(project_id, source)
            if doc is None:
                return FieldCatalog(
                    success=False,
                    project_id=project_id,
                    fields=[],
                    warnings=[f"document not found for project_id {project_id}: {source}"],
                )
        clauses = ["f.project_id = ?", "d.deleted_at IS NULL"]
        params: list[Any] = [project_id]
        if source:
            clauses.append("f.document_id = ?")
            params.append(source)
        if entity:
            clauses.append("f.entity_name = ?")
            params.append(entity)
        rows = self.conn.execute(
            f"""
            SELECT f.*, d.name AS document_name
            FROM field_catalog f
            JOIN documents d ON d.id = f.document_id
            WHERE {' AND '.join(clauses)}
            ORDER BY f.entity_name, f.field_name
            """,
            params,
        ).fetchall()
        return FieldCatalog(
            project_id=project_id,
            fields=[
                FieldCatalogEntry(
                    name=row["field_name"],
                    type=row["field_type"],
                    length=row["length"],
                    precision=row["precision"],
                    scale=row["scale"],
                    nullable=None if row["nullable"] is None else bool(row["nullable"]),
                    description=row["description"],
                    source_document=row["document_id"],
                    source_location=row["source_location"],
                    entity=row["entity_name"],
                )
                for row in rows
            ],
        )

    def delete_document(self, project_id: str, document_id: str) -> DeleteResult:
        row = self._find_document(project_id, document_id)
        if row is None:
            return DeleteResult(
                success=False,
                project_id=project_id,
                document_id=document_id,
                document_name="",
                warnings=[f"document not found or already deleted: {document_id}"],
            )

        deleted_at = datetime.now(timezone.utc).isoformat()
        with self.conn:
            self.conn.execute(
                "UPDATE documents SET deleted_at = ? WHERE id = ? AND project_id = ? AND deleted_at IS NULL",
                (deleted_at, document_id, project_id),
            )
            self._invalidate_manifest_suggestions_for_document_change(
                document_id,
                preserve_review_state=False,
            )
            self._delete_identity_role_review_state_for_document(
                project_id=project_id,
                document_id=document_id,
            )
        return DeleteResult(
            project_id=project_id,
            document_id=document_id,
            document_name=row["name"],
        )

    def purge_document(
        self,
        project_id: str,
        document_id: str,
        confirm_purge: bool = False,
    ) -> PurgeResult:
        if not confirm_purge:
            return PurgeResult(
                success=False,
                project_id=project_id,
                document_id=document_id,
                document_name="",
                warnings=[
                    (
                        "confirm_purge=True is required to delete stored records and scrub document "
                        f"{document_id}."
                    )
                ],
            )

        row = self._find_document_any_state(project_id, document_id)
        if row is None:
            if self._purge_scrub_pending_exists(project_id=project_id, document_id=document_id):
                scrub_warnings = self._finish_purge_scrub(
                    project_id=project_id, document_id=document_id
                )
                return PurgeResult(
                    success=not scrub_warnings,
                    project_id=project_id,
                    document_id=document_id,
                    document_name="",
                    warnings=scrub_warnings,
                )
            return PurgeResult(
                success=False,
                project_id=project_id,
                document_id=document_id,
                document_name="",
                warnings=[f"document not found for purge: {document_id}"],
            )

        with self.conn:
            # Intent and every logical deletion must commit or roll back together.
            self._write_purge_scrub_pending(
                project_id=project_id, document_id=document_id, warnings=[]
            )
            self._invalidate_manifest_suggestions_for_document_change(
                document_id,
                preserve_review_state=False,
            )
            self._delete_identity_role_review_state_for_document(
                project_id=project_id,
                document_id=document_id,
            )
            self.conn.execute(
                "DELETE FROM document_chunks WHERE document_id = ? AND project_id = ?",
                (document_id, project_id),
            )
            self.conn.execute(
                "DELETE FROM field_catalog WHERE document_id = ? AND project_id = ?",
                (document_id, project_id),
            )
            self.conn.execute(
                "DELETE FROM documents WHERE id = ? AND project_id = ?",
                (document_id, project_id),
            )
        scrub_warnings = self._finish_purge_scrub(
            project_id=project_id, document_id=document_id
        )

        return PurgeResult(
            success=not scrub_warnings,
            project_id=project_id,
            document_id=document_id,
            document_name=row["name"],
            warnings=scrub_warnings,
        )

    def _finish_purge_scrub(self, *, project_id: str, document_id: str) -> list[str]:
        warnings = self._scrub_sqlite_storage_after_purge()
        try:
            if warnings:
                self._mark_purge_scrub_pending(
                    project_id=project_id, document_id=document_id, warnings=warnings
                )
            else:
                warnings = self._clear_purge_scrub_pending(
                    project_id=project_id, document_id=document_id
                )
                if warnings:
                    self._mark_purge_scrub_pending(
                        project_id=project_id, document_id=document_id, warnings=warnings
                    )
        except sqlite3.DatabaseError:
            self.conn.rollback()
            warnings.append("purge cleanup state could not be finalized.")
            # Clear may already have committed before its final checkpoint failed.
            # Rollback alone cannot restore retry state in that case.
            pending = False
            try:
                pending = self._purge_scrub_pending_exists(
                    project_id=project_id, document_id=document_id
                )
                if not pending:
                    self._mark_purge_scrub_pending(
                        project_id=project_id, document_id=document_id, warnings=warnings
                    )
                    pending = True
            except sqlite3.DatabaseError:
                self.conn.rollback()
            warnings.append(
                "pending cleanup intent remains. Retry purge_document with the same "
                "project/document IDs and confirm_purge=True."
                if pending
                else "pending cleanup intent could not be restored or verified; "
                "same-ID retry availability is not guaranteed."
            )
        return warnings

    def _scrub_sqlite_storage_after_purge(self) -> list[str]:
        self.conn.commit()
        previous_busy_timeout = int(self.conn.execute("PRAGMA busy_timeout").fetchone()[0])
        self.conn.execute("PRAGMA busy_timeout = 50")
        try:
            self._compact_fts_index_after_purge()
            last_checkpoint: tuple[int, int, int] | None = None
            for _ in range(4):
                last_checkpoint = self._wal_checkpoint_truncate()
                if last_checkpoint[0] == 0:
                    self.conn.execute("VACUUM")
                    last_checkpoint = self._wal_checkpoint_truncate()
                    if last_checkpoint[0] == 0:
                        return []
                time.sleep(0.05)
            checkpoint_summary = (
                f"busy={last_checkpoint[0]}, log={last_checkpoint[1]}, "
                f"checkpointed={last_checkpoint[2]}"
                if last_checkpoint is not None
                else "no checkpoint result"
            )
            return [
                (
                    "purge removed logical rows, but SQLite storage scrub could not "
                    "complete because WAL truncation is blocked by another connection "
                    f"({checkpoint_summary}). Close open SQLite readers and retry "
                    "purge_document with the same project/document IDs and confirm_purge=True."
                )
            ]
        except sqlite3.DatabaseError as exc:
            self.conn.rollback()
            return [
                (
                    "purge removed logical rows, but SQLite storage scrub did not "
                    f"complete: {exc}. Close competing SQLite connections and retry "
                    "purge_document with the same project/document IDs and confirm_purge=True."
                )
            ]
        finally:
            self.conn.execute(f"PRAGMA busy_timeout = {previous_busy_timeout}")

    def _compact_fts_index_after_purge(self) -> None:
        # Merge delete-keys out of every segment before reclaiming pages/WAL.
        # Unlike FTS5 secure-delete, optimize retains pre-3.42 file compatibility.
        with self.conn:
            self.conn.execute("INSERT INTO document_chunks(document_chunks) VALUES('optimize')")

    def _wal_checkpoint_truncate(self) -> tuple[int, int, int]:
        row = self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        return int(row[0]), int(row[1]), int(row[2])

    def _purge_scrub_pending_exists(self, *, project_id: str, document_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1
            FROM purge_scrub_pending
            WHERE project_id = ? AND document_id = ?
            """,
            (project_id, document_id),
        ).fetchone()
        return row is not None

    def _mark_purge_scrub_pending(
        self,
        *,
        project_id: str,
        document_id: str,
        warnings: list[str],
    ) -> None:
        with self.conn:
            self._write_purge_scrub_pending(
                project_id=project_id, document_id=document_id, warnings=warnings
            )

    def _write_purge_scrub_pending(
        self, *, project_id: str, document_id: str, warnings: list[str]
    ) -> None:
        # Transaction-neutral: the caller owns commit/rollback, including initial deletion.
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO purge_scrub_pending (
                project_id, document_id, created_at, updated_at, last_warning
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id, document_id) DO UPDATE SET
                updated_at = excluded.updated_at,
                last_warning = excluded.last_warning
            """,
            (project_id, document_id, now, now, warnings[0] if warnings else None),
        )

    def _clear_purge_scrub_pending(self, *, project_id: str, document_id: str) -> list[str]:
        previous_secure_delete = int(self.conn.execute("PRAGMA secure_delete").fetchone()[0])
        previous_busy_timeout = int(self.conn.execute("PRAGMA busy_timeout").fetchone()[0])
        try:
            # Core SQLite zeroing, not the incompatible FTS5 secure-delete option.
            self.conn.execute("PRAGMA secure_delete = ON")
            self.conn.execute("PRAGMA busy_timeout = 50")
            with self.conn:
                self.conn.execute(
                    """
                    DELETE FROM purge_scrub_pending
                    WHERE project_id = ? AND document_id = ?
                    """,
                    (project_id, document_id),
                )
            for _ in range(4):
                checkpoint = self._wal_checkpoint_truncate()
                if checkpoint[0] == 0:
                    return []
                time.sleep(0.05)
            return [
                "purge cleanup intent metadata checkpoint could not complete because "
                "WAL truncation is blocked by another connection "
                f"(busy={checkpoint[0]}, log={checkpoint[1]}, checkpointed={checkpoint[2]}). "
                "Close open SQLite readers and retry purge_document with the same "
                "project/document IDs and confirm_purge=True."
            ]
        finally:
            secure_delete_setting = {0: "OFF", 1: "ON", 2: "FAST"}[previous_secure_delete]
            self.conn.execute(f"PRAGMA secure_delete = {secure_delete_setting}")
            self.conn.execute(f"PRAGMA busy_timeout = {previous_busy_timeout}")

    def find_conflicts(
        self,
        project_id: str,
        query: str,
        doc_types: list[str] | None = None,
        max_chunks_to_search: int = 40,
        min_score: float | None = None,
    ) -> ConflictResult:
        max_chunks_to_search = max(10, min(max_chunks_to_search, 100))
        safe_query = _normalize_fts_query(query)
        if not safe_query:
            return ConflictResult(
                project_id=project_id,
                query=query,
                conflict_pairs=[],
                conflict_count=0,
                searched_chunks=0,
                warnings=["Query contained no searchable tokens; returning empty results."],
            )

        rows = self._search_chunk_rows(
            project_id=project_id,
            safe_query=safe_query,
            doc_types=doc_types,
            limit=max_chunks_to_search,
            include_snippet=False,
        )
        filtered_rows = [
            row for row in rows if min_score is None or float(row["score"]) <= min_score
        ]
        rows_by_document: dict[str, list[sqlite3.Row]] = {}
        for row in filtered_rows:
            rows_by_document.setdefault(row["document_id"], []).append(row)

        if len(rows_by_document) < 2:
            return ConflictResult(
                project_id=project_id,
                query=query,
                conflict_pairs=[],
                conflict_count=0,
                searched_chunks=len(filtered_rows),
                warnings=["No conflicts detected — fewer than 2 documents matched the query."],
            )

        pairs: list[ConflictingChunkPair] = []
        for document_a_id, document_b_id in itertools.combinations(sorted(rows_by_document), 2):
            row_a = min(rows_by_document[document_a_id], key=lambda row: float(row["score"]))
            row_b = min(rows_by_document[document_b_id], key=lambda row: float(row["score"]))
            pairs.append(
                ConflictingChunkPair(
                    document_a_id=document_a_id,
                    document_a_name=row_a["name"],
                    chunk_a=self._evidence_chunk_from_row(row_a),
                    document_b_id=document_b_id,
                    document_b_name=row_b["name"],
                    chunk_b=self._evidence_chunk_from_row(row_b),
                    conflict_signal=(
                        f"Both '{row_a['name']}' and '{row_b['name']}' contain relevant "
                        f"content for query '{query}'"
                    ),
                )
            )

        pairs.sort(
            key=lambda pair: abs(pair.chunk_a.score) + abs(pair.chunk_b.score),
            reverse=True,
        )
        return ConflictResult(
            project_id=project_id,
            query=query,
            conflict_pairs=pairs,
            conflict_count=len(pairs),
            searched_chunks=len(filtered_rows),
        )

    def search_across_projects(
        self,
        query: str,
        project_ids: list[str] | None = None,
        doc_types: list[str] | None = None,
        max_results_per_project: int = 5,
        min_score: float | None = None,
    ) -> CrossProjectSearchResults:
        max_results_per_project = max(1, min(max_results_per_project, 20))
        safe_query = _normalize_fts_query(query)
        if not safe_query:
            return CrossProjectSearchResults(
                query=query,
                projects_searched=0 if project_ids is None else len(project_ids),
                projects_with_results=0,
                by_project=[],
                total_result_count=0,
                warnings=["Query contained no searchable tokens; returning empty results."],
            )

        if project_ids is None:
            project_rows = self.conn.execute(
                """
                SELECT DISTINCT project_id
                FROM documents
                WHERE deleted_at IS NULL
                ORDER BY project_id
                """
            ).fetchall()
            project_ids = [row["project_id"] for row in project_rows]

        by_project: list[ProjectSearchResult] = []
        total_result_count = 0
        for project_id in project_ids:
            rows = self._search_chunk_rows(
                project_id=project_id,
                safe_query=safe_query,
                doc_types=doc_types,
                limit=max_results_per_project,
                include_snippet=True,
            )
            filtered_rows = [
                row for row in rows if min_score is None or float(row["score"]) <= min_score
            ]
            results = [
                SearchResult(
                    document_id=row["document_id"],
                    document_name=row["name"],
                    chunk_id=row["chunk_id"],
                    score=float(row["score"]),
                    snippet=row["snippet"],
                    citation=_citation(row, row["snippet"]),
                )
                for row in filtered_rows
            ]
            if not results:
                continue
            by_project.append(
                ProjectSearchResult(
                    project_id=project_id,
                    results=results,
                    result_count=len(results),
                )
            )
            total_result_count += len(results)

        return CrossProjectSearchResults(
            query=query,
            projects_searched=len(project_ids),
            projects_with_results=len(by_project),
            by_project=by_project,
            total_result_count=total_result_count,
        )

    def suggest_fields(
        self,
        project_id: str,
        entity: str | None = None,
        field_name_pattern: str | None = None,
        min_source_count: int = 1,
        max_suggestions: int = 50,
    ) -> SuggestFieldsResult:
        min_source_count = max(1, min(min_source_count, 10))
        max_suggestions = max(1, min(max_suggestions, 200))
        clauses = ["f.project_id = ?", "d.deleted_at IS NULL"]
        params: list[Any] = [project_id]
        if entity:
            clauses.append("f.entity_name = ?")
            params.append(entity)
        if field_name_pattern:
            clauses.append("LOWER(f.field_name) LIKE LOWER(?)")
            params.append(f"%{field_name_pattern}%")
        rows = self.conn.execute(
            f"""
            SELECT f.*, d.name AS document_name, d.doc_type, d.ingested_at
            FROM field_catalog f
            JOIN documents d ON d.id = f.document_id
            WHERE {' AND '.join(clauses)}
            ORDER BY f.entity_name, f.field_name, d.ingested_at
            """,
            params,
        ).fetchall()
        if not rows:
            warning = f"No field catalog entries found for project '{project_id}'."
            if entity:
                warning = f"No field catalog entries found for project '{project_id}' and entity '{entity}'."
            return SuggestFieldsResult(
                project_id=project_id,
                entity=entity,
                suggestions=[],
                suggestion_count=0,
                warnings=[warning],
            )

        groups: dict[tuple[str | None, str], list[sqlite3.Row]] = {}
        for row in rows:
            normalized_field_name = _normalize_field_name(row["field_name"])
            group_entity = entity if entity is not None else _normalize_optional_entity(row["entity_name"])
            groups.setdefault((group_entity, normalized_field_name), []).append(row)

        suggestions: list[FieldSuggestion] = []
        for group_rows in groups.values():
            evidence = [self._field_evidence_from_row(row) for row in group_rows]
            if len(evidence) < min_source_count:
                continue
            suggested_type = _most_common_value([item.field_type for item in evidence])
            suggested_nullable = _most_common_value([item.nullable for item in evidence])
            suggested_length = _most_common_value([item.length for item in evidence])
            suggested_precision = _most_common_value([item.precision for item in evidence])
            suggested_scale = _most_common_value([item.scale for item in evidence])
            descriptions = [item.description for item in evidence if item.description]
            suggested_description = max(descriptions, key=len) if descriptions else None
            if suggested_type is None:
                consistency_score = 0.0
            else:
                matching_types = sum(1 for item in evidence if item.field_type == suggested_type)
                consistency_score = matching_types / len(evidence)
            conflict_parts = []
            type_conflict = _value_conflict_summary("Type conflict", [row["field_type"] for row in group_rows], [row["document_name"] for row in group_rows])
            if type_conflict:
                conflict_parts.append(type_conflict)
            nullable_conflict = _value_conflict_summary(
                "Nullable conflict",
                [None if row["nullable"] is None else bool(row["nullable"]) for row in group_rows],
                [row["document_name"] for row in group_rows],
            )
            if nullable_conflict:
                conflict_parts.append(nullable_conflict)
            chosen_entity = next((row["entity_name"] for row in group_rows if row["entity_name"]), entity)
            field_name = group_rows[0]["field_name"]
            suggestion_id = stable_field_suggestion_id(project_id, chosen_entity, field_name)
            status = self._load_suggestion_status(project_id, suggestion_id)
            manifest_path_hint = (
                f"{chosen_entity}.fields[name='{field_name}']"
                if chosen_entity
                else f"fields[name='{field_name}']"
            )
            suggestion = FieldSuggestion(
                suggestion_id=suggestion_id,
                status=status,
                field_name=field_name,
                entity=chosen_entity,
                suggested_type=suggested_type,
                suggested_nullable=suggested_nullable,
                suggested_description=suggested_description,
                suggested_length=suggested_length,
                suggested_precision=suggested_precision,
                suggested_scale=suggested_scale,
                source_count=len(evidence),
                consistency_score=consistency_score,
                conflict_hint="; ".join(conflict_parts) or None,
                manifest_path_hint=manifest_path_hint,
                evidence=evidence,
            )
            self._upsert_field_suggestion(project_id=project_id, suggestion=suggestion)
            suggestions.append(suggestion)

        suggestions.sort(
            key=lambda suggestion: (
                -suggestion.consistency_score,
                suggestion.field_name,
                suggestion.entity or "",
            )
        )
        suggestions = suggestions[:max_suggestions]
        return SuggestFieldsResult(
            project_id=project_id,
            entity=entity,
            suggestions=suggestions,
            suggestion_count=len(suggestions),
        )

    def suggest_manifest_candidates(
        self,
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
        supported_scopes = {
            "fields",
            "validations",
            "rules",
            "cross_entity_rules",
            "mappings",
            "conflict_resolution",
            "portfolio_reuse",
            "transforms",
            "identity_role",
        }
        if scope not in supported_scopes:
            return SuggestManifestCandidatesResult(
                success=False,
                project_id=project_id,
                scope=scope,
                entity=entity,
                suggestions=[],
                suggestion_count=0,
                source_document_count=0,
                unsupported_scope=True,
                warnings=[
                    (
                        f"Unsupported suggestion scope '{scope}'. Supported scopes are "
                        "fields, validations, rules, cross_entity_rules, mappings, "
                        "conflict_resolution, portfolio_reuse, transforms, and identity_role."
                    )
                ],
            )

        if scope == "fields":
            result = self.suggest_fields(
                project_id=project_id,
                entity=entity,
                field_name_pattern=field_name_pattern,
                min_source_count=min_source_count,
                max_suggestions=max_suggestions,
            )
            source_document_ids = {
                evidence.document_id
                for suggestion in result.suggestions
                for evidence in suggestion.evidence
            }
            return SuggestManifestCandidatesResult(
                project_id=project_id,
                scope="fields",
                entity=result.entity,
                suggestions=result.suggestions,
                suggestion_count=result.suggestion_count,
                source_document_count=len(source_document_ids),
                warnings=result.warnings,
            )

        max_suggestions = max(1, min(max_suggestions, 200))
        if scope == "validations":
            suggestions, warnings = self._suggest_validation_candidates(
                project_id=project_id,
                entity=entity,
                field_name_pattern=field_name_pattern,
                max_suggestions=max_suggestions,
            )
        elif scope == "rules":
            suggestions, warnings = self._suggest_rule_candidates(
                project_id=project_id,
                entity=entity,
                field_name_pattern=field_name_pattern,
                max_suggestions=max_suggestions,
            )
        elif scope == "cross_entity_rules":
            suggestions, warnings = self._suggest_cross_entity_rule_candidates(
                project_id=project_id,
                entity=entity,
                field_name_pattern=field_name_pattern,
                max_suggestions=max_suggestions,
            )
        elif scope == "mappings":
            suggestions, warnings = self._suggest_mapping_candidates(
                project_id=project_id,
                route_name=route_name,
                source_entity=source_entity,
                target_entity=target_entity,
                direction=direction,
                field_name_pattern=field_name_pattern,
                max_suggestions=max_suggestions,
            )
        elif scope == "transforms":
            suggestions, warnings = self._suggest_transform_candidates(
                project_id=project_id,
                route_name=route_name,
                source_entity=source_entity,
                target_entity=target_entity,
                target_id=target_id,
                direction=direction,
                field_name_pattern=field_name_pattern,
                max_suggestions=max_suggestions,
            )
        elif scope == "conflict_resolution":
            suggestions, warnings = self._suggest_conflict_resolution_candidates(
                project_id=project_id,
                query=field_name_pattern,
                entity=entity,
                route_name=route_name,
                direction=direction,
                max_suggestions=max_suggestions,
            )
        elif scope == "portfolio_reuse":
            suggestions, warnings = self._suggest_portfolio_reuse_candidates(
                project_id=project_id,
                query=field_name_pattern,
                max_suggestions=max_suggestions,
            )
        else:
            suggestions, warnings = self._suggest_identity_role_candidates(
                project_id=project_id,
                entity=entity,
                field_name_pattern=field_name_pattern,
                max_suggestions=max_suggestions,
            )

        source_document_ids = {
            document_id
            for suggestion in suggestions
            for document_id in suggestion.source_document_ids
        }
        return SuggestManifestCandidatesResult(
            project_id=project_id,
            scope=scope,
            entity=entity,
            suggestions=suggestions,
            suggestion_count=len(suggestions),
            source_document_count=len(source_document_ids),
            warnings=warnings,
        )

    def _suggest_validation_candidates(
        self,
        *,
        project_id: str,
        entity: str | None,
        field_name_pattern: str | None,
        max_suggestions: int,
    ) -> tuple[list[ManifestSuggestion], list[str]]:
        rows = self._field_catalog_rows(
            project_id=project_id,
            entity=entity,
            field_name_pattern=field_name_pattern,
        )
        if not rows:
            return [], [f"No field catalog entries found for project '{project_id}'."]

        suggestions: list[ManifestSuggestion] = []
        seen: set[str] = set()
        for row in rows:
            row_entity = row["entity_name"]
            field_name = row["field_name"]
            if not row_entity or not field_name:
                continue
            citation = self._citation_for_document(project_id, row["document_id"])
            if citation is None:
                continue

            candidates: list[tuple[str, dict[str, Any], str, float]] = []
            if row["nullable"] is not None and not bool(row["nullable"]):
                candidates.append(
                    (
                        "not_null",
                        {"required": True},
                        f"{row_entity}.{field_name} is marked not nullable in {row['document_name']}.",
                        0.92,
                    )
                )
            if row["length"] is not None:
                candidates.append(
                    (
                        "max_length",
                        {"max_length": int(row["length"])},
                        f"{row_entity}.{field_name} has length {row['length']} in {row['document_name']}.",
                        0.88,
                    )
                )
            if row["precision"] is not None and row["scale"] is not None:
                candidates.append(
                    (
                        "precision_scale",
                        {"precision": int(row["precision"]), "scale": int(row["scale"])},
                        (
                            f"{row_entity}.{field_name} has precision {row['precision']} "
                            f"and scale {row['scale']} in {row['document_name']}."
                        ),
                        0.88,
                    )
                )

            for validation_type, constraint, rationale, confidence in candidates:
                suggestion = self._build_manifest_suggestion(
                    project_id=project_id,
                    suggestion_type="validation",
                    key=f"{row_entity}:{field_name}:{validation_type}:{json.dumps(constraint, sort_keys=True)}",
                    entity=row_entity,
                    field_name=field_name,
                    title=f"Validate {row_entity}.{field_name}: {validation_type.replace('_', ' ')}",
                    summary=f"Add a {validation_type.replace('_', ' ')} validation for {row_entity}.{field_name}.",
                    rationale=rationale,
                    target_step="step3",
                    manifest_path=(
                        f"entities.{_manifest_path_token(row_entity)}.fields."
                        f"{_manifest_path_token(field_name)}.validations.{validation_type}"
                    ),
                    payload={
                        "entity": row_entity,
                        "field": field_name,
                        "validation_type": validation_type,
                        **constraint,
                        "source_excerpt": citation.snippet,
                    },
                    citations=[citation],
                    confidence=confidence,
                    confidence_basis="deterministic",
                )
                if suggestion.suggestion_id not in seen:
                    seen.add(suggestion.suggestion_id)
                    self._upsert_manifest_suggestion(suggestion)
                    suggestions.append(suggestion)

        for suggestion in self._pattern_validation_candidates(
            project_id=project_id,
            entity=entity,
            field_name_pattern=field_name_pattern,
        ):
            if suggestion.suggestion_id in seen:
                continue
            seen.add(suggestion.suggestion_id)
            self._upsert_manifest_suggestion(suggestion)
            suggestions.append(suggestion)

        suggestions.sort(key=lambda item: (-item.confidence, item.entity or "", item.field or ""))
        return suggestions[:max_suggestions], []

    def _pattern_validation_candidates(
        self,
        *,
        project_id: str,
        entity: str | None,
        field_name_pattern: str | None,
    ) -> list[ManifestSuggestion]:
        fields = self._field_catalog_rows(
            project_id=project_id,
            entity=entity,
            field_name_pattern=field_name_pattern,
        )
        chunks = self._project_chunk_rows(project_id)
        suggestions: list[ManifestSuggestion] = []
        for field in fields:
            row_entity = field["entity_name"]
            field_name = field["field_name"]
            if not row_entity or not field_name:
                continue
            for chunk in chunks:
                content = chunk["content"]
                if not _contains_token(content, row_entity) or not _contains_token(content, field_name):
                    continue
                pattern = _extract_pattern_hint(content, field_name)
                if pattern is None:
                    continue
                citation = _citation(chunk, _short_excerpt(content))
                suggestions.append(
                    self._build_manifest_suggestion(
                        project_id=project_id,
                        suggestion_type="validation",
                        key=f"{row_entity}:{field_name}:pattern:{pattern}",
                        entity=row_entity,
                        field_name=field_name,
                        title=f"Validate {row_entity}.{field_name}: pattern",
                        summary=f"Add a pattern validation for {row_entity}.{field_name}.",
                        rationale=f"Source text explicitly describes a format for {row_entity}.{field_name}.",
                        target_step="step3",
                        manifest_path=(
                            f"entities.{_manifest_path_token(row_entity)}.fields."
                            f"{_manifest_path_token(field_name)}.validations.pattern"
                        ),
                        payload={
                            "entity": row_entity,
                            "field": field_name,
                            "validation_type": "pattern",
                            "pattern": pattern,
                            "source_excerpt": citation.snippet,
                        },
                        citations=[citation],
                        confidence=0.76,
                        confidence_basis="heuristic",
                    )
                )
                break
        return suggestions

    def _suggest_rule_candidates(
        self,
        *,
        project_id: str,
        entity: str | None,
        field_name_pattern: str | None,
        max_suggestions: int,
    ) -> tuple[list[ManifestSuggestion], list[str]]:
        fields = self._field_catalog_rows(
            project_id=project_id,
            entity=entity,
            field_name_pattern=field_name_pattern,
        )
        if not fields:
            return [], [f"No field catalog entries found for project '{project_id}'."]

        suggestions: list[ManifestSuggestion] = []
        seen: set[str] = set()
        chunks = self._project_chunk_rows(project_id)
        for field in fields:
            row_entity = field["entity_name"]
            field_name = field["field_name"]
            if not row_entity or not field_name:
                continue
            for chunk in chunks:
                content = chunk["content"]
                if not _contains_token(content, row_entity) or not _contains_token(content, field_name):
                    continue
                citation = _citation(chunk, _short_excerpt(content))
                allowed_values = _extract_allowed_values(content, row_entity, field_name)
                if allowed_values:
                    rule_id = f"{_slugify(row_entity)}-{_slugify(field_name)}-allowed-values"
                    suggestion = self._build_rule_suggestion(
                        project_id=project_id,
                        entity=row_entity,
                        field_name=field_name,
                        rule_id=rule_id,
                        rule_type="allowed_values",
                        constraint={"values": allowed_values},
                        source_excerpt=citation.snippet,
                        citation=citation,
                        confidence=0.82,
                    )
                    if suggestion.suggestion_id not in seen:
                        seen.add(suggestion.suggestion_id)
                        self._upsert_manifest_suggestion(suggestion)
                        suggestions.append(suggestion)
                    continue

                range_constraint = _extract_range_constraint(content, row_entity, field_name)
                if range_constraint:
                    rule_id = f"{_slugify(row_entity)}-{_slugify(field_name)}-range"
                    suggestion = self._build_rule_suggestion(
                        project_id=project_id,
                        entity=row_entity,
                        field_name=field_name,
                        rule_id=rule_id,
                        rule_type="range",
                        constraint=range_constraint,
                        source_excerpt=citation.snippet,
                        citation=citation,
                        confidence=0.78,
                    )
                    if suggestion.suggestion_id not in seen:
                        seen.add(suggestion.suggestion_id)
                        self._upsert_manifest_suggestion(suggestion)
                        suggestions.append(suggestion)

        suggestions.sort(key=lambda item: (-item.confidence, item.entity or "", item.field or ""))
        return suggestions[:max_suggestions], []

    def _build_rule_suggestion(
        self,
        *,
        project_id: str,
        entity: str,
        field_name: str,
        rule_id: str,
        rule_type: str,
        constraint: dict[str, Any],
        source_excerpt: str,
        citation: Citation,
        confidence: float,
    ) -> ManifestSuggestion:
        return self._build_manifest_suggestion(
            project_id=project_id,
            suggestion_type="rule",
            key=f"{entity}:{field_name}:{rule_type}:{json.dumps(constraint, sort_keys=True)}",
            entity=entity,
            field_name=field_name,
            title=f"Suggested rule: {entity}.{field_name} {rule_type.replace('_', ' ')}",
            summary=f"Add a {rule_type.replace('_', ' ')} rule for {entity}.{field_name}.",
            rationale=f"Source text explicitly states a field-level business rule for {entity}.{field_name}.",
            target_step="step6",
            manifest_path=f"rules.{_manifest_path_token(entity)}.{rule_id}",
            payload={
                "entity": entity,
                "rule_id": rule_id,
                "rule_type": rule_type,
                "field": field_name,
                "constraint": constraint,
                "source_excerpt": source_excerpt,
            },
            citations=[citation],
            confidence=confidence,
            confidence_basis="heuristic",
        )

    def _suggest_cross_entity_rule_candidates(
        self,
        *,
        project_id: str,
        entity: str | None,
        field_name_pattern: str | None,
        max_suggestions: int,
    ) -> tuple[list[ManifestSuggestion], list[str]]:
        known_entities = self._known_entities(project_id)
        if not known_entities:
            return [], [f"No entity catalog entries found for project '{project_id}'."]

        suggestions: list[ManifestSuggestion] = []
        warnings: list[str] = []
        seen: set[str] = set()
        catalog_fields = self._catalog_field_index(project_id)
        for chunk in self._project_chunk_rows(project_id):
            content = chunk["content"]
            for relation in _extract_relationships(content):
                source_entity = relation["source_entity"]
                source_field = relation["source_field"]
                target_entity = relation["target_entity"]
                target_id_field = relation["target_field"]
                if entity and source_entity.lower() != entity.lower():
                    continue
                if field_name_pattern and field_name_pattern.lower() not in source_field.lower():
                    continue
                if target_entity.lower() not in known_entities:
                    continue
                if not _catalog_has_field(catalog_fields, source_entity, source_field):
                    warnings.append(
                        "Skipped cross-entity suggestion because source field "
                        f"{source_entity}.{source_field} is not present in field_catalog."
                    )
                    continue
                if not _catalog_has_field(catalog_fields, target_entity, target_id_field):
                    warnings.append(
                        "Skipped cross-entity suggestion because referenced id field "
                        f"{target_entity}.{target_id_field} is not present in field_catalog."
                    )
                    continue
                citation = _citation(chunk, _short_excerpt(content))
                for condition in _extract_cross_entity_conditions(
                    content=content,
                    source_entity=source_entity,
                    target_entity=target_entity,
                ):
                    rule_type = condition["rule_type"]
                    target_field = condition["target_field"]
                    if not _catalog_has_field(catalog_fields, target_entity, target_field):
                        warnings.append(
                            "Skipped cross-entity suggestion because target state field "
                            f"{target_entity}.{target_field} is not present in field_catalog."
                        )
                        continue
                    compare_source_field = condition.get("compare_source_field")
                    if compare_source_field and not _catalog_has_field(
                        catalog_fields, source_entity, str(compare_source_field)
                    ):
                        warnings.append(
                            "Skipped cross-entity suggestion because compare source field "
                            f"{source_entity}.{compare_source_field} is not present "
                            "in field_catalog."
                        )
                        continue
                    rule_id = (
                        f"{_slugify(source_entity)}-{_slugify(source_field)}-"
                        f"{_slugify(target_entity)}-{_slugify(target_field)}"
                    )
                    payload = {
                        "rule_id": rule_id,
                        "rule_type": rule_type,
                        "source_entity": source_entity,
                        "source_field": source_field,
                        "field": source_field,
                        "target_entity": target_entity,
                        "target_field": target_field,
                        "target_id_field": target_id_field,
                        "operator": condition["operator"],
                        "description": condition["description"],
                        "source_excerpt": citation.snippet,
                        "requires_prerequisite": "cross-entity-exists",
                    }
                    if "expected_value" in condition:
                        payload["expected_value"] = condition["expected_value"]
                    if "allowed_values" in condition:
                        payload["allowed_values"] = condition["allowed_values"]
                    if compare_source_field:
                        payload["compare_source_field"] = compare_source_field
                    suggestion = self._build_manifest_suggestion(
                        project_id=project_id,
                        suggestion_type="cross_entity_rule",
                        key=f"{source_entity}:{source_field}:{target_entity}:{target_field}:{json.dumps(condition, sort_keys=True)}",
                        entity=source_entity,
                        field_name=source_field,
                        title=(
                            f"Suggested cross-entity rule: "
                            f"{source_entity}.{source_field} checks {target_entity}.{target_field}"
                        ),
                        summary=condition["description"],
                        rationale=(
                            "Source text explicitly describes both the entity reference and "
                            "the referenced entity state constraint. Studio must still ensure "
                            "the cross-entity-exists prerequisite is present before applying it."
                        ),
                        target_step="step6",
                        manifest_path=(
                            f"rules.{_manifest_path_token(source_entity)}."
                            f"{_manifest_path_token(source_field)}.cross-entity"
                        ),
                        payload=payload,
                        citations=[citation],
                        confidence=0.76,
                        confidence_basis="heuristic",
                        warnings=[
                            (
                                "Requires Studio-side cross-entity-exists prerequisite "
                                f"for {source_entity}.{source_field} -> {target_entity}.{target_id_field}."
                            )
                        ],
                    )
                    if suggestion.suggestion_id in seen:
                        continue
                    seen.add(suggestion.suggestion_id)
                    self._upsert_manifest_suggestion(suggestion)
                    suggestions.append(suggestion)

        suggestions.sort(key=lambda item: (-item.confidence, item.entity or "", item.field or ""))
        return suggestions[:max_suggestions], list(dict.fromkeys(warnings))

    def _suggest_mapping_candidates(
        self,
        *,
        project_id: str,
        route_name: str | None,
        source_entity: str | None,
        target_entity: str | None,
        direction: str | None,
        field_name_pattern: str | None,
        max_suggestions: int,
    ) -> tuple[list[ManifestSuggestion], list[str]]:
        if not source_entity or not target_entity:
            return [], [
                (
                    "Mapping suggestions require source_entity and target_entity; "
                    "no suggestions were persisted."
                )
            ]
        route_token = route_name.strip() if route_name and route_name.strip() else None
        normalized_direction = direction.strip().lower() if direction else None
        if not route_token or not normalized_direction:
            return [], [
                (
                    "Mapping suggestions require route_name and direction to build a "
                    "route-backed manifest path; no suggestions were persisted."
                )
            ]
        if normalized_direction not in {"request", "response"}:
            return [], [
                (
                    "Mapping suggestions require direction to be 'request' or 'response' "
                    "when provided; no suggestions were persisted."
                )
            ]

        source_rows = _dedupe_mapping_rows(
            self._field_catalog_rows(project_id=project_id, entity=source_entity)
        )
        target_rows = _dedupe_mapping_rows(
            self._field_catalog_rows(project_id=project_id, entity=target_entity)
        )
        if not source_rows or not target_rows:
            return [], [
                (
                    f"No field catalog entries found for mapping source '{source_entity}' "
                    f"and target '{target_entity}'."
                )
            ]

        suggestions: list[ManifestSuggestion] = []
        warnings: list[str] = []
        for source_row in source_rows:
            source_field = source_row["field_name"]
            if field_name_pattern and not (
                field_name_pattern.lower() in source_field.lower()
                or any(
                    field_name_pattern.lower() in target_row["field_name"].lower()
                    for target_row in target_rows
                )
            ):
                continue
            match = _select_mapping_match(source_row, target_rows, field_name_pattern)
            if match.warning:
                warnings.append(match.warning)
            if match.target_row is None:
                continue

            target_row = match.target_row
            target_field = target_row["field_name"]
            source_citation = self._citation_for_document(project_id, source_row["document_id"])
            target_citation = self._citation_for_document(project_id, target_row["document_id"])
            citations = [
                citation
                for citation in [source_citation, target_citation]
                if citation is not None
            ]
            if not citations:
                warnings.append(
                    f"Skipped mapping suggestion for {source_entity}.{source_field} "
                    f"because no source catalog citation was available."
                )
                continue

            payload = {
                "route_name": route_token,
                "direction": normalized_direction,
                "source_entity": source_entity,
                "target_entity": target_entity,
                "source_field": source_field,
                "target_field": target_field,
                "mapping_type": "copy",
                "confidence_basis": match.confidence_basis,
                "value_map": None,
            }
            suggestion = self._build_manifest_suggestion(
                project_id=project_id,
                suggestion_type="mapping",
                key=(
                    f"{route_token}:{normalized_direction}:{source_entity}:{target_entity}:"
                    f"{source_field}:{target_field}"
                ),
                entity=target_entity,
                field_name=target_field,
                title=f"Map {source_entity}.{source_field} to {target_entity}.{target_field}",
                summary=(
                    f"Copy {source_entity}.{source_field} into "
                    f"{target_entity}.{target_field}."
                ),
                rationale=match.rationale,
                target_step="step4",
                manifest_path=(
                    f"async_routes.{_manifest_path_token(route_token)}."
                    f"transform_mapping.{_manifest_path_token(normalized_direction)}."
                    f"{_manifest_path_token(source_field)}."
                    f"{_manifest_path_token(target_field)}"
                ),
                payload=payload,
                citations=citations,
                confidence=match.confidence,
                confidence_basis=match.confidence_basis,
            )
            self._upsert_manifest_suggestion(suggestion)
            suggestions.append(suggestion)

        suggestions.sort(
            key=lambda item: (
                -item.confidence,
                item.payload["source_field"],
                item.payload["target_field"],
            )
        )
        return suggestions[:max_suggestions], list(dict.fromkeys(warnings))

    def _suggest_transform_candidates(
        self,
        *,
        project_id: str,
        route_name: str | None,
        source_entity: str | None,
        target_entity: str | None,
        target_id: str | None,
        direction: str | None,
        field_name_pattern: str | None,
        max_suggestions: int,
    ) -> tuple[list[ManifestSuggestion], list[str]]:
        if not source_entity or not target_entity:
            return [], [
                (
                    "Transform suggestions require source_entity and target_entity; "
                    "no suggestions were persisted."
                )
            ]
        route_token = route_name.strip() if route_name and route_name.strip() else None
        normalized_direction = direction.strip().lower() if direction else None
        if not route_token or not normalized_direction:
            return [], [
                (
                    "Transform suggestions require route_name and direction; "
                    "no suggestions were persisted."
                )
            ]
        target_id_token = target_id.strip() if target_id and target_id.strip() else None
        if not target_id_token:
            return [], [
                (
                    "Transform suggestions require target_id from router_config.targets; "
                    "no suggestions were persisted."
                )
            ]
        if normalized_direction not in {"request", "response"}:
            return [], [
                (
                    "Transform suggestions require direction to be 'request' or "
                    "'response'; no suggestions were persisted."
                )
            ]

        source_rows = _dedupe_mapping_rows(
            self._field_catalog_rows(project_id=project_id, entity=source_entity)
        )
        target_rows = _dedupe_mapping_rows(
            self._field_catalog_rows(project_id=project_id, entity=target_entity)
        )
        if not source_rows or not target_rows:
            return [], [
                (
                    f"No field catalog entries found for transform source '{source_entity}' "
                    f"and target '{target_entity}'."
                )
            ]

        transform_ref = "request_transform" if normalized_direction == "request" else "response_transform"
        transform_file_suggestion = (
            f"transforms/{_slugify(route_token)}-{_slugify(target_id_token)}-{normalized_direction}.yaml"
        )
        warnings: list[str] = []
        suggestions: list[ManifestSuggestion] = []
        for source_row in source_rows:
            source_field = source_row["field_name"]
            if field_name_pattern and not (
                field_name_pattern.lower() in source_field.lower()
                or any(
                    field_name_pattern.lower() in target_row["field_name"].lower()
                    for target_row in target_rows
                )
            ):
                continue
            match = _select_transform_match(source_row, target_rows, field_name_pattern)
            if match.warning:
                warnings.append(match.warning)
            if match.target_row is None:
                continue

            target_row = match.target_row
            target_field = target_row["field_name"]
            source_citation = self._citation_for_document(project_id, source_row["document_id"])
            target_citation = self._citation_for_document(project_id, target_row["document_id"])
            citations = [
                citation
                for citation in [source_citation, target_citation]
                if citation is not None
            ]
            if not citations:
                warnings.append(
                    f"Skipped transform suggestion for {source_entity}.{source_field} "
                    f"because no source catalog citation was available."
                )
                continue

            source_path = f"$.{source_field}"
            target_path = f"$.{target_field}"
            manifest_path = (
                f"async_routes.{_manifest_path_token(route_token)}.router_config."
                f"targets.{_router_path_token(target_id_token)}.{transform_ref}"
            )
            payload = {
                "source": source_path,
                "target": target_path,
                "default_value": None,
                "constant": None,
                "value_map": None,
                "type_coercion": None,
                "route_name": route_token,
                "direction": normalized_direction,
                "target_id": target_id_token,
                "source_entity": source_entity,
                "target_entity": target_entity,
                "source_field": source_field,
                "target_field": target_field,
                "transform_file_suggestion": transform_file_suggestion,
                "manifest_path": manifest_path,
                "scope": "transforms",
                "suggestion_type": "transform",
                "confidence_basis": match.confidence_basis,
            }
            suggestion = self._build_manifest_suggestion(
                project_id=project_id,
                suggestion_type="transform",
                key=(
                    f"{route_token}:{target_id_token}:{normalized_direction}:"
                    f"{source_path}:{target_path}"
                ),
                entity=target_entity,
                field_name=target_field,
                title=f"Transform {source_entity}.{source_field} to {target_entity}.{target_field}",
                summary=(
                    f"Add a Kafka router {normalized_direction} transform row copying "
                    f"{source_path} to {target_path}."
                ),
                rationale=match.rationale,
                target_step="kafka_step3",
                manifest_path=manifest_path,
                payload=payload,
                citations=citations,
                confidence=match.confidence,
                confidence_basis=match.confidence_basis,
            )
            self._upsert_manifest_suggestion(suggestion)
            suggestions.append(suggestion)

        suggestions.sort(
            key=lambda item: (
                -item.confidence,
                item.payload["source"],
                item.payload["target"],
            )
        )
        return suggestions[:max_suggestions], list(dict.fromkeys(warnings))

    def _suggest_conflict_resolution_candidates(
        self,
        *,
        project_id: str,
        query: str | None,
        entity: str | None,
        route_name: str | None,
        direction: str | None,
        max_suggestions: int,
    ) -> tuple[list[ManifestSuggestion], list[str]]:
        normalized_query = query.strip() if query else ""
        if not normalized_query:
            return [], [
                (
                    "Conflict-resolution suggestions require field_name_pattern as "
                    "the conflict query; no suggestions were persisted."
                )
            ]

        field_delta_suggestions, field_delta_warnings = self._suggest_field_delta_conflicts(
            project_id=project_id,
            query=normalized_query,
            entity=entity,
            route_name=route_name,
            direction=direction,
            max_suggestions=max_suggestions,
        )
        if field_delta_suggestions:
            return field_delta_suggestions, field_delta_warnings

        conflict_result = self.find_conflicts(
            project_id=project_id,
            query=normalized_query,
            max_chunks_to_search=max(10, min(max_suggestions * 4, 100)),
        )
        warnings = list(field_delta_warnings)
        if conflict_result.conflict_pairs:
            warnings.append(
                "Broad source overlap was found, but no actionable field-level "
                "delta was detected; no conflict_resolution suggestion was persisted."
            )
        else:
            warnings.extend(conflict_result.warnings)
        return [], list(dict.fromkeys(warnings))

    def _suggest_field_delta_conflicts(
        self,
        *,
        project_id: str,
        query: str,
        entity: str | None,
        route_name: str | None,
        direction: str | None,
        max_suggestions: int,
    ) -> tuple[list[ManifestSuggestion], list[str]]:
        all_rows = self._field_catalog_rows(project_id=project_id, entity=entity)
        matching_rows = [
            row for row in all_rows if _field_row_matches_conflict_query(row, query, entity)
        ]
        if not matching_rows:
            return [], []

        query_context = _compact_key(
            ":".join(
                value
                for value in [entity or "", route_name or "", direction or "", query]
                if value
            )
        )
        matching_entities = {
            _normalize_optional_entity(row["entity_name"])
            for row in matching_rows
            if _normalize_optional_entity(row["entity_name"]) is not None
        }
        suggestions: list[ManifestSuggestion] = []
        warnings: list[str] = []
        seen_keys: set[str] = set()
        for entity_key in sorted(matching_entities):
            assert entity_key is not None
            entity_rows = [
                row
                for row in all_rows
                if _normalize_optional_entity(row["entity_name"]) == entity_key
            ]
            entity_doc_names = {
                row["document_id"]: row["document_name"]
                for row in entity_rows
            }
            rows_by_field: dict[tuple[str, ...], list[sqlite3.Row]] = {}
            for row in entity_rows:
                rows_by_field.setdefault(_mapping_token_key(row["field_name"]), []).append(row)

            for field_key, field_rows in rows_by_field.items():
                if not field_key:
                    continue
                if not any(
                    _field_row_matches_conflict_query(row, query, entity)
                    for row in field_rows
                ):
                    continue
                first_by_document = _first_field_rows_by_document(field_rows)
                present_document_ids = set(first_by_document)
                all_document_ids = set(entity_doc_names)

                for row_a, row_b in itertools.combinations(first_by_document.values(), 2):
                    category = _field_delta_category(row_a, row_b)
                    if category == "source overlap/no actionable conflict":
                        continue
                    suggestion = self._build_field_delta_conflict_suggestion(
                        project_id=project_id,
                        query=query,
                        query_context=query_context,
                        row_a=row_a,
                        row_b=row_b,
                        difference_category=category,
                    )
                    if suggestion.suggestion_id in seen_keys:
                        continue
                    seen_keys.add(suggestion.suggestion_id)
                    self._upsert_manifest_suggestion(suggestion)
                    suggestions.append(suggestion)
                    if len(suggestions) >= max_suggestions:
                        return suggestions, warnings

                missing_document_ids = sorted(all_document_ids - present_document_ids)
                for missing_document_id in missing_document_ids:
                    present_row = next(iter(first_by_document.values()))
                    suggestion = self._build_field_delta_conflict_suggestion(
                        project_id=project_id,
                        query=query,
                        query_context=query_context,
                        row_a=present_row,
                        row_b=None,
                        missing_document_id=missing_document_id,
                        missing_document_name=entity_doc_names[missing_document_id],
                        difference_category="missing field in one source",
                    )
                    if suggestion.suggestion_id in seen_keys:
                        continue
                    seen_keys.add(suggestion.suggestion_id)
                    self._upsert_manifest_suggestion(suggestion)
                    suggestions.append(suggestion)
                    if len(suggestions) >= max_suggestions:
                        return suggestions, warnings

        return suggestions, warnings

    def _build_field_delta_conflict_suggestion(
        self,
        *,
        project_id: str,
        query: str,
        query_context: str,
        row_a: sqlite3.Row,
        row_b: sqlite3.Row | None,
        difference_category: str,
        missing_document_id: str | None = None,
        missing_document_name: str | None = None,
    ) -> ManifestSuggestion:
        document_a_id = row_a["document_id"]
        document_a_name = row_a["document_name"]
        document_b_id = row_b["document_id"] if row_b is not None else missing_document_id
        document_b_name = row_b["document_name"] if row_b is not None else missing_document_name
        if document_b_id is None or document_b_name is None:
            raise ValueError("field delta conflict requires a second source document")

        citation_a = self._citation_for_document(project_id, document_a_id)
        citation_b = self._citation_for_document(project_id, document_b_id)
        citations = [
            citation
            for citation in [citation_a, citation_b]
            if citation is not None
        ]
        chunk_a_id = citation_a.chunk_id if citation_a is not None else None
        chunk_b_id = citation_b.chunk_id if citation_b is not None else None
        source_a_field = row_a["field_name"]
        source_b_field = row_b["field_name"] if row_b is not None else None
        entity_name = row_a["entity_name"]
        field_name = _friendly_delta_field(source_a_field, source_b_field)
        delta_summary = _field_delta_summary(
            difference_category=difference_category,
            source_a_document_name=document_a_name,
            source_a_field=source_a_field,
            source_a_type=row_a["field_type"],
            source_b_document_name=document_b_name,
            source_b_field=source_b_field,
            source_b_type=row_b["field_type"] if row_b is not None else None,
        )
        interpretation, suggested_action, confidence = _field_delta_guidance(difference_category)
        payload = {
            "conflict_signal": delta_summary,
            "document_a_id": document_a_id,
            "document_a_name": document_a_name,
            "document_b_id": document_b_id,
            "document_b_name": document_b_name,
            "chunk_a_id": chunk_a_id,
            "chunk_b_id": chunk_b_id,
            "citation_a": citation_a.model_dump() if citation_a is not None else None,
            "citation_b": citation_b.model_dump() if citation_b is not None else None,
            "query": query,
            "scope": "conflict_resolution",
            "suggestion_type": "conflict_resolution",
            "delta_summary": delta_summary,
            "difference_category": difference_category,
            "entity": entity_name,
            "field": field_name,
            "source_a_document_id": document_a_id,
            "source_a_document_name": document_a_name,
            "source_a_field": source_a_field,
            "source_a_type": row_a["field_type"],
            "source_a_length": row_a["length"],
            "source_a_precision": row_a["precision"],
            "source_a_scale": row_a["scale"],
            "source_b_document_id": document_b_id,
            "source_b_document_name": document_b_name,
            "source_b_field": source_b_field,
            "source_b_type": row_b["field_type"] if row_b is not None else None,
            "source_b_length": row_b["length"] if row_b is not None else None,
            "source_b_precision": row_b["precision"] if row_b is not None else None,
            "source_b_scale": row_b["scale"] if row_b is not None else None,
            "normalized_field_mapping": (
                {
                    "source_a": source_a_field,
                    "source_b": source_b_field,
                    "normalized_key": "_".join(_mapping_token_key(source_a_field)),
                }
                if source_b_field is not None
                else None
            ),
            "interpretation": interpretation,
            "suggested_action": suggested_action,
        }
        document_key = ":".join(sorted([document_a_id, document_b_id]))
        key = (
            f"{document_key}:{query_context}:{_normalize_optional_entity(entity_name)}:"
            f"{_mapping_exact_key(field_name)}:{difference_category}"
        )
        return self._build_manifest_suggestion(
            project_id=project_id,
            suggestion_type="conflict_resolution",
            key=key,
            entity=entity_name,
            field_name=field_name,
            title=f"Review {difference_category} for {entity_name}.{field_name}",
            summary=delta_summary,
            rationale=interpretation,
            target_step="step7",
            manifest_path="",
            payload=payload,
            citations=citations,
            confidence=confidence,
            confidence_basis="field_catalog_delta",
        )

    def _suggest_portfolio_reuse_candidates(
        self,
        *,
        project_id: str,
        query: str | None,
        max_suggestions: int,
    ) -> tuple[list[ManifestSuggestion], list[str]]:
        normalized_query = query.strip() if query else ""
        if not _normalize_fts_query(normalized_query):
            return [], [
                (
                    "Portfolio-reuse suggestions require field_name_pattern as "
                    "a searchable query; no suggestions were persisted."
                )
            ]

        other_project_ids = self._active_project_ids(exclude_project_id=project_id)
        if not other_project_ids:
            return [], [
                (
                    "No other projects are available for portfolio reuse; "
                    "no suggestions were persisted."
                )
            ]

        search_result = self.search_across_projects(
            query=normalized_query,
            project_ids=other_project_ids,
            max_results_per_project=max(1, min(max_suggestions, 20)),
        )
        flattened_results: list[tuple[str, SearchResult]] = [
            (project_result.project_id, result)
            for project_result in search_result.by_project
            for result in project_result.results
        ]
        if not flattened_results:
            return [], [
                (
                    "No portfolio reuse candidates were found outside the current "
                    f"project for query '{normalized_query}'."
                )
            ]

        suggestions: list[ManifestSuggestion] = []
        for matched_project_id, result in flattened_results[:max_suggestions]:
            document_row = self._find_document(matched_project_id, result.document_id)
            doc_type = document_row["doc_type"] if document_row is not None else None
            manifest_path = (
                f"portfolio_reuse.{_manifest_path_token(matched_project_id)}."
                f"{_manifest_path_token(result.document_id)}."
                f"{_manifest_path_token(result.chunk_id)}"
            )
            payload = {
                "query": normalized_query,
                "matched_project_id": matched_project_id,
                "matched_document_id": result.document_id,
                "matched_document_name": result.document_name,
                "matched_chunk_id": result.chunk_id,
                "doc_type": doc_type,
                "snippet": result.snippet,
                "citation_summary": result.citation.snippet,
                "reuse_kind": "portfolio-pattern",
                "target_step": "review",
                "target_manifest_path": None,
                "source_score": result.score,
                "search_score": result.score,
                "scope": "portfolio_reuse",
                "suggestion_type": "portfolio_reuse",
            }
            suggestion = self._build_manifest_suggestion(
                project_id=project_id,
                suggestion_type="portfolio_reuse",
                key=f"{matched_project_id}:{manifest_path}",
                entity=None,
                field_name=_compact_key(normalized_query) or manifest_path,
                title=f"Review portfolio reuse candidate from {matched_project_id}",
                summary=(
                    f"Review similar evidence in {result.document_name} from "
                    f"project {matched_project_id}."
                ),
                rationale=(
                    "Cross-project search found a deterministic text match. KS has "
                    "not inferred semantic fit or applied any reuse automatically."
                ),
                target_step="review",
                manifest_path=manifest_path,
                payload=payload,
                citations=[result.citation],
                confidence=0.62,
                confidence_basis="search_across_projects",
            )
            self._upsert_manifest_suggestion(suggestion)
            suggestions.append(suggestion)

        return suggestions, search_result.warnings

    def _suggest_identity_role_candidates(
        self,
        *,
        project_id: str,
        entity: str | None,
        field_name_pattern: str | None,
        max_suggestions: int,
    ) -> tuple[list[ManifestSuggestion], list[str]]:
        rows = self._identity_field_rows(
            project_id=project_id,
            entity=entity,
            field_name_pattern=field_name_pattern,
        )
        if not rows:
            scope = f" for entity '{entity}'" if entity else ""
            return [], [
                (
                    f"No field catalog entries found{scope} in project '{project_id}'; "
                    "no identity_role suggestions were persisted."
                )
            ]

        known_entity_keys = {
            _identity_entity_key(row["entity_name"])
            for row in self._field_catalog_rows(project_id=project_id)
            if row["entity_name"]
        }
        chunks = self._project_chunk_rows(project_id)
        groups: dict[tuple[tuple[str, ...], tuple[str, ...]], list[sqlite3.Row]] = {}
        for row in rows:
            if not row["entity_name"] or not row["field_name"]:
                continue
            groups.setdefault(
                (_identity_entity_key(row["entity_name"]), _mapping_token_key(row["field_name"])),
                [],
            ).append(row)

        suggestions: list[ManifestSuggestion] = []
        warnings: list[str] = []
        seen: set[str] = set()
        for (_, field_key), field_rows in sorted(
            groups.items(),
            key=lambda item: (_preferred_identity_entity_name(item[1]), _preferred_identity_field_name(item[1])),
        ):
            if not field_key:
                continue
            row_entity = _preferred_identity_entity_name(field_rows, requested_entity=entity)
            field_name = _preferred_identity_field_name(field_rows)
            candidates: list[dict[str, Any]] = []
            source_citations: list[Citation] = []
            for row in field_rows:
                citation = self._citation_for_document(project_id, row["document_id"])
                if citation is not None:
                    source_citations.append(citation)
                candidates.extend(
                    _identity_candidates_from_field_row(
                        row=row,
                        entity=row_entity,
                        field_name=field_name,
                        known_entity_keys=known_entity_keys,
                    )
                )

            for chunk in chunks:
                if chunk["doc_type"] in {"sql", "csv", "excel"}:
                    continue
                content = chunk["content"]
                if not _identity_chunk_mentions_field(content, row_entity, field_name):
                    continue
                citation = _citation(chunk, _short_excerpt(content))
                chunk_candidates = _identity_candidates_from_text(
                    content=content,
                    entity=row_entity,
                    field_name=field_name,
                    citation=citation,
                )
                if chunk_candidates:
                    source_citations.append(citation)
                    candidates.extend(chunk_candidates)

            selected = _select_identity_candidate(candidates)
            if selected is None:
                continue

            citations = _dedupe_citations(
                [
                    *source_citations,
                    *[
                        citation
                        for candidate in candidates
                        for citation in candidate.get("citations", [])
                        if isinstance(citation, Citation)
                    ],
                ]
            )
            if not citations:
                warnings.append(
                    f"Skipped identity_role suggestion for {row_entity}.{field_name} "
                    "because no supporting citation was available."
                )
                continue

            suggested_role = selected["role"]
            signals = _identity_signals_for_role(candidates, suggested_role)
            if selected.get("signal") not in signals:
                signals.insert(0, selected["signal"])
            conflicting_roles = sorted(
                {
                    candidate["role"]
                    for candidate in candidates
                    if candidate.get("role") != suggested_role
                    and float(candidate.get("confidence", 0.0)) >= 0.8
                }
            )
            confidence = float(selected["confidence"])
            review_needed = bool(conflicting_roles) or confidence < 0.7
            source_document_names = sorted({citation.document_name for citation in citations})
            source_document_ids = sorted({citation.document_id for citation in citations})
            rationale = str(selected["rationale"])
            summary = f"Suggest {suggested_role} for {row_entity}.{field_name}."
            payload = {
                "scope": "identity_role",
                "suggestion_type": "identity_role",
                "entity": row_entity,
                "field": field_name,
                "suggested_role": suggested_role,
                "confidence": confidence,
                "confidence_basis": selected["confidence_basis"],
                "rationale": rationale,
                "summary": summary,
                "signals": signals,
                "source_document_ids": source_document_ids,
                "source_document_names": source_document_names,
                "review_needed": review_needed,
            }
            if conflicting_roles:
                payload["conflicting_roles"] = conflicting_roles
            key = (
                f"{_identity_entity_key(row_entity)}:{_mapping_token_key(field_name)}:"
                f"{suggested_role}"
            )
            suggestion = self._build_manifest_suggestion(
                project_id=project_id,
                suggestion_type="identity_role",
                key=key,
                entity=row_entity,
                field_name=field_name,
                title=f"Review identity role for {row_entity}.{field_name}",
                summary=summary,
                rationale=rationale,
                target_step="step3",
                manifest_path=(
                    f"entities.{_manifest_path_token(row_entity)}.fields."
                    f"{_manifest_path_token(field_name)}.identity_role"
                ),
                payload=payload,
                citations=citations,
                confidence=confidence,
                confidence_basis=str(selected["confidence_basis"]),
                warnings=(
                    [f"Conflicting identity-role evidence also suggested: {', '.join(conflicting_roles)}."]
                    if conflicting_roles
                    else []
                ),
            )
            if suggestion.suggestion_id in seen:
                continue
            seen.add(suggestion.suggestion_id)
            self._upsert_manifest_suggestion(suggestion)
            suggestions.append(suggestion)
            if len(suggestions) >= max_suggestions:
                break

        if not suggestions:
            warnings.append(
                "No evidence-backed identity_role suggestions were found; "
                "no suggestions were persisted."
            )
        suggestions.sort(key=lambda item: (-item.confidence, item.entity or "", item.field or ""))
        return suggestions[:max_suggestions], list(dict.fromkeys(warnings))

    def submit_suggestion_decisions(
        self,
        project_id: str,
        decisions: list[SuggestionDecision],
    ) -> SubmitSuggestionDecisionsResult:
        outcomes: list[SuggestionDecisionOutcome] = []
        for decision in decisions:
            row = self.conn.execute(
                """
                SELECT suggestion_type, suggestion_payload
                FROM manifest_suggestions
                WHERE suggestion_id = ? AND project_id = ?
                """,
                (decision.suggestion_id, project_id),
            ).fetchone()
            if row is None:
                outcomes.append(
                    SuggestionDecisionOutcome(
                        suggestion_id=decision.suggestion_id,
                        status=decision.status,
                        success=False,
                        error=(
                            f"Suggestion not found for project '{project_id}': "
                            f"{decision.suggestion_id}"
                        ),
                    )
                )
                continue

            payload = json.loads(row["suggestion_payload"])
            validation_error, validation_warnings = _validate_edited_payload(
                row["suggestion_type"],
                decision.edited_payload,
                decision.status,
                payload,
            )
            if validation_error:
                outcomes.append(
                    SuggestionDecisionOutcome(
                        suggestion_id=decision.suggestion_id,
                        status=decision.status,
                        success=False,
                        warnings=validation_warnings,
                        error=validation_error,
                    )
                )
                continue

            payload["status"] = decision.status
            if decision.edited_payload is not None:
                payload["edited_payload"] = decision.edited_payload
            now = datetime.now(timezone.utc).isoformat()
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE manifest_suggestions
                    SET status = ?,
                        edited_payload = ?,
                        suggestion_payload = ?,
                        updated_at = ?,
                        reviewed_at = ?
                    WHERE suggestion_id = ? AND project_id = ?
                    """,
                    (
                        decision.status,
                        json.dumps(decision.edited_payload)
                        if decision.edited_payload is not None
                        else None,
                        json.dumps(payload),
                        now,
                        now,
                        decision.suggestion_id,
                        project_id,
                    ),
                )
                if row["suggestion_type"] == "identity_role":
                    self._upsert_identity_role_review_state(
                        project_id=project_id,
                        suggestion_id=decision.suggestion_id,
                        status=decision.status,
                        edited_payload=(
                            json.dumps(decision.edited_payload)
                            if decision.edited_payload is not None
                            else None
                        ),
                        reviewed_at=now,
                        source_document_ids=sorted(_document_ids_from_suggestion_payload(payload)),
                    )
            outcomes.append(
                SuggestionDecisionOutcome(
                    suggestion_id=decision.suggestion_id,
                    status=decision.status,
                    success=True,
                    warnings=validation_warnings,
                )
            )

        return SubmitSuggestionDecisionsResult(
            success=all(outcome.success for outcome in outcomes),
            project_id=project_id,
            outcomes=outcomes,
            outcome_count=len(outcomes),
        )

    def compare_field_definitions(
        self,
        project_id: str,
        field_name: str,
        entity: str | None = None,
    ) -> FieldComparisonResult:
        clauses = ["f.project_id = ?", "LOWER(f.field_name) = LOWER(?)", "d.deleted_at IS NULL"]
        params: list[Any] = [project_id, field_name]
        if entity:
            clauses.append("LOWER(f.entity_name) = LOWER(?)")
            params.append(entity)
        rows = self.conn.execute(
            f"""
            SELECT f.*, d.name AS document_name, d.doc_type, d.ingested_at
            FROM field_catalog f
            JOIN documents d ON d.id = f.document_id
            WHERE {' AND '.join(clauses)}
            ORDER BY d.ingested_at ASC
            """,
            params,
        ).fetchall()
        if not rows:
            return FieldComparisonResult(
                project_id=project_id,
                field_name=field_name,
                definitions=[],
                definition_count=0,
                warnings=[f"No definitions found for field '{field_name}' in project '{project_id}'."],
            )

        definitions = [
            FieldDefinitionRow(
                document_id=row["document_id"],
                document_name=row["document_name"],
                doc_type=row["doc_type"],
                entity_name=row["entity_name"],
                field_type=row["field_type"],
                nullable=None if row["nullable"] is None else bool(row["nullable"]),
                description=row["description"],
                length=row["length"],
                precision=row["precision"],
                scale=row["scale"],
                source_location=row["source_location"],
                ingested_at=row["ingested_at"],
            )
            for row in rows
        ]
        type_conflict = _value_conflict_summary(
            "Type conflict",
            [definition.field_type for definition in definitions],
            [definition.document_name for definition in definitions],
        )
        nullable_conflict = _value_conflict_summary(
            "Nullable conflict",
            [definition.nullable for definition in definitions],
            [definition.document_name for definition in definitions],
        )
        conflict_parts = [part for part in [type_conflict, nullable_conflict] if part]
        return FieldComparisonResult(
            project_id=project_id,
            field_name=field_name,
            definitions=definitions,
            definition_count=len(definitions),
            has_conflicts=bool(conflict_parts),
            conflict_summary="; ".join(conflict_parts) or None,
        )

    def get_field_evidence_chain(
        self,
        project_id: str,
        field_name: str,
        entity: str | None = None,
        max_chunks: int = 10,
    ) -> FieldEvidenceChain:
        max_chunks = max(1, min(max_chunks, 50))
        suggestion_result = self.suggest_fields(
            project_id=project_id,
            entity=entity,
            field_name_pattern=field_name,
            min_source_count=1,
            max_suggestions=1,
        )
        suggestion = suggestion_result.suggestions[0] if suggestion_result.suggestions else None
        comparison_result = self.compare_field_definitions(
            project_id=project_id,
            field_name=field_name,
            entity=entity,
        )
        scoped_document_ids = {definition.document_id for definition in comparison_result.definitions}
        if entity and not scoped_document_ids:
            evidence_result = EvidenceResult(
                project_id=project_id,
                query=field_name,
                chunks=[],
                chunk_count=0,
            )
            filtered_chunks = []
        else:
            evidence_query = f"{entity} {field_name}" if entity else field_name
            evidence_result = self.get_evidence(
                project_id=project_id,
                query=evidence_query,
                max_chunks=max_chunks,
            )
            if entity:
                filtered_chunks = [
                    chunk
                    for chunk in evidence_result.chunks
                    if chunk.document_id in scoped_document_ids
                ]
            else:
                filtered_chunks = evidence_result.chunks
        filtered_chunks = _dedupe_evidence_chunks(filtered_chunks)

        source_document_ids = {definition.document_id for definition in comparison_result.definitions}
        source_document_ids.update(chunk.document_id for chunk in filtered_chunks)
        if suggestion:
            source_document_ids.update(item.document_id for item in suggestion.evidence)
        warnings = list(
            dict.fromkeys(
                suggestion_result.warnings + comparison_result.warnings + evidence_result.warnings
            )
        )
        return FieldEvidenceChain(
            project_id=project_id,
            field_name=field_name,
            entity=entity,
            suggestion=suggestion,
            definitions=comparison_result.definitions,
            evidence_chunks=filtered_chunks,
            has_conflicts=comparison_result.has_conflicts,
            conflict_summary=comparison_result.conflict_summary,
            source_count=len(source_document_ids),
            warnings=warnings,
        )

    def get_suggestion_evidence_chain(
        self,
        project_id: str,
        suggestion_id: str,
        scope: str = "fields",
        max_chunks: int = 10,
    ) -> SuggestionEvidenceChain:
        supported_scope_types = {
            "fields": "field",
            "validations": "validation",
            "rules": "rule",
            "cross_entity_rules": "cross_entity_rule",
            "mappings": "mapping",
            "transforms": "transform",
            "conflict_resolution": "conflict_resolution",
            "portfolio_reuse": "portfolio_reuse",
            "identity_role": "identity_role",
        }
        if scope not in supported_scope_types:
            return SuggestionEvidenceChain(
                success=False,
                project_id=project_id,
                suggestion_id=suggestion_id,
                scope=scope,
                unsupported_scope=True,
                warnings=[
                    (
                        f"Unsupported suggestion scope '{scope}'. Supported scopes are "
                        "fields, validations, rules, cross_entity_rules, mappings, "
                        "conflict_resolution, portfolio_reuse, transforms, and identity_role."
                    )
                ],
            )

        row = self.conn.execute(
            """
            SELECT suggestion_type, status, edited_payload, suggestion_payload
            FROM manifest_suggestions
            WHERE suggestion_id = ? AND project_id = ?
            """,
            (suggestion_id, project_id),
        ).fetchone()
        if row is None:
            return SuggestionEvidenceChain(
                success=False,
                project_id=project_id,
                suggestion_id=suggestion_id,
                scope=scope,
                warnings=[f"suggestion not found for project_id {project_id}: {suggestion_id}"],
            )

        suggestion_type = row["suggestion_type"]
        if suggestion_type != supported_scope_types[scope]:
            return SuggestionEvidenceChain(
                success=False,
                project_id=project_id,
                suggestion_id=suggestion_id,
                scope=scope,
                warnings=[
                    (
                        f"suggestion '{suggestion_id}' has type '{suggestion_type}', "
                        f"not scope '{scope}'."
                    )
                ],
            )

        payload = json.loads(row["suggestion_payload"])
        payload["status"] = row["status"]
        payload["edited_payload"] = json.loads(row["edited_payload"]) if row["edited_payload"] else None
        if suggestion_type != "field":
            suggestion = ManifestSuggestion.model_validate(payload)
            chunks = self._evidence_chunks_for_manifest_suggestion(
                project_id=project_id,
                suggestion=suggestion,
                max_chunks=max_chunks,
            )
            source_document_ids = set(suggestion.source_document_ids)
            source_document_ids.update(chunk.document_id for chunk in chunks)
            return SuggestionEvidenceChain(
                project_id=project_id,
                suggestion_id=suggestion_id,
                scope=scope,
                field_name=suggestion.field,
                entity=suggestion.entity,
                suggestion=suggestion,
                evidence_chunks=chunks,
                source_count=len(source_document_ids),
                warnings=suggestion.warnings,
            )

        field_name = payload.get("field_name")
        if not isinstance(field_name, str) or not field_name:
            return SuggestionEvidenceChain(
                success=False,
                project_id=project_id,
                suggestion_id=suggestion_id,
                scope="fields",
                warnings=[f"field suggestion payload missing field_name: {suggestion_id}"],
            )

        entity = payload.get("entity")
        chain = self.get_field_evidence_chain(
            project_id=project_id,
            field_name=field_name,
            entity=entity if isinstance(entity, str) else None,
            max_chunks=max_chunks,
        )
        return SuggestionEvidenceChain(
            project_id=project_id,
            suggestion_id=suggestion_id,
            scope="fields",
            field_name=chain.field_name,
            entity=chain.entity,
            suggestion=chain.suggestion,
            definitions=chain.definitions,
            evidence_chunks=chain.evidence_chunks,
            has_conflicts=chain.has_conflicts,
            conflict_summary=chain.conflict_summary,
            source_count=chain.source_count,
            warnings=chain.warnings,
        )

    def _evidence_chunks_for_manifest_suggestion(
        self,
        *,
        project_id: str,
        suggestion: ManifestSuggestion,
        max_chunks: int,
    ) -> list[EvidenceChunk]:
        max_chunks = max(1, min(max_chunks, 50))
        citation_chunk_ids = [citation.chunk_id for citation in suggestion.citations]
        evidence_project_id = project_id
        if suggestion.suggestion_type == "portfolio_reuse":
            matched_project_id = suggestion.payload.get("matched_project_id")
            if isinstance(matched_project_id, str) and matched_project_id:
                evidence_project_id = matched_project_id
        chunks: list[EvidenceChunk] = []
        if citation_chunk_ids:
            placeholders = ",".join("?" * len(citation_chunk_ids))
            rows = self.conn.execute(
                f"""
                SELECT
                    c.chunk_id,
                    c.document_id,
                    c.section,
                    c.heading,
                    c.char_offset,
                    c.content_hash,
                    c.parser_version,
                    c.content,
                    0.0 AS score,
                    d.name,
                    d.doc_type
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.project_id = ?
                  AND c.chunk_id IN ({placeholders})
                  AND d.deleted_at IS NULL
                ORDER BY c.rowid
                LIMIT ?
                """,
                [evidence_project_id, *citation_chunk_ids, max_chunks],
            ).fetchall()
            chunks = [self._evidence_chunk_from_row(row) for row in rows]

        if chunks:
            return chunks

        terms = [
            str(value)
            for value in [
                suggestion.entity,
                suggestion.field,
                suggestion.payload.get("target_entity"),
                suggestion.payload.get("source_entity"),
                suggestion.payload.get("source_field"),
                suggestion.payload.get("target_field"),
                suggestion.payload.get("rule_id"),
                suggestion.payload.get("route_name"),
                suggestion.payload.get("query"),
                suggestion.payload.get("document_a_name"),
                suggestion.payload.get("document_b_name"),
                suggestion.payload.get("matched_document_name"),
                suggestion.payload.get("source"),
                suggestion.payload.get("target"),
                suggestion.payload.get("target_id"),
                suggestion.payload.get("suggested_role"),
                suggestion.payload.get("rationale"),
            ]
            if value
        ]
        evidence_result = self.get_evidence(
            project_id=evidence_project_id,
            query=" ".join(terms),
            max_chunks=max_chunks,
        )
        scoped_document_ids = set(suggestion.source_document_ids)
        if scoped_document_ids:
            return [
                chunk
                for chunk in evidence_result.chunks
                if chunk.document_id in scoped_document_ids
            ]
        return evidence_result.chunks

    def _field_catalog_rows(
        self,
        *,
        project_id: str,
        entity: str | None = None,
        field_name_pattern: str | None = None,
    ) -> list[sqlite3.Row]:
        clauses = ["f.project_id = ?", "d.deleted_at IS NULL"]
        params: list[Any] = [project_id]
        if entity:
            clauses.append("LOWER(f.entity_name) = LOWER(?)")
            params.append(entity)
        if field_name_pattern:
            clauses.append("LOWER(f.field_name) LIKE LOWER(?)")
            params.append(f"%{field_name_pattern}%")
        return self.conn.execute(
            f"""
            SELECT f.*, d.name AS document_name, d.doc_type, d.ingested_at
            FROM field_catalog f
            JOIN documents d ON d.id = f.document_id
            WHERE {' AND '.join(clauses)}
            ORDER BY f.entity_name, f.field_name, d.ingested_at
            """,
            params,
        ).fetchall()

    def _identity_field_rows(
        self,
        *,
        project_id: str,
        entity: str | None,
        field_name_pattern: str | None,
    ) -> list[sqlite3.Row]:
        rows = self._field_catalog_rows(project_id=project_id)
        if entity:
            requested_entity_key = _identity_entity_key(entity)
            rows = [
                row
                for row in rows
                if row["entity_name"] and _identity_entity_key(row["entity_name"]) == requested_entity_key
            ]
        if field_name_pattern:
            pattern = field_name_pattern.lower()
            pattern_key = _mapping_token_key(field_name_pattern)
            rows = [
                row
                for row in rows
                if pattern in (row["field_name"] or "").lower()
                or pattern_key == _mapping_token_key(row["field_name"] or "")
            ]
        return rows

    def _project_chunk_rows(self, project_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT
                c.chunk_id,
                c.document_id,
                c.project_id,
                c.section,
                c.heading,
                c.char_offset,
                c.content_hash,
                c.parser_version,
                c.content,
                d.name,
                d.doc_type
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.project_id = ? AND d.deleted_at IS NULL
            ORDER BY d.ingested_at, c.rowid
            """,
            (project_id,),
        ).fetchall()

    def _known_entities(self, project_id: str) -> set[str]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT LOWER(entity_name) AS entity_name
            FROM field_catalog f
            JOIN documents d ON d.id = f.document_id
            WHERE f.project_id = ? AND f.entity_name IS NOT NULL AND d.deleted_at IS NULL
            """,
            (project_id,),
        ).fetchall()
        return {row["entity_name"] for row in rows}

    def _active_project_ids(self, *, exclude_project_id: str | None = None) -> list[str]:
        clauses = ["deleted_at IS NULL"]
        params: list[Any] = []
        if exclude_project_id is not None:
            clauses.append("project_id != ?")
            params.append(exclude_project_id)
        rows = self.conn.execute(
            f"""
            SELECT DISTINCT project_id
            FROM documents
            WHERE {' AND '.join(clauses)}
            ORDER BY project_id
            """,
            params,
        ).fetchall()
        return [row["project_id"] for row in rows]

    def _catalog_field_index(self, project_id: str) -> set[tuple[str, str]]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT LOWER(entity_name) AS entity_name, LOWER(field_name) AS field_name
            FROM field_catalog f
            JOIN documents d ON d.id = f.document_id
            WHERE f.project_id = ?
              AND f.entity_name IS NOT NULL
              AND f.field_name IS NOT NULL
              AND d.deleted_at IS NULL
            """,
            (project_id,),
        ).fetchall()
        return {(row["entity_name"], row["field_name"]) for row in rows}

    def _citation_for_document(self, project_id: str, document_id: str) -> Citation | None:
        row = self.conn.execute(
            """
            SELECT
                c.chunk_id,
                c.document_id,
                c.section,
                c.heading,
                c.char_offset,
                c.content_hash,
                c.parser_version,
                c.content,
                d.name,
                d.doc_type
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.project_id = ? AND c.document_id = ? AND d.deleted_at IS NULL
            ORDER BY c.rowid
            LIMIT 1
            """,
            (project_id, document_id),
        ).fetchone()
        if row is None:
            return None
        return _citation(row, _short_excerpt(row["content"]))

    def _build_manifest_suggestion(
        self,
        *,
        project_id: str,
        suggestion_type: str,
        key: str,
        entity: str | None,
        field_name: str | None,
        title: str,
        summary: str,
        rationale: str,
        target_step: str,
        manifest_path: str,
        payload: dict[str, Any],
        citations: list[Citation],
        confidence: float,
        confidence_basis: str,
        warnings: list[str] | None = None,
    ) -> ManifestSuggestion:
        suggestion_id = stable_manifest_suggestion_id(project_id, suggestion_type, key)
        status, edited_payload, _ = self._load_suggestion_review_state(
            project_id,
            suggestion_id,
            suggestion_type=suggestion_type,
        )
        now = datetime.now(timezone.utc).isoformat()
        source_document_ids = sorted({citation.document_id for citation in citations})
        return ManifestSuggestion(
            suggestion_id=suggestion_id,
            suggestion_type=suggestion_type,
            project_id=project_id,
            status=status,
            confidence=confidence,
            confidence_basis=confidence_basis,
            title=title,
            summary=summary,
            rationale=rationale,
            target_step=target_step,
            manifest_path=manifest_path,
            payload=payload,
            citations=citations,
            source_document_ids=source_document_ids,
            entity=entity,
            field=field_name,
            created_at=now,
            updated_at=now,
            edited_payload=edited_payload,
            warnings=warnings or [],
        )

    def _find_document(self, project_id: str, document_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM documents WHERE id = ? AND project_id = ? AND deleted_at IS NULL",
            (document_id, project_id),
        ).fetchone()

    def _find_document_any_state(self, project_id: str, document_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM documents WHERE id = ? AND project_id = ?",
            (document_id, project_id),
        ).fetchone()

    def _load_suggestion_status(self, project_id: str, suggestion_id: str) -> str:
        status, _, _ = self._load_suggestion_review_state(project_id, suggestion_id)
        return status

    def _load_suggestion_review_state(
        self,
        project_id: str,
        suggestion_id: str,
        suggestion_type: str | None = None,
    ) -> tuple[str, dict[str, Any] | None, str | None]:
        row = self.conn.execute(
            """
            SELECT status, edited_payload, reviewed_at
            FROM manifest_suggestions
            WHERE suggestion_id = ? AND project_id = ?
            """,
            (suggestion_id, project_id),
        ).fetchone()
        if row is not None:
            edited_payload = json.loads(row["edited_payload"]) if row["edited_payload"] else None
            return str(row["status"]), edited_payload, row["reviewed_at"]

        if suggestion_type != "identity_role":
            return "pending", None, None

        preserved_row = self.conn.execute(
            """
            SELECT status, edited_payload, reviewed_at
            FROM manifest_suggestion_review_state
            WHERE suggestion_id = ?
              AND project_id = ?
              AND suggestion_type = 'identity_role'
            """,
            (suggestion_id, project_id),
        ).fetchone()
        if preserved_row is None:
            return "pending", None, None
        edited_payload = (
            json.loads(preserved_row["edited_payload"])
            if preserved_row["edited_payload"]
            else None
        )
        return str(preserved_row["status"]), edited_payload, preserved_row["reviewed_at"]

    def _upsert_field_suggestion(self, *, project_id: str, suggestion: FieldSuggestion) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO manifest_suggestions (
                    suggestion_id,
                    project_id,
                    suggestion_type,
                    entity_name,
                    field_name,
                    status,
                    edited_payload,
                    suggestion_payload,
                    created_at,
                    updated_at,
                    reviewed_at
                ) VALUES (?, ?, 'field', ?, ?, ?, NULL, ?, ?, ?, NULL)
                ON CONFLICT(suggestion_id) DO UPDATE SET
                    project_id = excluded.project_id,
                    suggestion_type = excluded.suggestion_type,
                    entity_name = excluded.entity_name,
                    field_name = excluded.field_name,
                    suggestion_payload = excluded.suggestion_payload,
                    updated_at = excluded.updated_at
                """,
                (
                    suggestion.suggestion_id,
                    project_id,
                    suggestion.entity,
                    suggestion.field_name,
                    suggestion.status,
                    json.dumps(suggestion.model_dump()),
                    now,
                    now,
                ),
            )

    def _upsert_manifest_suggestion(self, suggestion: ManifestSuggestion) -> None:
        now = datetime.now(timezone.utc).isoformat()
        field_name = suggestion.field or suggestion.payload.get("field") or suggestion.payload.get("rule_id")
        _, _, reviewed_at = self._load_suggestion_review_state(
            suggestion.project_id,
            suggestion.suggestion_id,
            suggestion_type=suggestion.suggestion_type,
        )
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO manifest_suggestions (
                    suggestion_id,
                    project_id,
                    suggestion_type,
                    entity_name,
                    field_name,
                    status,
                    edited_payload,
                    suggestion_payload,
                    created_at,
                    updated_at,
                    reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(suggestion_id) DO UPDATE SET
                    project_id = excluded.project_id,
                    suggestion_type = excluded.suggestion_type,
                    entity_name = excluded.entity_name,
                    field_name = excluded.field_name,
                    suggestion_payload = excluded.suggestion_payload,
                    updated_at = excluded.updated_at
                """,
                (
                    suggestion.suggestion_id,
                    suggestion.project_id,
                    suggestion.suggestion_type,
                    suggestion.entity,
                    str(field_name or suggestion.suggestion_id),
                    suggestion.status,
                    json.dumps(suggestion.edited_payload)
                    if suggestion.edited_payload is not None
                    else None,
                    json.dumps(suggestion.model_dump()),
                    now,
                    now,
                    reviewed_at,
                ),
            )

    def _evidence_chunk_from_row(self, row: sqlite3.Row) -> EvidenceChunk:
        return EvidenceChunk(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            document_name=row["name"],
            doc_type=row["doc_type"],
            section=row["section"],
            heading=row["heading"],
            page=_page_from_section(row["section"], row["parser_version"]),
            char_offset=row["char_offset"],
            content=row["content"],
            content_hash=row["content_hash"],
            parser_version=row["parser_version"],
            score=float(row["score"]),
            citation=_citation(row, row["content"]),
        )

    def _field_evidence_from_row(self, row: sqlite3.Row) -> FieldEvidence:
        return FieldEvidence(
            document_id=row["document_id"],
            document_name=row["document_name"],
            doc_type=row["doc_type"],
            field_type=row["field_type"],
            nullable=None if row["nullable"] is None else bool(row["nullable"]),
            description=row["description"],
            source_location=row["source_location"],
            length=row["length"],
            precision=row["precision"],
            scale=row["scale"],
        )

    def _search_chunk_rows(
        self,
        *,
        project_id: str,
        safe_query: str,
        doc_types: list[str] | None,
        limit: int,
        include_snippet: bool,
    ) -> list[sqlite3.Row]:
        doc_type_clause = ""
        params: list[Any] = [safe_query, project_id]
        if doc_types:
            placeholders = ",".join("?" * len(doc_types))
            doc_type_clause = f"AND d.doc_type IN ({placeholders})"
            params.extend(doc_types)
        params.append(limit)
        snippet_select = (
            "snippet(document_chunks, 8, '[', ']', '...', 16) AS snippet,"
            if include_snippet
            else "c.content AS snippet,"
        )
        return self.conn.execute(
            f"""
            SELECT
                c.chunk_id,
                c.document_id,
                c.section,
                c.heading,
                c.char_offset,
                c.content_hash,
                c.parser_version,
                c.content,
                {snippet_select}
                bm25(document_chunks) AS score,
                d.name,
                d.doc_type
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE document_chunks MATCH ?
              AND c.project_id = ?
              AND d.deleted_at IS NULL
              {doc_type_clause}
            ORDER BY score
            LIMIT ?
            """,
            params,
        ).fetchall()


def stable_document_id(project_id: str, path: Path, entity_name: str | None = None) -> str:
    """Derive a stable document ID from project + resolved file path (not content)."""
    suffix = f":{entity_name}" if entity_name else ""
    return hashlib.sha256(f"{project_id}:{path.resolve()}{suffix}".encode()).hexdigest()[:24]


def stable_chunk_id(document_id: str, position: int) -> str:
    return hashlib.sha256(f"{document_id}:{position}".encode()).hexdigest()[:24]


def stable_field_id(document_id: str, position: int, field_name: str) -> str:
    return hashlib.sha256(f"{document_id}:{position}:{field_name}".encode()).hexdigest()[:24]


def _document_content_fingerprint(chunks: list[TextChunk], fields: list[CsvField]) -> tuple[str, ...]:
    chunk_fingerprint = tuple(
        f"chunk:{chunk.content_hash}"
        for chunk in sorted(chunks, key=lambda item: item.position)
    )
    field_fingerprint = tuple(
        f"field:{_stable_json_hash(_field_fingerprint_payload(field))}"
        for field in sorted(
            fields,
            key=lambda item: (
                item.entity or "",
                item.name,
                item.source_location,
            ),
        )
    )
    return (*chunk_fingerprint, *field_fingerprint)


def _field_fingerprint_payload(field: CsvField) -> dict[str, Any]:
    return {
        "entity_name": field.entity,
        "field_name": field.name,
        "field_type": field.type,
        "length": field.length,
        "precision": field.precision,
        "scale": field.scale,
        "nullable": field.nullable,
        "description": field.description,
        "source_location": field.source_location,
        "source_metadata": json.dumps(field.source_metadata or {}, sort_keys=True),
    }


def _stored_field_fingerprint_payload(row: sqlite3.Row) -> dict[str, Any]:
    nullable = row["nullable"]
    return {
        "entity_name": row["entity_name"],
        "field_name": row["field_name"],
        "field_type": row["field_type"],
        "length": row["length"],
        "precision": row["precision"],
        "scale": row["scale"],
        "nullable": None if nullable is None else bool(nullable),
        "description": row["description"],
        "source_location": row["source_location"],
        "source_metadata": json.dumps(
            _json_object_or_empty(row["source_metadata"]),
            sort_keys=True,
        ),
    }


def _json_object_or_empty(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _stable_json_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _suggestion_payload_references_document(value: Any, document_id: str) -> bool:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if _document_reference_key_matches(key, nested_value, document_id):
                return True
            if _suggestion_payload_references_document(nested_value, document_id):
                return True
        return False
    if isinstance(value, list):
        return any(
            _suggestion_payload_references_document(item, document_id)
            for item in value
        )
    return False


def _document_ids_from_suggestion_payload(value: Any) -> set[str]:
    document_ids: set[str] = set()
    if isinstance(value, dict):
        for key, nested_value in value.items():
            normalized_key = key.lower()
            if normalized_key == "source_document_ids" and isinstance(nested_value, list):
                document_ids.update(item for item in nested_value if isinstance(item, str))
            elif (
                isinstance(nested_value, str)
                and (
                    normalized_key == "document_id"
                    or normalized_key.endswith("_document_id")
                    or normalized_key in {"document_a_id", "document_b_id"}
                )
            ):
                document_ids.add(nested_value)
            document_ids.update(_document_ids_from_suggestion_payload(nested_value))
    elif isinstance(value, list):
        for item in value:
            document_ids.update(_document_ids_from_suggestion_payload(item))
    return document_ids


def _document_reference_key_matches(key: str, value: Any, document_id: str) -> bool:
    normalized_key = key.lower()
    if normalized_key == "source_document_ids" and isinstance(value, list):
        return document_id in value
    if not isinstance(value, str) or value != document_id:
        return False
    return (
        normalized_key == "document_id"
        or normalized_key.endswith("_document_id")
        or normalized_key in {"document_a_id", "document_b_id"}
    )


def stable_field_suggestion_id(project_id: str, entity_name: str | None, field_name: str) -> str:
    normalized_entity = _normalize_optional_entity(entity_name) or ""
    normalized_field_name = _normalize_field_name(field_name)
    seed = f"field:{project_id}:{normalized_entity}:{normalized_field_name}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def stable_manifest_suggestion_id(project_id: str, suggestion_type: str, key: str) -> str:
    seed_type_by_suggestion_type = {
        "conflict_resolution": "conflict",
        "portfolio_reuse": "portfolio",
    }
    seed_type = seed_type_by_suggestion_type.get(suggestion_type, suggestion_type)
    seed = f"{seed_type}:{project_id}:{_compact_key(key)}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _normalize_fts_query(query: str) -> str:
    """Convert arbitrary user text into a safe FTS5 query.

    Extracts word tokens (\\w+) and joins them with OR so that natural-language
    questions and punctuation-laden strings never raise sqlite3.OperationalError.
    Returns an empty string when no tokens are found.
    """
    tokens = re.findall(r"\w+", query)
    if not tokens:
        return ""
    # Quote each token to prevent FTS5 from interpreting them as syntax.
    return " OR ".join(f'"{t}"' for t in tokens)


def _citation(row: sqlite3.Row | dict[str, Any], snippet: str) -> Citation:
    page = _page_from_section(row["section"], row["parser_version"])
    return Citation(
        document_id=row["document_id"],
        document_name=row["name"],
        chunk_id=row["chunk_id"],
        content_hash=row["content_hash"],
        parser_version=row["parser_version"],
        page=page,
        section=row["section"],
        heading=row["heading"],
        char_offset=row["char_offset"],
        snippet=snippet,
    )


def _page_from_section(section: str | None, parser_version: str) -> int | None:
    if parser_version != "pdf-v1":
        return None
    match = re.fullmatch(r"Page (\d+)", section or "")
    return int(match.group(1)) if match else None


def _normalize_field_name(field_name: str) -> str:
    return re.sub(r"\s+", "", field_name).strip().lower()


def _normalize_optional_entity(entity_name: str | None) -> str | None:
    if entity_name is None:
        return None
    return entity_name.strip().lower() or None


def _most_common_value(values: list[Any]) -> Any:
    non_none_values = [value for value in values if value is not None]
    if not non_none_values:
        return None
    counts: dict[Any, int] = {}
    for value in non_none_values:
        counts[value] = counts.get(value, 0) + 1
    highest_count = max(counts.values())
    winners = [value for value, count in counts.items() if count == highest_count]
    if len(winners) != 1:
        return None
    return winners[0]


def _value_conflict_summary(label: str, values: list[Any], document_names: list[str]) -> str | None:
    value_to_documents: dict[Any, list[str]] = {}
    for value, document_name in zip(values, document_names, strict=False):
        if value is None:
            continue
        documents = value_to_documents.setdefault(value, [])
        if document_name not in documents:
            documents.append(document_name)
    if len(value_to_documents) <= 1:
        return None
    parts = [
        f"{_short_conflict_value(value)} in {_format_conflict_documents(documents)}"
        for value, documents in sorted(value_to_documents.items(), key=lambda item: repr(item[0]))
    ]
    if len(parts) > 4:
        parts = [*parts[:4], f"+{len(parts) - 4} more values"]
    return f"{label}: {'; '.join(parts)}"


def _field_row_matches_conflict_query(
    row: sqlite3.Row,
    query: str,
    entity: str | None,
) -> bool:
    normalized_query = query.strip().lower()
    query_tokens = _mapping_token_key(query)
    field_name = row["field_name"] or ""
    entity_name = row["entity_name"] or ""
    document_name = row["document_name"] or ""
    description = row["description"] or ""
    haystacks = [field_name.lower(), entity_name.lower(), document_name.lower(), description.lower()]
    if any(normalized_query in item for item in haystacks):
        return True
    return bool(query_tokens) and query_tokens == _mapping_token_key(field_name)


def _first_field_rows_by_document(rows: list[sqlite3.Row]) -> dict[str, sqlite3.Row]:
    first_by_document: dict[str, sqlite3.Row] = {}
    for row in rows:
        first_by_document.setdefault(row["document_id"], row)
    return first_by_document


def _field_delta_category(row_a: sqlite3.Row, row_b: sqlite3.Row) -> str:
    field_a = row_a["field_name"]
    field_b = row_b["field_name"]
    type_a = row_a["field_type"]
    type_b = row_b["field_type"]
    family_a = _mapping_type_family(type_a)
    family_b = _mapping_type_family(type_b)
    name_differs = field_a != field_b
    type_differs = (type_a or "").lower() != (type_b or "").lower()
    if family_a is not None and family_b is not None and family_a != family_b:
        return "type difference"
    if row_a["nullable"] is not None and row_b["nullable"] is not None:
        if bool(row_a["nullable"]) != bool(row_b["nullable"]):
            return "nullable difference"
    if _catalog_shape_differs(row_a, row_b):
        return "catalog shape difference"
    if name_differs or type_differs:
        if _mapping_types_are_compatible(type_a, type_b):
            return "compatible normalization"
        return "naming difference"
    if _description_delta(row_a["description"], row_b["description"]):
        return "description/semantic difference"
    return "source overlap/no actionable conflict"


def _catalog_shape_differs(row_a: sqlite3.Row, row_b: sqlite3.Row) -> bool:
    if _shape_difference_is_normalized_string_length(row_a, row_b):
        return False
    return any(
        row_a[key] != row_b[key]
        for key in ["length", "precision", "scale"]
        if row_a[key] is not None or row_b[key] is not None
    )


def _shape_difference_is_normalized_string_length(row_a: sqlite3.Row, row_b: sqlite3.Row) -> bool:
    if _mapping_type_family(row_a["field_type"]) != "string":
        return False
    if _mapping_type_family(row_b["field_type"]) != "string":
        return False
    if row_a["precision"] is not None or row_a["scale"] is not None:
        return False
    if row_b["precision"] is not None or row_b["scale"] is not None:
        return False
    lengths = [row_a["length"], row_b["length"]]
    return any(length == 36 for length in lengths) and any(length is None for length in lengths)


def _description_delta(description_a: str | None, description_b: str | None) -> bool:
    if not description_a or not description_b:
        return False
    normalized_a = _compact_key(description_a)
    normalized_b = _compact_key(description_b)
    if normalized_a == normalized_b:
        return False
    return normalized_a not in normalized_b and normalized_b not in normalized_a


def _friendly_delta_field(source_a_field: str, source_b_field: str | None) -> str:
    if source_b_field is None or source_a_field == source_b_field:
        return source_a_field
    return source_a_field if len(source_a_field) <= len(source_b_field) else source_b_field


def _field_delta_summary(
    *,
    difference_category: str,
    source_a_document_name: str,
    source_a_field: str,
    source_a_type: str | None,
    source_b_document_name: str,
    source_b_field: str | None,
    source_b_type: str | None,
) -> str:
    if difference_category == "missing field in one source":
        return (
            f"{source_a_document_name} defines {source_a_field}, but "
            f"{source_b_document_name} does not define a compatible field."
        )
    source_b_display = source_b_field or "<missing>"
    return (
        f"{difference_category}: {source_a_document_name} has "
        f"{source_a_field} ({source_a_type or 'unknown'}), while "
        f"{source_b_document_name} has {source_b_display} ({source_b_type or 'unknown'})."
    )


def _field_delta_guidance(difference_category: str) -> tuple[str, str, float]:
    if difference_category == "compatible normalization":
        return (
            "The sources appear to describe the same field using compatible naming or type normalization.",
            "Treat this as advisory alignment, not a blocking conflict; confirm the normalized mapping.",
            0.66,
        )
    if difference_category == "missing field in one source":
        return (
            "One source defines the field while another source for the same entity does not.",
            "Review whether the missing source is incomplete or whether the field should be optional/out of scope.",
            0.78,
        )
    if difference_category == "type difference":
        return (
            "The sources define incompatible type families for the same normalized field.",
            "Choose the authoritative type or add an explicit transform/validation note.",
            0.86,
        )
    if difference_category == "catalog shape difference":
        return (
            "The sources use the same compatible type family but disagree on length, precision, or scale.",
            "Confirm the authoritative catalog shape before applying generated validation or schema constraints.",
            0.8,
        )
    if difference_category == "nullable difference":
        return (
            "The sources disagree on whether the field is required.",
            "Confirm requiredness with the source owner before applying validations.",
            0.82,
        )
    if difference_category == "description/semantic difference":
        return (
            "The sources use materially different descriptions for the same normalized field.",
            "Review the descriptions and preserve the authoritative business meaning.",
            0.72,
        )
    return (
        "The sources differ in field naming for a likely related field.",
        "Confirm whether the names represent the same manifest field.",
        0.7,
    )


def _short_conflict_value(value: Any, max_length: int = 80) -> str:
    rendered = repr(value)
    if len(rendered) <= max_length:
        return rendered
    return rendered[: max_length - 3].rstrip() + "..."


def _format_conflict_documents(documents: list[str], max_documents: int = 3) -> str:
    if len(documents) <= max_documents:
        return ", ".join(documents)
    shown = ", ".join(documents[:max_documents])
    return f"{shown}, +{len(documents) - max_documents} more"


def _dedupe_evidence_chunks(chunks: list[EvidenceChunk]) -> list[EvidenceChunk]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[EvidenceChunk] = []
    for chunk in chunks:
        key = (chunk.document_id, chunk.content_hash, chunk.content)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(chunk)
    return deduped


def _compact_key(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


@dataclass(frozen=True)
class _MappingMatch:
    target_row: sqlite3.Row | None
    confidence: float = 0.0
    confidence_basis: str = ""
    rationale: str = ""
    warning: str | None = None


def _select_mapping_match(
    source_row: sqlite3.Row,
    target_rows: list[sqlite3.Row],
    field_name_pattern: str | None,
) -> _MappingMatch:
    source_field = source_row["field_name"]
    pattern = field_name_pattern.lower() if field_name_pattern else None
    candidate_targets = [
        target_row
        for target_row in target_rows
        if pattern is None
        or pattern in source_field.lower()
        or pattern in target_row["field_name"].lower()
    ]
    exact_candidates = [
        target_row
        for target_row in candidate_targets
        if _mapping_exact_key(source_field) == _mapping_exact_key(target_row["field_name"])
        and _mapping_types_are_compatible(source_row["field_type"], target_row["field_type"])
    ]
    exact_confidence = 0.74
    exact_basis = "exact_name_match_type_unknown"
    if (
        exact_candidates
        and _mapping_type_family(source_row["field_type"]) is not None
        and _mapping_type_family(exact_candidates[0]["field_type"]) is not None
    ):
        exact_confidence = 0.92
        exact_basis = "exact_name_match_and_type_compatible"
    match = _single_mapping_candidate(
        source_row=source_row,
        candidates=exact_candidates,
        confidence=exact_confidence,
        confidence_basis=exact_basis,
        rationale=(
            f"Source field {source_field} exactly matches target field name after "
            "case/separator normalization."
        ),
    )
    if match.target_row is not None or match.warning:
        return match

    equivalent_candidates = [
        target_row
        for target_row in candidate_targets
        if _mapping_token_key(source_field) == _mapping_token_key(target_row["field_name"])
        and _mapping_types_are_compatible(source_row["field_type"], target_row["field_type"])
    ]
    match = _single_mapping_candidate(
        source_row=source_row,
        candidates=equivalent_candidates,
        confidence=0.86,
        confidence_basis="name_match_and_type_compatible",
        rationale=(
            f"Source field {source_field} matches target field name after "
            "camel/snake/kebab token normalization."
        ),
    )
    if match.target_row is not None or match.warning:
        return match

    prefix_suffix_candidates = [
        target_row
        for target_row in candidate_targets
        if _mapping_types_are_strictly_compatible(source_row["field_type"], target_row["field_type"])
        and _shares_mapping_prefix_or_suffix(source_field, target_row["field_name"])
    ]
    return _single_mapping_candidate(
        source_row=source_row,
        candidates=prefix_suffix_candidates,
        confidence=0.68,
        confidence_basis="prefix_or_suffix_match_and_type_compatible",
        rationale=(
            f"Source field {source_field} has a unique compatible prefix/suffix "
            "match in the target entity."
        ),
    )


def _select_transform_match(
    source_row: sqlite3.Row,
    target_rows: list[sqlite3.Row],
    field_name_pattern: str | None,
) -> _MappingMatch:
    source_field = source_row["field_name"]
    pattern = field_name_pattern.lower() if field_name_pattern else None
    candidate_targets = [
        target_row
        for target_row in target_rows
        if pattern is None
        or pattern in source_field.lower()
        or pattern in target_row["field_name"].lower()
    ]
    exact_candidates = [
        target_row
        for target_row in candidate_targets
        if _mapping_exact_key(source_field) == _mapping_exact_key(target_row["field_name"])
        and _mapping_types_are_compatible(source_row["field_type"], target_row["field_type"])
    ]
    match = _single_mapping_candidate(
        source_row=source_row,
        candidates=exact_candidates,
        confidence=0.9,
        confidence_basis="exact_name_match_and_type_compatible",
        rationale=(
            f"Source field {source_field} exactly matches target field name after "
            "case/separator normalization."
        ),
    )
    if match.target_row is not None or match.warning:
        return match

    equivalent_candidates = [
        target_row
        for target_row in candidate_targets
        if _mapping_token_key(source_field) == _mapping_token_key(target_row["field_name"])
        and _mapping_types_are_compatible(source_row["field_type"], target_row["field_type"])
    ]
    match = _single_mapping_candidate(
        source_row=source_row,
        candidates=equivalent_candidates,
        confidence=0.84,
        confidence_basis="name_match_and_type_compatible",
        rationale=(
            f"Source field {source_field} matches target field name after "
            "camel/snake/kebab token normalization."
        ),
    )
    if match.target_row is not None or match.warning:
        return match

    aligned_candidates = [
        target_row
        for target_row in candidate_targets
        if _mapping_types_are_strictly_compatible(source_row["field_type"], target_row["field_type"])
        and _shares_mapping_prefix_or_suffix(source_field, target_row["field_name"])
    ]
    return _single_mapping_candidate(
        source_row=source_row,
        candidates=aligned_candidates,
        confidence=0.66,
        confidence_basis="strong_name_alignment_and_type_compatible",
        rationale=(
            f"Source field {source_field} has a unique same-type prefix/suffix "
            "alignment in the target schema."
        ),
    )


def _single_mapping_candidate(
    *,
    source_row: sqlite3.Row,
    candidates: list[sqlite3.Row],
    confidence: float,
    confidence_basis: str,
    rationale: str,
) -> _MappingMatch:
    if not candidates:
        return _MappingMatch(target_row=None)
    if len(candidates) > 1:
        target_names = ", ".join(sorted({candidate["field_name"] for candidate in candidates}))
        return _MappingMatch(
            target_row=None,
            warning=(
                f"Ambiguous mapping for source field {source_row['entity_name']}."
                f"{source_row['field_name']}: candidate targets {target_names}; "
                "no suggestion persisted."
            ),
        )
    return _MappingMatch(
        target_row=candidates[0],
        confidence=confidence,
        confidence_basis=confidence_basis,
        rationale=rationale,
    )


def _dedupe_mapping_rows(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    deduped: dict[tuple[str | None, tuple[str, ...]], sqlite3.Row] = {}
    for row in rows:
        key = (_normalize_optional_entity(row["entity_name"]), _mapping_token_key(row["field_name"]))
        deduped.setdefault(key, row)
    return list(deduped.values())


def _mapping_exact_key(field_name: str) -> str:
    return re.sub(r"[-\s]+", "_", field_name.strip().lower())


def _mapping_token_key(field_name: str) -> tuple[str, ...]:
    return tuple(_identifier_tokens(field_name))


def _identifier_tokens(field_name: str) -> list[str]:
    tokens: list[str] = []
    for part in re.split(r"[^A-Za-z0-9]+", field_name):
        if not part:
            continue
        if part.isupper() or part.islower():
            tokens.append(part.lower())
            continue
        tokens.extend(
            token.lower()
            for token in re.split(r"(?<!^)(?=[A-Z])", part)
            if token
        )
    return tokens


def _shares_mapping_prefix_or_suffix(source_field: str, target_field: str) -> bool:
    source_tokens = _identifier_tokens(source_field)
    target_tokens = _identifier_tokens(target_field)
    if not source_tokens or not target_tokens:
        return False
    return source_tokens[0] == target_tokens[0] or source_tokens[-1] == target_tokens[-1]


def _mapping_types_are_compatible(source_type: str | None, target_type: str | None) -> bool:
    source_family = _mapping_type_family(source_type)
    target_family = _mapping_type_family(target_type)
    return source_family is None or target_family is None or source_family == target_family


def _mapping_types_are_strictly_compatible(source_type: str | None, target_type: str | None) -> bool:
    source_family = _mapping_type_family(source_type)
    target_family = _mapping_type_family(target_type)
    return source_family is not None and source_family == target_family


def _mapping_type_family(field_type: str | None) -> str | None:
    if not field_type:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "", field_type.lower())
    if normalized in {"string", "str", "text", "varchar", "char", "character"}:
        return "string"
    if normalized in {"int", "integer", "long", "bigint", "smallint", "short"}:
        return "integer"
    if normalized in {"decimal", "numeric", "number", "float", "double", "bigdecimal"}:
        return "decimal"
    if normalized in {"bool", "boolean"}:
        return "boolean"
    if normalized in {"date", "datetime", "timestamp", "time", "localdate", "localdatetime"}:
        return "date"
    return None


def _catalog_has_field(catalog_fields: set[tuple[str, str]], entity: str, field_name: str) -> bool:
    return (entity.lower(), field_name.lower()) in catalog_fields


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "item"


def _manifest_path_token(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "", value) or "item"


def _router_path_token(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "", value) or "item"


def _contains_token(content: str, token: str) -> bool:
    normalized_token = re.escape(token)
    spaced_token = re.escape(_camel_to_words(token))
    return bool(
        re.search(rf"\b{normalized_token}\b", content, flags=re.IGNORECASE)
        or re.search(rf"\b{spaced_token}\b", content, flags=re.IGNORECASE)
    )


def _camel_to_words(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", value).replace("_", " ")


IDENTITY_ROLE_VALUES = {
    "persistence_id",
    "parent_reference",
    "business_key",
    "event_id",
    "idempotency_key",
    "correlation_id",
    "external_reference",
}


def _identity_entity_key(entity_name: str | None) -> tuple[str, ...]:
    return _mapping_token_key(entity_name or "")


def _preferred_identity_entity_name(
    rows: list[sqlite3.Row],
    requested_entity: str | None = None,
) -> str:
    if requested_entity:
        return requested_entity
    values = [str(row["entity_name"]) for row in rows if row["entity_name"]]
    return _preferred_display_name(values)


def _preferred_identity_field_name(rows: list[sqlite3.Row]) -> str:
    values = [str(row["field_name"]) for row in rows if row["field_name"]]
    return _preferred_display_name(values)


def _preferred_display_name(values: list[str]) -> str:
    if not values:
        return ""
    return sorted(
        dict.fromkeys(values),
        key=lambda value: (
            "_" in value or value.isupper(),
            value.lower(),
        ),
    )[0]


def _identity_candidates_from_field_row(
    *,
    row: sqlite3.Row,
    entity: str,
    field_name: str,
    known_entity_keys: set[tuple[str, ...]],
) -> list[dict[str, Any]]:
    metadata = _field_source_metadata(row)
    description = str(row["description"] or "")
    candidates: list[dict[str, Any]] = []
    explicit_role = str(metadata.get("identity_role") or "").strip()
    if explicit_role in IDENTITY_ROLE_VALUES:
        candidates.append(
            _identity_candidate(
                role=explicit_role,
                signal="field_catalog_identity_hint",
                confidence=0.96,
                confidence_basis="field_catalog_identity_hint",
                rationale=(
                    f"{entity}.{field_name} has an explicit field-catalog "
                    f"identity_role hint of {explicit_role}."
                ),
            )
        )
    if metadata.get("primary_key"):
        candidates.append(
            _identity_candidate(
                role="persistence_id",
                signal="ddl_primary_key",
                confidence=0.95,
                confidence_basis="ddl_primary_key",
                rationale=f"DDL marks {entity}.{field_name} as a primary key.",
            )
        )
    if metadata.get("foreign_key"):
        reference = ".".join(
            str(value)
            for value in [metadata.get("referenced_entity"), metadata.get("referenced_field")]
            if value
        )
        candidates.append(
            _identity_candidate(
                role="parent_reference",
                signal="ddl_foreign_key",
                confidence=0.93,
                confidence_basis="ddl_foreign_key",
                rationale=(
                    f"DDL marks {entity}.{field_name} as a foreign key"
                    f"{f' referencing {reference}' if reference else ''}."
                ),
            )
        )
    if metadata.get("unique"):
        unique_role = _identity_role_for_unique_field(entity, field_name, description)
        candidates.append(
            _identity_candidate(
                role=unique_role,
                signal="ddl_unique_constraint",
                confidence=0.82,
                confidence_basis="ddl_unique_constraint",
                rationale=(
                    f"DDL marks {entity}.{field_name} as unique; KS treats it as "
                    f"{unique_role} pending human review."
                ),
            )
        )

    description_candidate = _identity_candidate_from_text(
        text=description,
        entity=entity,
        field_name=field_name,
        signal="field_catalog_identity_hint",
        confidence_basis="field_catalog_identity_hint",
        base_confidence=0.86,
    )
    if description_candidate is not None:
        candidates.append(description_candidate)

    naming_candidate = _identity_candidate_from_naming(
        entity=entity,
        field_name=field_name,
        known_entity_keys=known_entity_keys,
    )
    if naming_candidate is not None:
        candidates.append(naming_candidate)
    return candidates


def _field_source_metadata(row: sqlite3.Row) -> dict[str, Any]:
    raw = row["source_metadata"] if "source_metadata" in row.keys() else None
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _identity_candidate_from_text(
    *,
    text: str,
    entity: str,
    field_name: str,
    signal: str,
    confidence_basis: str,
    base_confidence: float,
    citation: Citation | None = None,
) -> dict[str, Any] | None:
    if not text:
        return None
    lowered = text.lower()
    role: str | None = None
    rationale: str | None = None
    if re.search(r"\b(primary key|row id|row identifier|surrogate id|persistence id)\b", lowered):
        role = "persistence_id"
        rationale = f"Source text describes {entity}.{field_name} as the row or persistence identity."
    elif re.search(r"\b(foreign key|references|parent reference|parent id|owning parent)\b", lowered):
        role = "parent_reference"
        rationale = f"Source text describes {entity}.{field_name} as a foreign-key or parent reference."
    elif re.search(r"\b(idempotenc|duplicate prevention|duplicate detection|retry key|replay)\b", lowered):
        role = "idempotency_key"
        rationale = f"Source text ties {entity}.{field_name} to duplicate prevention or retry safety."
    elif re.search(r"\b(correlation|trace id|trace identifier|request correlation)\b", lowered):
        role = "correlation_id"
        rationale = f"Source text ties {entity}.{field_name} to correlation or trace behavior."
    elif re.search(r"\b(external reference|provider reference|gateway reference|source system reference)\b", lowered):
        role = "external_reference"
        rationale = f"Source text ties {entity}.{field_name} to an external provider or source-system reference."
    elif _is_event_identity_field(entity, field_name) and re.search(
        r"\b(event id|transaction id|transaction identifier|externally supplied)\b", lowered
    ):
        role = "event_id"
        rationale = f"Source text describes {entity}.{field_name} as an event or transaction identifier."
    if role is None or rationale is None:
        return None
    return _identity_candidate(
        role=role,
        signal=signal,
        confidence=base_confidence,
        confidence_basis=confidence_basis,
        rationale=rationale,
        citations=[citation] if citation is not None else [],
    )


def _identity_candidates_from_text(
    *,
    content: str,
    entity: str,
    field_name: str,
    citation: Citation,
) -> list[dict[str, Any]]:
    relevant_text = _identity_relevant_text_window(content, field_name)
    if not relevant_text:
        return []
    candidate = _identity_candidate_from_text(
        text=relevant_text,
        entity=entity,
        field_name=field_name,
        signal="brd_identity_language",
        confidence_basis="brd_identity_language",
        base_confidence=0.88,
        citation=citation,
    )
    return [candidate] if candidate is not None else []


def _identity_candidate_from_naming(
    *,
    entity: str,
    field_name: str,
    known_entity_keys: set[tuple[str, ...]],
) -> dict[str, Any] | None:
    field_key = _mapping_token_key(field_name)
    if not field_key:
        return None
    compact_field = "".join(field_key)
    if compact_field in {"correlationid", "traceid", "requestcorrelationid"}:
        return _identity_candidate(
            role="correlation_id",
            signal="naming_convention",
            confidence=0.62,
            confidence_basis="naming_convention",
            rationale=f"{entity}.{field_name} follows a common correlation/trace identifier naming convention.",
        )
    if compact_field in {
        "externalreference",
        "sourcereference",
        "legacyid",
        "providerreference",
        "gatewaytransactionid",
    }:
        return _identity_candidate(
            role="external_reference",
            signal="naming_convention",
            confidence=0.62,
            confidence_basis="naming_convention",
            rationale=f"{entity}.{field_name} follows a common external-reference naming convention.",
        )
    parent_key = field_key[:-1] if field_key[-1:] == ("id",) else ()
    if parent_key and parent_key in known_entity_keys and parent_key != _identity_entity_key(entity):
        signal = "event_entity_guard" if _is_event_like_entity(entity) else "naming_convention"
        return _identity_candidate(
            role="parent_reference",
            signal=signal,
            confidence=0.66 if signal == "event_entity_guard" else 0.6,
            confidence_basis=signal,
            rationale=(
                f"{entity}.{field_name} looks like a reference to known entity "
                f"{''.join(parent_key)} and should not be treated as this row's persistence identity."
            ),
        )
    if _is_event_identity_field(entity, field_name):
        return _identity_candidate(
            role="event_id",
            signal="naming_convention",
            confidence=0.58,
            confidence_basis="naming_convention",
            rationale=(
                f"{entity}.{field_name} looks like an event or transaction identifier; "
                "this is advisory and not a persistence ID without stronger evidence."
            ),
        )
    return None


def _identity_role_for_unique_field(entity: str, field_name: str, description: str) -> str:
    text = f"{entity} {field_name} {description}".lower()
    if re.search(r"\b(idempotenc|duplicate prevention|duplicate detection|retry key|replay)\b", text):
        return "idempotency_key"
    return "business_key"


def _is_event_like_entity(entity: str) -> bool:
    tokens = set(_identity_entity_key(entity))
    return bool(tokens & {"transaction", "posting", "event", "history", "ledger", "activity", "movement", "log"})


def _is_event_identity_field(entity: str, field_name: str) -> bool:
    field_tokens = set(_mapping_token_key(field_name))
    return _is_event_like_entity(entity) and bool(field_tokens & {"transaction", "event", "posting"})


def _identity_candidate(
    *,
    role: str,
    signal: str,
    confidence: float,
    confidence_basis: str,
    rationale: str,
    citations: list[Citation] | None = None,
) -> dict[str, Any]:
    return {
        "role": role,
        "signal": signal,
        "confidence": confidence,
        "confidence_basis": confidence_basis,
        "rationale": rationale,
        "citations": citations or [],
    }


def _select_identity_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    priority = {
        "field_catalog_identity_hint": 7,
        "ddl_primary_key": 6,
        "ddl_foreign_key": 6,
        "ddl_unique_constraint": 5,
        "brd_identity_language": 4,
        "event_entity_guard": 3,
        "naming_convention": 2,
    }
    return sorted(
        candidates,
        key=lambda candidate: (
            -float(candidate["confidence"]),
            -priority.get(str(candidate["signal"]), 0),
            str(candidate["role"]),
        ),
    )[0]


def _identity_signals_for_role(candidates: list[dict[str, Any]], role: str) -> list[str]:
    signals: list[str] = []
    for candidate in candidates:
        if candidate.get("role") != role:
            continue
        signal = str(candidate.get("signal") or "")
        if signal and signal not in signals:
            signals.append(signal)
    return signals


def _identity_chunk_mentions_field(content: str, entity: str, field_name: str) -> bool:
    return (
        _contains_token(content, field_name)
        or _contains_token(content, _camel_to_words(field_name))
        or (
            _contains_token(content, entity)
            and any(_contains_token(content, token) for token in _mapping_token_key(field_name))
        )
    )


def _identity_relevant_text_window(content: str, field_name: str, max_radius: int = 180) -> str:
    patterns = [re.escape(field_name), re.escape(_camel_to_words(field_name))]
    for token in _mapping_token_key(field_name):
        if token != "id":
            patterns.append(re.escape(token))
    for pattern in patterns:
        match = re.search(rf"(?<![A-Za-z0-9]){pattern}(?![A-Za-z0-9])", content, flags=re.IGNORECASE)
        if match:
            line_start = content.rfind("\n", 0, match.start()) + 1
            line_end = content.find("\n", match.end())
            if line_end == -1:
                line_end = len(content)
            line = content[line_start:line_end].strip()
            if line:
                return line
            start = max(0, match.start() - max_radius)
            end = min(len(content), match.end() + max_radius)
            return content[start:end]
    return ""


def _dedupe_citations(citations: list[Citation]) -> list[Citation]:
    seen: set[tuple[str, str]] = set()
    deduped: list[Citation] = []
    for citation in citations:
        key = (citation.document_id, citation.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(citation)
    return deduped


def _short_excerpt(content: str, max_length: int = 320) -> str:
    text = re.sub(r"\s+", " ", content).strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def _extract_pattern_hint(content: str, field_name: str) -> str | None:
    field_pattern = re.escape(field_name)
    regex_match = re.search(
        rf"{field_pattern}[^.\n]{{0,80}}(?:match|matches|pattern|format)[^.\n]{{0,40}}(?:`([^`]+)`|/([^/]+)/)",
        content,
        flags=re.IGNORECASE,
    )
    if regex_match:
        return regex_match.group(1) or regex_match.group(2)

    words = _camel_to_words(field_name)
    nn_format = re.search(
        rf"(?:{field_pattern}|{re.escape(words)})[^.\n]{{0,80}}(?:format|pattern)[^.\n]{{0,80}}\b(?:NN|XX)-(?:NN|XX)-(?:NN|XX)\b",
        content,
        flags=re.IGNORECASE,
    )
    if nn_format:
        return r"^\d{2}-\d{2}-\d{2}$"
    return None


def _extract_allowed_values(content: str, entity: str, field_name: str) -> list[str] | None:
    entity_pattern = re.escape(entity)
    field_patterns = [re.escape(field_name), re.escape(_camel_to_words(field_name))]
    for field_pattern in field_patterns:
        match = re.search(
            rf"{entity_pattern}\s+{field_pattern}[^.\n]{{0,80}}must\s+(?:be\s+)?(?:one of|in|be)?\s*:?\s*([A-Z][A-Z0-9_ -]*(?:\s*,\s*[A-Z][A-Z0-9_ -]*)+(?:\s*(?:or|and)\s*[A-Z][A-Z0-9_ -]*)?)",
            content,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        raw_values = re.split(r",|\bor\b|\band\b", match.group(1))
        values = [
            re.sub(r"[^A-Za-z0-9_-].*$", "", value.strip())
            for value in raw_values
            if value.strip()
        ]
        values = [value for value in values if value and len(value) <= 40]
        if len(values) >= 2:
            return values
    return None


def _extract_range_constraint(content: str, entity: str, field_name: str) -> dict[str, Any] | None:
    entity_pattern = re.escape(entity)
    field_patterns = [re.escape(field_name), re.escape(_camel_to_words(field_name))]
    for field_pattern in field_patterns:
        between = re.search(
            rf"{entity_pattern}\s+{field_pattern}[^.\n]{{0,80}}must\s+be\s+between\s+(-?\d+(?:\.\d+)?)\s+and\s+(-?\d+(?:\.\d+)?)",
            content,
            flags=re.IGNORECASE,
        )
        if between:
            return {"min": _number_value(between.group(1)), "max": _number_value(between.group(2))}
        bounded = re.search(
            rf"{entity_pattern}\s+{field_pattern}[^.\n]{{0,80}}(?:>=|at least)\s*(-?\d+(?:\.\d+)?)[^.\n]{{0,80}}(?:<=|at most)\s*(-?\d+(?:\.\d+)?)",
            content,
            flags=re.IGNORECASE,
        )
        if bounded:
            return {"min": _number_value(bounded.group(1)), "max": _number_value(bounded.group(2))}
    return None


def _number_value(value: str) -> int | float:
    return float(value) if "." in value else int(value)


def _extract_relationships(content: str) -> list[dict[str, str]]:
    relationships: list[dict[str, str]] = []
    pattern = re.compile(
        r"\b(?P<source_entity>[A-Z][A-Za-z0-9_]*)\.(?P<source_field>[A-Za-z][A-Za-z0-9_]*)\s+"
        r"(?:references|refers\s+to|links\s+to)\s+"
        r"(?P<target_entity>[A-Z][A-Za-z0-9_]*)\.(?P<target_field>[A-Za-z][A-Za-z0-9_]*)\b",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(content):
        relationships.append(match.groupdict())
    return relationships


def _extract_cross_entity_conditions(
    *,
    content: str,
    source_entity: str,
    target_entity: str,
) -> list[dict[str, Any]]:
    conditions: list[dict[str, Any]] = []
    target = re.escape(target_entity)
    check_match = re.search(
        rf"{target}(?:\.|\s+)(?P<target_field>[A-Za-z][A-Za-z0-9_]*)[^.\n]{{0,80}}must\s+be\s+(?P<value>[A-Z0-9_-]+)",
        content,
        flags=re.IGNORECASE,
    )
    if check_match:
        target_field = check_match.group("target_field")
        expected_value = check_match.group("value")
        conditions.append(
            {
                "rule_type": "cross-entity-field-check",
                "target_field": target_field,
                "operator": "eq",
                "expected_value": expected_value,
                "description": f"{target_entity}.{target_field} must equal {expected_value}.",
            }
        )

    in_match = re.search(
        rf"{target}(?:\.|\s+)(?P<target_field>[A-Za-z][A-Za-z0-9_]*)[^.\n]{{0,80}}must\s+(?:be\s+)?(?:one of|in)\s*:?\s*(?P<values>[A-Z0-9_,\s-]+)",
        content,
        flags=re.IGNORECASE,
    )
    if in_match:
        values = [
            value.strip()
            for value in re.split(r",|\bor\b|\band\b", in_match.group("values"))
            if value.strip()
        ]
        if len(values) >= 2:
            target_field = in_match.group("target_field")
            conditions.append(
                {
                    "rule_type": "cross-entity-field-in",
                    "target_field": target_field,
                    "operator": "in",
                    "allowed_values": values,
                    "description": f"{target_entity}.{target_field} must be one of {', '.join(values)}.",
                }
            )

    source = re.escape(source_entity)
    compare_match = re.search(
        rf"{source}(?:\.|\s+)(?P<source_compare_field>[A-Za-z][A-Za-z0-9_]*)[^.\n]{{0,80}}"
        rf"(?:must\s+be\s+)?(?P<operator><=|>=|<|>)\s*"
        rf"{target}(?:\.|\s+)(?P<target_field>[A-Za-z][A-Za-z0-9_]*)",
        content,
        flags=re.IGNORECASE,
    )
    if compare_match:
        operator_map = {"<=": "lte", ">=": "gte", "<": "lt", ">": "gt"}
        source_field = compare_match.group("source_compare_field")
        target_field = compare_match.group("target_field")
        operator = operator_map[compare_match.group("operator")]
        conditions.append(
            {
                "rule_type": "cross-entity-field-compare",
                "target_field": target_field,
                "operator": operator,
                "compare_source_field": source_field,
                "description": (
                    f"{source_entity}.{source_field} must be {operator} "
                    f"{target_entity}.{target_field}."
                ),
            }
        )
    return conditions


def _validate_edited_payload(
    suggestion_type: str,
    edited_payload: dict[str, Any] | None,
    status: str,
    stored_payload: dict[str, Any],
) -> tuple[str | None, list[str]]:
    if edited_payload is None:
        if suggestion_type == "conflict_resolution" and status == "edited":
            return "edited_payload is required when editing conflict_resolution suggestions.", []
        if suggestion_type == "portfolio_reuse" and status == "edited":
            return "edited_payload is required when editing portfolio_reuse suggestions.", []
        if suggestion_type == "transform" and status == "edited":
            return "edited_payload is required when editing transform suggestions.", []
        if suggestion_type == "identity_role" and status == "edited":
            return "edited_payload is required when editing identity_role suggestions.", []
        return None, []
    if not isinstance(edited_payload, dict):
        return "edited_payload must be an object.", []
    if suggestion_type == "conflict_resolution" and status == "edited" and not edited_payload:
        return "edited_payload must not be empty when editing conflict_resolution suggestions.", []
    if suggestion_type == "portfolio_reuse" and status == "edited" and not edited_payload:
        return "edited_payload must not be empty when editing portfolio_reuse suggestions.", []
    if suggestion_type == "transform" and status == "edited" and not edited_payload:
        return "edited_payload must not be empty when editing transform suggestions.", []
    if suggestion_type == "identity_role" and status == "edited" and not edited_payload:
        return "edited_payload must not be empty when editing identity_role suggestions.", []

    validators = {
        "field": _validate_field_edited_payload,
        "rule": _validate_rule_edited_payload,
        "validation": _validate_validation_edited_payload,
        "cross_entity_rule": _validate_cross_entity_rule_edited_payload,
        "mapping": _validate_mapping_edited_payload,
        "transform": _validate_transform_edited_payload,
        "conflict_resolution": lambda payload: _validate_conflict_resolution_edited_payload(
            payload, stored_payload, status
        ),
        "portfolio_reuse": lambda payload: _validate_portfolio_reuse_edited_payload(
            payload, status
        ),
        "identity_role": _validate_identity_role_edited_payload,
    }
    validator = validators.get(suggestion_type)
    if validator is None:
        return None, [f"Unknown suggestion_type '{suggestion_type}'; edited_payload was stored without type validation."]
    return validator(edited_payload), []


def _validate_field_edited_payload(payload: dict[str, Any]) -> str | None:
    return _require_optional_strings(payload, ["manifest_path", "field_name"])


def _validate_rule_edited_payload(payload: dict[str, Any]) -> str | None:
    required_error = _require_strings(payload, ["entity", "rule_id", "rule_type", "field"])
    if required_error:
        return required_error
    if not isinstance(payload.get("constraint"), dict):
        return "edited_payload.constraint must be an object for rule suggestions."
    return None


def _validate_validation_edited_payload(payload: dict[str, Any]) -> str | None:
    required_error = _require_strings(payload, ["entity", "field", "validation_type"])
    if required_error:
        return required_error
    return None


def _validate_cross_entity_rule_edited_payload(payload: dict[str, Any]) -> str | None:
    required_error = _require_strings(
        payload,
        [
            "rule_id",
            "rule_type",
            "source_entity",
            "source_field",
            "target_entity",
            "target_field",
            "operator",
            "description",
        ],
    )
    if required_error:
        return required_error
    allowed_rule_types = {
        "cross-entity-field-check",
        "cross-entity-field-compare",
        "cross-entity-field-in",
    }
    if payload["rule_type"] not in allowed_rule_types:
        return (
            "edited_payload.rule_type must be one of cross-entity-field-check, "
            "cross-entity-field-compare, or cross-entity-field-in."
        )
    operator = payload["operator"]
    if payload["rule_type"] == "cross-entity-field-check":
        if operator not in {"eq", "neq", "lt", "lte", "gt", "gte"}:
            return "edited_payload.operator is invalid for cross-entity-field-check."
        if (
            not isinstance(payload.get("expected_value"), str)
            or not payload["expected_value"].strip()
        ):
            return (
                "edited_payload.expected_value must be a non-empty string for "
                "cross-entity-field-check."
            )
    if payload["rule_type"] == "cross-entity-field-in":
        if operator != "in":
            return "edited_payload.operator must be 'in' for cross-entity-field-in."
        allowed_values = payload.get("allowed_values")
        if not isinstance(allowed_values, list) or not allowed_values:
            return (
                "edited_payload.allowed_values must be a non-empty list for "
                "cross-entity-field-in."
            )
        if not all(isinstance(value, str) and value.strip() for value in allowed_values):
            return "edited_payload.allowed_values must contain only non-empty strings."
    if payload["rule_type"] == "cross-entity-field-compare":
        if operator not in {"eq", "neq", "lt", "lte", "gt", "gte"}:
            return "edited_payload.operator is invalid for cross-entity-field-compare."
        if (
            not isinstance(payload.get("compare_source_field"), str)
            or not payload["compare_source_field"].strip()
        ):
            return (
                "edited_payload.compare_source_field must be a non-empty string for "
                "cross-entity-field-compare."
            )
    return None


def _validate_mapping_edited_payload(payload: dict[str, Any]) -> str | None:
    required_error = _require_strings(
        payload,
        [
            "route_name",
            "direction",
            "source_entity",
            "target_entity",
            "source_field",
            "target_field",
            "mapping_type",
            "confidence_basis",
        ],
    )
    if required_error:
        return required_error
    if payload["direction"] not in {"request", "response"}:
        return "edited_payload.direction must be 'request' or 'response' for mapping suggestions."
    if payload["mapping_type"] != "copy":
        return "edited_payload.mapping_type must be 'copy' for KS-B3 mapping suggestions."
    if "value_map" in payload and payload["value_map"] is not None:
        return "edited_payload.value_map must be null or omitted for copy mappings."
    return None


def _validate_transform_edited_payload(payload: dict[str, Any]) -> str | None:
    allowed_keys = {
        "source",
        "target",
        "default_value",
        "constant",
        "value_map",
        "type_coercion",
        "rationale",
    }
    unknown_keys = sorted(set(payload) - allowed_keys)
    if unknown_keys:
        return (
            "edited_payload contains unsupported keys for transform suggestions: "
            f"{', '.join(unknown_keys)}."
        )
    if not isinstance(payload.get("target"), str) or not payload["target"].strip():
        return "edited_payload.target must be a non-empty string for transform suggestions."
    source = payload.get("source")
    constant = payload.get("constant")
    default_value = payload.get("default_value")
    if source is not None and (not isinstance(source, str) or not source.strip()):
        return "edited_payload.source must be a non-empty string when provided."
    if constant is not None and (not isinstance(constant, str) or not constant.strip()):
        return "edited_payload.constant must be a non-empty string when provided."
    if default_value is not None and not isinstance(default_value, str):
        return "edited_payload.default_value must be a string when provided."
    if source is None and constant is None and default_value is None:
        return (
            "edited_payload must include source, constant, or default_value "
            "for transform suggestions."
        )
    value_map = payload.get("value_map")
    if value_map is not None and not isinstance(value_map, dict):
        return "edited_payload.value_map must be an object when provided."
    type_coercion = payload.get("type_coercion")
    if type_coercion is not None and type_coercion not in {
        "major_to_minor_units",
        "minor_to_major_units",
    }:
        return (
            "edited_payload.type_coercion must be one of major_to_minor_units "
            "or minor_to_major_units."
        )
    rationale = payload.get("rationale")
    if rationale is not None and (not isinstance(rationale, str) or not rationale.strip()):
        return "edited_payload.rationale must be a non-empty string when provided."
    return None


def _validate_conflict_resolution_edited_payload(
    payload: dict[str, Any], stored_payload: dict[str, Any], status: str
) -> str | None:
    allowed_keys = {"preferred_document_id", "resolution_note", "rationale"}
    unknown_keys = sorted(set(payload) - allowed_keys)
    if unknown_keys:
        return (
            "edited_payload contains unsupported keys for conflict_resolution "
            f"suggestions: {', '.join(unknown_keys)}."
        )
    if status == "edited" and not any(key in payload for key in allowed_keys):
        return (
            "edited_payload must include at least one of preferred_document_id, "
            "resolution_note, or rationale for conflict_resolution suggestions."
        )

    preferred_document_id = payload.get("preferred_document_id")
    if preferred_document_id is not None:
        if not isinstance(preferred_document_id, str) or not preferred_document_id.strip():
            return "edited_payload.preferred_document_id must be a non-empty string."
        suggestion_payload = stored_payload.get("payload")
        if not isinstance(suggestion_payload, dict):
            suggestion_payload = stored_payload
        allowed_document_ids = {
            suggestion_payload.get("document_a_id"),
            suggestion_payload.get("document_b_id"),
        }
        if preferred_document_id not in allowed_document_ids:
            return (
                "edited_payload.preferred_document_id must match one of the "
                "conflicting document IDs."
            )
    for key in ["resolution_note", "rationale"]:
        value = payload.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            return f"edited_payload.{key} must be a non-empty string when provided."
    return None


def _validate_portfolio_reuse_edited_payload(payload: dict[str, Any], status: str) -> str | None:
    allowed_keys = {"reuse_note", "target_step", "target_manifest_path", "rationale"}
    unknown_keys = sorted(set(payload) - allowed_keys)
    if unknown_keys:
        return (
            "edited_payload contains unsupported keys for portfolio_reuse "
            f"suggestions: {', '.join(unknown_keys)}."
        )
    for key in allowed_keys:
        value = payload.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            return f"edited_payload.{key} must be a non-empty string when provided."
    has_reuse_note = isinstance(payload.get("reuse_note"), str) and bool(
        payload["reuse_note"].strip()
    )
    has_rationale = isinstance(payload.get("rationale"), str) and bool(
        payload["rationale"].strip()
    )
    if status == "edited" and not (has_reuse_note or has_rationale):
        return (
            "edited_payload must include reuse_note or rationale when editing "
            "portfolio_reuse suggestions."
        )
    return None


def _validate_identity_role_edited_payload(payload: dict[str, Any]) -> str | None:
    allowed_keys = {"entity", "field", "role", "suggested_role", "rationale"}
    unknown_keys = sorted(set(payload) - allowed_keys)
    if unknown_keys:
        return (
            "edited_payload contains unsupported keys for identity_role suggestions: "
            f"{', '.join(unknown_keys)}."
        )
    required_error = _require_strings(payload, ["entity", "field"])
    if required_error:
        return required_error
    role = payload.get("role", payload.get("suggested_role"))
    if not isinstance(role, str) or not role.strip():
        return "edited_payload.role or edited_payload.suggested_role must be a non-empty string."
    if role not in IDENTITY_ROLE_VALUES:
        return (
            "edited_payload.role must be one of persistence_id, parent_reference, "
            "business_key, event_id, idempotency_key, correlation_id, or external_reference."
        )
    if "rationale" in payload and (
        not isinstance(payload["rationale"], str) or not payload["rationale"].strip()
    ):
        return "edited_payload.rationale must be a non-empty string when provided."
    return None


def _require_strings(payload: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            return f"edited_payload.{key} must be a non-empty string."
    return None


def _require_optional_strings(payload: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        if key in payload and not isinstance(payload[key], str):
            return f"edited_payload.{key} must be a string when provided."
    return None
