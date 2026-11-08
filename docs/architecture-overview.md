# Knowledge Server Architecture Overview

EdgeForge Knowledge Server is a separate local stdio MCP server for
project-scoped document ingestion, deterministic SQLite FTS5/BM25 retrieval,
evidence lookup, and suggestion-only manifest guidance.

## Boundaries

- KS is local stdio only: no HTTP/SSE transport, no auth surface, and no network
  fetch behavior.
- KS is deterministic: no LLM, embeddings, or AI/provider inference.
- KS is suggestion-only: it produces evidence-backed candidates and persists
  review status, but Studio owns human review, apply workflows, generated
  artifacts, and manifest/package state.
- Engine consumes only approved Studio artifacts; KS neither produces nor
  consumes `app-definition.yaml` and does not call Engine at runtime.

## Data Flow

1. `ingest_document` reads a local file from `EDGEFORGE_KS_ALLOWED_ROOTS`.
2. A parser extracts document text, chunks, and field-catalog rows where
   supported.
3. `KnowledgeStore` persists documents, chunks, FTS rows, field catalog rows, and
   manifest suggestions in SQLite.
4. Retrieval tools query project-scoped chunks and field catalog data.
5. Suggestion tools generate deterministic, evidence-backed candidates and store
   stable suggestion IDs/status in `manifest_suggestions`.
6. `submit_suggestion_decisions` records Studio review decisions without
   mutating manifests.

## Persistence

The SQLite database is local. Ordinary retrieval is scoped by `project_id`;
cross-project search and generic portfolio-reuse suggestions/evidence can access
other projects in the same store. This is not tenant authorization; separate
trust domains need separate database/process boundaries.

Document soft delete hides a document from active retrieval and keeps indexed
data for audit. `purge_document(confirm_purge=True)` removes document-scoped
logical records, compacts the whole FTS5 index, then runs SQLite freelist/WAL
scrubbing. Cleanup intent commits atomically with logical deletion and remains
until successful cleanup and committed intent removal. The tested process
interruptions leave committed intent available for a confirmed same-ID retry.
Intent removal zeroes its row with core SQLite `secure_delete` and checks a
final checkpoint. A process stop between removal and that checkpoint can leave
ID/time residue without retry state; see the correction record for this limit.
This is not a power-loss or universal crash-recovery guarantee; historical
purges without intent remain limited as described in the correction record below.
This controlled database/WAL cleanup does not erase backups, snapshots,
storage-device remnants, or copies already read by other processes.
Success does not establish physical erasure; see the
[FTS5 purge correction record](publication-preparation.md#open-fts5-purge-follow-up).
Neither operation deletes the operator's original source file. See the
[storage and access caveats](security-boundary-map.md#5-honest-open-items--recommendations).

## Current Tool Surface

The v4.1.0 posture exposes 16 MCP tools. See the root
[README](../README.md#tools-reference) for the current tool vocabulary and
payload summaries.
