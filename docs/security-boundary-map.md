# Handoff Security Boundary Map — Knowledge Server

> **Import-gate G8.** The trust-boundary / data-flow / attack-surface view a
> **security architect** reads at import — the architecture companion to the G7
> [Compliance & Portability Checklist](compliance-and-portability.md). It maps
> where the trust boundaries are, what data crosses each, where untrusted input
> enters, where the controls sit, and the honest open items.
>
> **Scope:** a *lightweight* now-doc, **not** a full threat model. Claims below
> record the bounded review against the actual
> source** (the file/symbol is cited), not asserted.
>
> **Last updated:** 2026-08-02. References the evidence pack as the single source
> of truth — G3 (secret/data scan), G4 (SBOM + licenses) — and does not re-derive
> it. The G10 [handover-evidence index](handover-evidence/README.md) links this doc.
>
> **Scope clarification (2026-09-26):** The cross-project reuse paths and the
> dated transitive audit evidence are reflected below; original evidence dates
> remain unchanged.

> **Dependency pointer correction (2026-10-03):** G4 links below now identify
> the current 2026-10-01 snapshot, not the superseded 2026-09-19 snapshot.

> **Dependency refresh (2026-10-15):** the current G4 reports now use MCP
> 1.30.0; see the [correction receipt](handover-evidence/mcp-correction-2026-10-15.md).
> The October 1/3 observations above remain dated history, not current scans.

> **Publication clarification (2026-10-08):** this lightweight map is not a full
> threat model. Public-project security ownership is not deferred to enterprise
> import; [maintainer decisions](publication-preparation.md#remaining-maintainer-decisions)
> now distinguish selected PVR/email routes from their still-pending operation.
> v5 source preparation applies Apache-2.0/DCO 1.1 and Python 3.11; written
> maintainer publication authorization and public exposure remain pending.

## At a glance

| # | Question a reviewer asks | Short answer | Where |
|---|---|---|---|
| 1 | What is the central boundary? | KS is a **local stdio MCP process** — a design-time developer tool. Its boundary is the **local MCP client that launches it** and the **document roots** it is allowed to read. There is **no network listener** and **no production-runtime role**; local host and data risks remain in scope. | [§1](#1-the-central-boundary--a-local-stdio-tool) |
| 2 | Show me the trust boundaries | Diagram: local MCP client ⇄ **stdio** ⇄ KS process → reads **allowed-root** documents → local **SQLite FTS5** index. No KS runtime network egress. | [§2](#2-trust-boundary-diagram) |
| 3 | Where does untrusted input enter? | **Tool-call parameters** over stdio (typed) and **ingested document content** from allowed local roots. No network input. | [§3](#3-attack-surfaces-per-component) |
| 4 | Where are the controls? | Path-allowlist **resolve-then-contain** guard + 50 MB file cap (`safety.py`); **parameterized SQL** + **FTS5 query normalization** (verified); project scoping with explicit cross-project search and portfolio-reuse suggestion/evidence paths; local stdio runtime; **no LLM**. | [§4](#4-controls--boundaries) |
| 5 | What's still open? | Document-parser attack surface (optional PDF/XLSX/DOCX libs); at-rest index is cleartext SQLite; soft-delete retains indexed data and purge cleanup is limited to the controlled live database/WAL; full threat model deferred. The transitive audit is a dated snapshot, not current clearance. | [§5](#5-honest-open-items--recommendations) |

---

## 1. The central boundary — a local stdio tool

KS is a **design-time developer tool**, not a runtime service. It runs as a
**local stdio MCP server** that a local MCP client (Studio, or a developer's MCP
client) launches as a child process.

Two facts shape its entire threat model:

- **No network surface.** The KS application entrypoint pins stdio in code and
  binds no listening socket. FastMCP transport, host, and port settings supplied
  through the process environment or a working-directory `.env` are not
  honoured.
- **No production role.** KS suggests candidates and returns evidence with
  citations; **Studio** owns review/decisions and **Engine** consumes only
  approved Studio artifacts. The supported KS entrypoint does not use network
  transport or run in the production data path. A defect in KS is a
  **developer/build-host** concern, not a production-runtime one.

## 2. Trust-boundary diagram

```
  LOCAL DEVELOPER / BUILD HOST  (no production traffic)
  ─────────────────────────────────────────────────────────────────────
   MCP client (Studio / dev)
        │  stdio (no network)         ┌─────────────────────────────┐
        ▼  trust boundary: the local  │  Knowledge Server (KS)       │
        │  process that launched KS   │  fastmcp over stdio          │
        │  + typed tool parameters    │  deterministic, no LLM       │
        └────────────────────────────►│                              │
                                       │  reads ──► allowed-root docs │
   local documents  ──ingest─────────►│   (resolve-then-contain      │
        ▲  trust boundary: document     │    guard + 50 MB cap)       │
        │  CONTENT (operator-supplied)  │                             │
        │  parsed by md/csv/sql +       │  index ──► SQLite FTS5/BM25 │
        │  optional pdf/xlsx/docx libs  │   (local file; parameterized│
                                       │    SQL + FTS normalization)  │
                                       └─────────────┬───────────────┘
                                  text + citations   │  (no runtime network egress)
        ◄──────────────────────────────────────────┘
```

Read it as: **untrusted input enters at exactly two places** — typed tool-call
parameters over stdio, and the *content* of documents the operator ingests — and
KS returns text and citations to the local client over stdio and writes a local
SQLite index. The supported server runtime sends no ingested content to a
network service; separately invoked installation/audit tools can use the network.
KS generates no code, mutates no manifest, and neither produces nor consumes
`app-definition.yaml`.

## 3. Attack surfaces, per component

### 3a. MCP stdio interface

The 16 tools in [`server.py`](../knowledge_server/server.py) accept typed
parameters (validated by the `fastmcp` tool signatures; `submit_suggestion_decisions`
additionally validates each item via `SuggestionDecision.model_validate`). The
caller is the **local process** that launched KS over stdio — there is no network
listener and no authentication step because there is no remote surface to
authenticate (the OS process boundary is the control). **Most data tools use
`project_id` for ordinary scoping.** Two intentional cross-project paths matter:
`search_across_projects` searches **all** active indexed projects when optional
`project_ids` is omitted; `suggest_manifest_candidates(scope="portfolio_reuse")`
searches other active projects and stores the review suggestion under the
requesting project. Its `get_suggestion_evidence_chain(scope="portfolio_reuse")`
retrieves cited chunks from the matched source project (`database.py`). These
paths are available through the same stdio MCP surface. A caller-supplied
`project_id` is not tenant authorization; trust-separated corpora require
appropriate separate database/process boundaries (see [§5](#5-honest-open-items--recommendations)).

### 3b. Document ingestion — the primary untrusted-input surface

`ingest_document` reads a **local file** and parses it. This is where
operator-supplied (potentially untrusted) *content* enters. Controls, **verified**
in [`knowledge_server/safety.py`](../knowledge_server/safety.py):

- **Path-traversal guard (resolve-then-contain).** `resolve_allowed_path()`
  resolves the candidate path (`expanduser().resolve()`, which normalizes `..` and
  follows symlinks) **and then** requires it to be under one of the roots in
  `EDGEFORGE_KS_ALLOWED_ROOTS` (`candidate.relative_to(root)`), raising otherwise.
  A `../`-style escape is normalized first and then rejected.
- **File-size cap.** `enforce_file_size()` rejects files over **50 MB**
  (`DEFAULT_MAX_FILE_BYTES`), bounding the simplest ingest resource-exhaustion.
- **Parser resource guards.** Optional `xlsx`/`docx` ZIP-based parsers enforce
  entry-count, total uncompressed-size, per-entry uncompressed-size, and
  suspicious-path checks before parser libraries open the archive. Optional PDF
  parsing enforces page-count and extracted-text caps.
- **Root restriction.** Ingestion is limited to the operator-declared
  `EDGEFORGE_KS_ALLOWED_ROOTS`. Solo/local mode defaults to the working directory;
  shared mode requires an explicit non-empty value and fails closed otherwise.

The parsers live in [`knowledge_server/parsers/`](../knowledge_server/parsers/):
`markdown`, `csv`, and `sql` are plain-text; the **optional** `excel` / `pdf` /
`docx` parsers (opt-in extras) handle complex formats and now have practical
resource guards — see the remaining caveat in
[§5](#5-honest-open-items--recommendations).

### 3c. SQLite storage + FTS query

Storage is a local **SQLite FTS5** database
([`storage/database.py`](../knowledge_server/storage/database.py)).

- **SQL injection — mitigated (verified).** Data queries use bound parameters
  (`?` placeholders, e.g. `... WHERE document_id = ?`, `(document_id,)`). Where an
  f-string appears in a query, it interpolates only **internal constants or fixed
  clause structure**, never a user value: `_table_row_count` is called with
  literal table names (`"field_suggestions"`, `"manifest_suggestions"`), and
  `list_documents` f-strings the clause **shape** (`"project_id = ?"`, `"doc_type
  = ?"`) while the values flow through the parameter list.
- **FTS5 query injection — mitigated (verified).** User query text is passed
  through `_normalize_fts_query()`, which extracts `\w+` tokens, **quotes each**,
  and OR-joins them — stripping every FTS5 operator/punctuation char — and the
  search then binds it via `... MATCH ?`. Arbitrary user text cannot inject FTS5
  syntax or raise an operational error.
- **At rest.** The index is a local SQLite file (path from `EDGEFORGE_KS_DB_PATH`,
  `*.sqlite3`/`*.db` are git-ignored) holding ingested document content in
  cleartext — at-rest protection is the host's responsibility (see
  [§5](#5-honest-open-items--recommendations)).

### 3d. Output

Tools return **JSON-compatible structured result models** (`model_dump()` of
pydantic results): text/citations, document metadata and lists, field catalogs,
manifest suggestions, conflict and portfolio-reuse results, and decision-status
metadata. KS returns document-derived text rather than executing it as code or
mutating a manifest. Returned text remains untrusted content; a client must
handle rendering or later use safely. Local stdio and deterministic output do
not establish that arbitrary downstream rendering is injection-safe.

## 4. Controls + boundaries

| Control | Where (verified) |
|---|---|
| **Path-allowlist, resolve-then-contain** | `safety.py` `resolve_allowed_path()` + `allowed_roots_from_env()` |
| **Ingest file-size cap (50 MB)** | `safety.py` `enforce_file_size()` |
| **Optional parser resource guards** | `safety.py` `enforce_zip_resource_limits()` + PDF page/text caps in `pdf_parser.py` |
| **Parameterized SQL** | `storage/database.py` — bound `?` params throughout |
| **FTS5 query normalization** | `storage/database.py` `_normalize_fts_query()` + `MATCH ?` |
| **Project scoping (most data tools)** | `project_id` scopes ordinary tools, while `search_across_projects` and generic portfolio-reuse suggestion/evidence paths access other indexed projects. It is not tenant authorization (see §5 item 8). |
| **No network / no auth surface** | `mcp.run(transport="stdio", show_banner=False)`; FastMCP startup update checks disabled; no listening socket (G7 §3) |
| **No LLM / no runtime network content egress** | deterministic FTS5/BM25; supported stdio entrypoint and runtime tests (G7 §3/§5) |
| **Secret-pattern checks on committed tree** | gitleaks CI on every PR/push; scope and limits in G3 |
| **Soft-delete audit trail + logical purge and scrub** | `delete_document` removes a document from active retrieval while retaining indexed data; `purge_document(confirm_purge=True)` deletes document-scoped logical records, compacts FTS5, then scrubs SQLite freelist/WAL storage. Cleanup intent commits atomically with deletion and supports confirmed retry after tested process interruptions; recovery limits remain (§5.3). |

## 5. Honest open items / recommendations

This map records the remaining controls and caveats; implementation fixes
belong in separate changes.

| # | Item | Surface | Posture / recommendation |
|---|---|---|---|
| 1 | **Document-parser attack surface** (hostile input — *not* a functionality issue) | Optional `pdf`/`xlsx`/`docx` parsers | **This concerns handling of deliberately hostile/malformed files, not normal operation** — the parsers are unit-tested and pass in CI (`tests/test_parsers/`). KS now enforces ZIP entry/uncompressed-size/path guards for `xlsx`/`docx` and PDF page/text caps, which narrows decompression-bomb and parser-output risk. A malicious file could still trip a parser-library vulnerability. **Recommendation:** ingest only from **trusted/approved roots**; keep optional parser extras **disabled** unless the format is approved; consider process sandboxing for highly untrusted corpora. |
| 2 | **At-rest index is cleartext** | SQLite index file | Ingested content is stored unencrypted in the configured local SQLite file. For sensitive corpora, rely on **host filesystem encryption**. The DB path is operator-controlled; the repository ignores `*.sqlite3` and `*.db`, not database files with other names such as `custom.sqlite`. Keep the index outside the repository and review staged files before committing. |
| 3 | **Soft-delete retains data; purge cleanup has a bounded scope** | `delete_document`, `purge_document` | Soft-delete removes the document from active retrieval while preserving indexed data for audit. `purge_document(confirm_purge=True)` deletes document-scoped logical records, compacts the whole FTS5 index, then runs checkpoint/VACUUM/checkpoint scrubbing. Cleanup intent commits in the same transaction as logical deletion; either both commit or neither does. Intent remains until successful cleanup and committed removal. The tested process interruptions preserve committed intent for a confirmed same-project/same-document retry; handled maintenance or final state-update errors report non-success. Until successful retry, a pending row retains project/document IDs, creation/update timestamps and any cleanup warning. Re-ingesting the same file keeps that intent until a later confirmed purge of the ID. This is not a power-loss, disk-full or universal crash-recovery guarantee. Historical purges without intent remain not found on same-ID retry; no startup or retroactive recovery is added. This cleans the controlled live database/WAL, not backups, snapshots, storage-device remnants or copies held by other processes. Neither operation deletes the operator's original source file. Whole-index compaction and VACUUM can be expensive; see the [FTS5 purge correction record](publication-preparation.md#open-fts5-purge-follow-up). |
| 4 | **No authentication on the interface** | stdio MCP | **By design** — local stdio, the OS process boundary is the control. If KS were ever exposed beyond local stdio (no network transport exists today), authentication would be required first. |
| 5 | **Optional AI (future)** | — | **None today** — KS has no LLM/AI in the codebase (verified). If an optional-AI capability is ever added, it is gated by the **KS-B5** PII/sanitization design (roadmap), not enabled here. |
| 6 | **Dated transitive dependency evidence** | Supply chain | The [current G4 snapshot](handover-evidence/dependencies.md) covers all 84 constrained packages; `pip-audit` reported no findings at scan time. It is not present-day vulnerability clearance or complete repository-advisory coverage. The [applied audit requirement](handover-evidence/dependency-closure-2026-10-01.md#applied-enforcement-state) does not clear bootstrap/tool exclusions or license flags. Rerun against the approved package source when required; review transitive license flags (G7 §1). |
| 7 | **Full threat model** | All | This lightweight map does not complete a full threat model. The older import plan deferred deeper assessment to an in-house pipeline; public-project security maturity remains project-owned, alongside adopter-specific deployment assessment. No new full-model deliverable is included in this preparation slice. |
| 8 | **Cross-project reuse (intentional surface)** | `search_across_projects`; generic `portfolio_reuse` suggestions and evidence | Direct search can read all active indexed projects when `project_ids` is omitted. Generic portfolio reuse searches other active projects, persists the suggestion under the requesting project, and retrieves evidence from the matched source project (§3a). `project_id` and avoiding the direct search tool do not enforce tenant isolation; use separate database/process boundaries for trust-separated corpora. |

For §5.3, successful intent removal uses core SQLite `secure_delete` and a
checked final WAL checkpoint (not FTS5 secure-delete). Handled final-checkpoint
failure reports non-success and restores intent; failed restoration explicitly
disclaims verified retry state. A process stop after removal commits but before
checkpoint/restoration can leave ID/time residue without same-ID retry state.
Document-content cleanup has already succeeded at that stage. See the
[pending-record privacy correction](publication-preparation.md#pending-record-privacy-correction--2026-10-11).

---

## Caveats summary (not buried)

- **Optional document parsers** (pdf/xlsx/docx) are a **hostile-input** surface
  (not a functionality issue — the parsers are unit-tested and resource-guarded)
  — ingest only trusted roots; keep extras disabled unless approved (§5.1).
- **Cross-project reuse is intentional** — direct search can read all active
  projects; generic portfolio suggestions and evidence can refer to other
  projects even when direct search is not called (§3a, §5.8).
- **At-rest index is cleartext SQLite** — host-level encryption for sensitive
  corpora (§5.2).
- **Soft-delete retains data; purge cleanup has a bounded scope** —
  `purge_document(confirm_purge=True)` deletes document-scoped logical records
  and compacts FTS5 before SQLite storage scrubbing. Atomic cleanup intent enables
  confirmed same-ID retry after the tested process interruptions, not universal
  crash recovery. Success is not an erasure guarantee for external copies (§5.3).
  Neither operation deletes the original source file. See the
  [correction record](publication-preparation.md#open-fts5-purge-follow-up).
- **No auth on the stdio interface** — by design (local process boundary); no
  network transport exists (§5.4).
- **No AI today**; any future optional AI is KS-B5-gated (§5.5).
- **Transitive audit is dated evidence** — 84 constrained packages covered in
  the [current v5 G4 snapshot](handover-evidence/dependencies.md);
  current advisory status is not established (§5.6).
- **No full threat model yet** — project maturity and adopter-specific assessment
  remain distinct responsibilities (§5.7).

## See also

- [Compliance & Portability Checklist](compliance-and-portability.md) (G7) — the
  compliance companion to this architecture map.
- [Handover-evidence index](handover-evidence/README.md) (G10) — concern → evidence.
- [SBOM + license inventory](handover-evidence/dependencies.md) (G4);
  [`secret-and-data-scan.md`](handover-evidence/secret-and-data-scan.md) (G3).
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — the authoritative invariants
  (deterministic, suggestion-only, local-stdio, no-LLM).
