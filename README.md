# EdgeForge Knowledge Server

EdgeForge Knowledge Server is a separate local stdio MCP server for project-scoped document ingestion, retrieval, evidence lookup, and deterministic manifest suggestion guidance.

It is intentionally:

- deterministic
- local stdio only
- project-scoped, with explicit cross-project reuse
- evidence-first

It is intentionally not:

- an Engine MCP extension
- a Studio UI implementation
- a manifest writer
- an LLM reasoning or generation service
- a network/SSE or auth-enabled service

## Status — v5 Source and Technical Acceptance

**All 16 current MCP tools are implemented and tested.**
Wire protocol is verified via real stdio subprocess round-trips.

Current 16-tool vocabulary:

1. `ingest_document`
2. `list_documents`
3. `search_documents`
4. `read_document`
5. `read_field_catalog`
6. `get_evidence`
7. `find_conflicts`
8. `delete_document`
9. `purge_document`
10. `search_across_projects`
11. `suggest_manifest_candidates`
12. `get_suggestion_evidence_chain`
13. `suggest_fields`
14. `compare_field_definitions`
15. `get_field_evidence_chain`
16. `submit_suggestion_decisions`

The KS package and runtime version is `5.0.0`. It includes deterministic
identity-role suggestion support for Studio Step 3 review. The earlier `v4.1.0`
handover-consistency posture and
`v4.0.0` suite-alignment milestone remain historical baselines. The selected
Engine/Studio/KS sources and completed technical acceptance are recorded in the
[Suite acceptance results](https://github.com/edgeforge-suite/EdgeForge/blob/92d0de224d127525b3b3db1365cf931188ccfffb/docs/handover-evidence/v5-acceptance-2026-11-10.md).
Tags and public Releases require separate maintainer authorization; a package
version alone does not establish publication.

Important nuance:

- backend bug-fix and hardening work may continue in parallel
- the KS backend baseline plus additive decision write-back contract are in place
- `suggest_manifest_candidates` and `get_suggestion_evidence_chain` are the current generic suggestion and evidence-chain surfaces
- `suggest_fields` and `get_field_evidence_chain` remain backward-compatible field-scope aliases
- deterministic suggestion scopes now cover fields, validations, rules, cross-entity rules, mappings, Kafka router transforms, conflict resolution, portfolio reuse, and identity-role review when explicit catalog/evidence exists
- Oracle-style DDL ingest and evidence-summary cleanup are merged
- optional AI/provider assistance remains future work and off by default

KS remains suggestion-only:

- KS suggests candidates and provides evidence
- Studio owns human review, decisions, generated-artifact state, manifest/package state, and apply workflows
- Engine consumes only approved Studio manifest/package artifacts

## What KS Does And Does Not Do

KS supplies deterministic local stdio retrieval, citations and reviewable
suggestions. It neither produces nor consumes `app-definition.yaml`, generates
applications, nor applies suggestions to a manifest. Studio's optional Knowledge
Assist feature can call KS; Studio owns human review and artifact changes.
Optional Excel/PDF/DOCX parser extras remain opt-in. There is no AI/provider
integration in the supported runtime.

Project IDs scope ordinary retrieval; they are not tenant authorization.
`search_across_projects` and generic `portfolio_reuse` suggestions and persisted
evidence can reference other projects in the same store. Trust-separated corpora
require appropriate database/process boundaries. See the
[security boundary map](docs/security-boundary-map.md#3a-mcp-stdio-interface).

This is the `edgeforge-suite/EdgeForgeKnowledgeServer` repository.
Apache-2.0, copyright Santosh Hommaradi and DCO 1.1 (no CLA) are
applied in [LICENSE](LICENSE), [NOTICE](NOTICE) and [CONTRIBUTING](CONTRIBUTING.md).
Public exposure requires maintainer authorization. The
[publication requirements](docs/publication-preparation.md) distinguish email
checks before exposure from PVR checks at public cutover. Technical acceptance
does not authorize tags, Releases or public launch.

References to pre-v5 commits, pull requests, issues and workflow runs point to the private development archive and may be inaccessible to public readers.

## Project intent and community

EdgeForge is an independently maintained open-source project, shared freely under
[Apache-2.0](LICENSE). Contributions and feedback are welcome. Individuals and
enterprises may use, modify and redistribute it, including commercially, under
those terms. The maintainer does not seek sponsorship or offer paid services,
consulting, custom implementation or managed deployments through this project.
No response deadlines, fixes, delivery dates or ongoing operational support are
promised. Community contributions that improve correctness, stability and
usability are especially welcome. Enterprise adoption is welcome under the
same license; it does not establish affiliation, endorsement or maintainer
service commitments.

Start with the [documentation](docs/README.md). Use
[project issues](https://github.com/edgeforge-suite/EdgeForgeKnowledgeServer/issues)
for ordinary questions, bugs and suggestions when you have repository access.
See [CONTRIBUTING](CONTRIBUTING.md)
for contributions and [SECURITY](SECURITY.md) for private vulnerability reporting.
Share only synthetic examples and redacted diagnostics.

Initial v5 distribution is source repositories and tags, not official packages,
images or hosted services. KS runs locally under the adopter's control.

## Baseline Tags

Historical v4.1.0 guidance, retained for that posture (not instructions to select
or create the proposed v5 release):

As checked on 2026-10-08, `v4.1.0` was not created as a KS tag: the remote lists
only `v1.0.0` and `v4.0.0`, with no releases. Tag/package reconciliation remains
in the [release metadata decision](docs/publication-preparation.md#remaining-maintainer-decisions).

```bash
git tag -a v4.1.0 -m "EdgeForge Knowledge Server v4.1.0 - handover consistency baseline"
git push origin v4.1.0
```

`v4.0.0` marks the KS standalone baseline aligned with the EdgeForge suite
`v4.0.0` enterprise-readiness handoff baseline, after deterministic broader
suggestion scopes, stable suggestion identity, persisted review status, Oracle
DDL ingest hardening, parser resource guards, hard purge, and
`submit_suggestion_decisions` write-back are all present on `main`.

`v4.1.0` is the follow-on consistency baseline for handover polish: packaging
metadata, docs navigation, portable setup messaging, lint configuration, and
suite-aligned developer ergonomics.

## Implemented Suggestion Scopes

As of the v4.1.0 suite posture, KS deterministic suggestions cover:

| Scope | Status |
|---|---|
| `fields` | Original field guidance baseline and generic `suggest_manifest_candidates` path |
| `validations` | Validation hints for Studio Step 3 / Step 6 materialization |
| `rules` | Business rule candidates |
| `cross_entity_rules` | Cross-entity rule candidates |
| `mappings` | Mapping suggestions where catalog/evidence supports source/target matching |
| `transforms` | Kafka router transform suggestions via KS PR #21 |
| `conflict_resolution` | Advisory conflict suggestions with field-level deltas via KS PR #23 |
| `portfolio_reuse` | Cross-project advisory reuse suggestions |
| `identity_role` | Entity field identity-role suggestions for Studio Step 3 review |

`conflict_resolution` and `portfolio_reuse` are advisory review artifacts in
Studio. They are not generated-manifest evidence links and KS does not mutate
manifest state for them.

## Boundaries And Follow-On Work

KS remains a separate MCP server. Studio owns:

- subprocess lifecycle
- degraded-mode behavior
- in-session review state
- persisted human decisions and generated-artifact state
- manifest/package mutation and export workflows

KS owns:

- evidence retrieval and citations
- project-scoped document intelligence
- deterministic suggestion generation

Current follow-on work remains outside this KS baseline:

- optional AI/provider assistance
- LegacyExtractor integration and UX v3 refresh
- Graph/GraphRAG or vector-search augmentation
- deeper Knowledge Assist persistence/reopen hardening where needed
- Evidence Trail handling for identity decisions if a future Evidence Trail v1.2 requires it
- generated app behavior changes

## Documentation Navigation

Start with the local docs index for onboarding and operational evidence:

- [docs/README.md](docs/README.md) — documentation map
- [docs/architecture-overview.md](docs/architecture-overview.md) — short KS architecture and data-flow overview
- [docs/module-guide.md](docs/module-guide.md) — package/module guide for contributors
- [docs/handover-evidence/README.md](docs/handover-evidence/README.md) — enterprise handover evidence index
- [docs/publication-preparation.md](docs/publication-preparation.md) — contributor preparation and remaining publication decisions

## Supported Doc Types

- `markdown`
- `csv`
- `sql`
- `excel`
- `pdf`
- `docx`

## Tools Reference

### Tier 1 — Ingestion & Retrieval

`ingest_document`
- Description: ingest one local document into a project namespace.
- Key parameters: `project_id: str`, `file_path: str`, `doc_type: str`, `tags: list[str] | None`, `description: str | None`
- Returns: `IngestResult`

> **Standalone ingestion data handling:** Submit only synthetic or approved
> content. KS does not sanitize, anonymize, or redact sensitive information in
> submitted documents. Extracted metadata, chunks, and catalog entries are
> persisted in the configured local SQLite store. The original source file
> remains operator-owned; KS does not copy it into managed storage or delete it.

`list_documents`
- Description: list project documents, optionally filtered by document type or tags.
- Key parameters: `project_id: str`, `doc_type: str | None`, `tags: list[str] | None`
- Returns: `DocumentList`

`search_documents`
- Description: run deterministic SQLite FTS5/BM25 search across one project.
- Key parameters: `project_id: str`, `query: str`, `doc_types: list[str] | None`, `max_results: int`, `min_score: float | None`
- Returns: `SearchResults`

`read_document`
- Description: read the full extracted text for a document or one named section/page.
- Key parameters: `project_id: str`, `document_id: str`, `section: str | None`
- Returns: `DocumentContent`

`read_field_catalog`
- Description: return structured fields extracted from CSV, SQL, or Excel dictionaries.
- Key parameters: `project_id: str`, `source: str | None`, `entity: str | None`
- Returns: `FieldCatalog`

### Tier 2 — Evidence & Management

`get_evidence`
- Description: return ranked full evidence chunks with citations for a natural-language query.
- Key parameters: `project_id: str`, `query: str`, `doc_types: list[str] | None`, `max_chunks: int`, `min_score: float | None`
- Returns: `EvidenceResult`

`find_conflicts`
- Description: surface potentially conflicting chunks from different documents for the same query topic.
- Key parameters: `project_id: str`, `query: str`, `doc_types: list[str] | None`, `max_chunks_to_search: int`, `min_score: float | None`
- Returns: `ConflictResult`

`delete_document`
- Description: soft-delete a project document while retaining chunk data for audit trail.
- Key parameters: `project_id: str`, `document_id: str`
- Returns: `DeleteResult`

`purge_document`
- Description: after explicit confirmation, delete document-scoped logical records, compact the whole FTS5 index, then checkpoint/VACUUM/checkpoint SQLite storage. Cleanup intent commits atomically with logical deletion and remains until cleanup succeeds and intent removal commits. Committed intent survives the tested process interruptions for a confirmed same-ID retry; this is not a power-loss or universal crash-recovery guarantee. Intent removal uses core SQLite zeroing and a checked final checkpoint; a process stop between removal and that checkpoint can leave ID/time residue without retry state. Historical purges without pending intent do not gain retroactive same-ID recovery. This cleans deleted index entries and reclaimed pages in the controlled live database/WAL, not source files, backups, snapshots, storage-device remnants, or copies already read by other processes. Whole-index compaction and VACUUM can be expensive. See the [FTS5 purge correction record](docs/publication-preparation.md#open-fts5-purge-follow-up).
- Key parameters: `project_id: str`, `document_id: str`, `confirm_purge: bool`
- Returns: `PurgeResult`

`search_across_projects`
- Description: search for similar content across all indexed projects for portfolio reuse.
- Key parameters: `query: str`, `project_ids: list[str] | None`, `doc_types: list[str] | None`, `max_results_per_project: int`, `min_score: float | None`
- Returns: `CrossProjectSearchResults`

### Tier 3 — Manifest Suggestion Guidance

`suggest_manifest_candidates`
- Description: generic suggestion entry point for manifest candidates. Current deterministic scopes are `fields`, `validations`, `rules`, `cross_entity_rules`, `mappings`, `transforms`, `conflict_resolution`, `portfolio_reuse`, and `identity_role`.
- Key parameters: `project_id: str`, `scope: str`, `entity: str | None`, `route_name: str | None`, `source_entity: str | None`, `target_entity: str | None`, `target_id: str | None`, `direction: str | None`, `field_name_pattern: str | None`, `min_source_count: int`, `max_suggestions: int`
- Returns: `SuggestManifestCandidatesResult`

`get_suggestion_evidence_chain`
- Description: generic evidence-chain entry point for persisted field, validation, rule, cross-entity-rule, mapping, transform, conflict-resolution, portfolio-reuse, and identity-role suggestions.
- Key parameters: `project_id: str`, `suggestion_id: str`, `scope: str`, `max_chunks: int`
- Returns: `SuggestionEvidenceChain`

`suggest_fields`
- Description: backward-compatible alias for field suggestions for existing field-scope clients; current generic callers use `suggest_manifest_candidates(scope="fields")`.
- Key parameters: `project_id: str`, `entity: str | None`, `field_name_pattern: str | None`, `min_source_count: int`, `max_suggestions: int`
- Returns: `SuggestFieldsResult`

`compare_field_definitions`
- Description: compare how one field is defined across project documents in chronological order.
- Key parameters: `project_id: str`, `field_name: str`, `entity: str | None`
- Returns: `FieldComparisonResult`

`get_field_evidence_chain`
- Description: backward-compatible alias for field evidence for existing field-scope clients; current generic callers use `get_suggestion_evidence_chain(scope="fields")`.
- Key parameters: `project_id: str`, `field_name: str`, `entity: str | None`, `max_chunks: int`
- Returns: `FieldEvidenceChain`

`submit_suggestion_decisions`
- Description: persist batched Studio accept / edit / reject decisions for manifest suggestions.
- Key parameters: `project_id: str`, `decisions: list[{suggestion_id, status, edited_payload?}]`
- Returns: `SubmitSuggestionDecisionsResult`

Current implementation notes:

- `suggest_fields` now returns stable `suggestion_id` values and persisted `status`
- `suggest_manifest_candidates(scope="fields")` preserves the same field-suggestion persistence and decision behavior
- `suggest_manifest_candidates` also persists deterministic validation, rule, cross-entity-rule, mapping, transform, conflict-resolution, portfolio-reuse, and identity-role suggestions when source evidence is explicit
- unsupported broader scopes return clear warnings and do not persist fake suggestions
- write-back validates edited payloads for field, validation, rule, cross-entity-rule, mapping, transform, conflict-resolution, portfolio-reuse, and identity-role suggestions
- `status` is constrained to `accepted`, `edited`, or `rejected`
- unknown future suggestion types remain forward-compatible with warning-only edited-payload handling

## Requirements

Python **3.11 or later** is required for v5. On macOS the system `python3` may still be 3.9, so use `python3.11`, Homebrew Python, or pyenv.

## Installation

```bash
# minimal install
pip install -e .

# with Excel support
pip install -e ".[excel]"

# with PDF support
pip install -e ".[pdf]"

# with DOCX support
pip install -e ".[docx]"

# everything, including tests
pip install -e ".[all,test]"
```

The direct FastMCP dependency is pinned to the supported runtime version, so
every install command above receives the transport and error-boundary version
verified by this repository. For the reproducible **CPython 3.11 / Ubuntu 24.04
x86_64 reference install** of the complete resolved dependency set, apply the
committed constraints file:

```bash
pip install --constraint constraints.txt -e ".[all,test]"
```

CI, vulnerability auditing, SBOM generation, and transitive license evidence
all use this exact resolved graph. The reference evidence environment is CPython
3.11 on Ubuntu 24.04 x86_64; this does not narrow the supported KS runtime range
of Python 3.11 or later.

The [current dependency correction](docs/handover-evidence/joserfc-correction-2026-11-02.md)
records the selected dependency set and dated audit; the earlier
[source-preparation proof](docs/handover-evidence/v5-source-preparation.md) is retained.
Apply the selected constraints
to any installation command above when reproducing the reference graph; an
unconstrained install is not the same audited graph. KS remains stdio-only.

**Python support change:** v5 requires Python 3.11 to preserve PDF support with
Pillow 13. The approved revision 2 amendment does not change the SQLite support
floor or replace the parser. The [October 15 Python 3.10 proof](docs/handover-evidence/mcp-correction-2026-10-15.md#python-310-proof)
is preserved as dated historical evidence, not continued v5 support. No new
3.10 run is claimed. Parser extras remain opt-in.

## Enterprise Dependency Posture

KS uses `fastmcp` as a Python runtime library to expose this repo's own local stdio MCP server. It does not call or depend on public hosted MCP servers at runtime.

Optional parser dependencies are document-format capabilities, not MCP servers:

- `openpyxl` enables Excel ingestion
- `pdfplumber` enables PDF ingestion
- `python-docx` enables DOCX ingestion

For enterprise deployment, install approved dependencies from an internal artifact registry or wheelhouse, keep optional parser extras disabled unless the document type is approved, and keep `EDGEFORGE_KS_ALLOWED_ROOTS` limited to reviewed local document roots. The constraints file is the reference-platform full-environment lock, not a universal platform lock; the direct FastMCP pin remains enforced even when constraints are not supplied.

## Local Setup

```bash
python3.11 -m venv .venv
.venv/bin/pip install --constraint constraints.txt -e ".[all,test]"
.venv/bin/python -m pytest -q
```

### L5 Isolation Acceptance Helper

The suite-level L5 orchestrator can call the KS isolation helper directly:

```bash
python3.11 scripts/run_ks_l5_isolation.py --pretty
```

The helper creates ephemeral per-session SQLite databases and synthetic documents,
then verifies per-session DB isolation, project-scoped search isolation, explicit
`search_across_projects(project_ids=...)` filtering, shared-mode fail-closed DB
path requirements, allowed-root rejection, and absence of absolute local paths in
search/evidence result payloads.

## MCP Server Launch

```bash
EDGEFORGE_KS_ALLOWED_ROOTS=/path/to/docs \
EDGEFORGE_KS_DB_PATH=/tmp/edgeforge-ks.sqlite3 \
python3.11 -m knowledge_server.server
```

Environment variables:

- `EDGEFORGE_KS_ALLOWED_ROOTS`: OS path-list of ingestable roots; defaults to the
  working directory only in solo/local mode
- `EDGEFORGE_KS_DB_PATH`: SQLite database path; defaults to
  `./edgeforge_knowledge.sqlite3` only in solo/local mode
- `EDGEFORGE_SHARED_MODE`: when enabled, requires explicit non-empty
  `EDGEFORGE_KS_ALLOWED_ROOTS` and `EDGEFORGE_KS_DB_PATH` values

## MCP Client Config

Example local stdio MCP client entry:

```json
{
  "mcpServers": {
    "edgeforge-knowledge-server": {
      "command": "/path/to/python3.11",
      "args": ["-m", "knowledge_server.server"],
      "cwd": "/absolute/path/to/EdgeForgeKnowledgeServer",
      "env": {
        "EDGEFORGE_KS_ALLOWED_ROOTS": "/absolute/path/to/project-docs:/absolute/path/to/shared-docs",
        "EDGEFORGE_KS_DB_PATH": "/tmp/edgeforge-knowledge-server.sqlite3"
      }
    }
  }
}
```

Use a real interpreter path for your environment. Common choices are
`.venv/bin/python` on macOS/Linux, `.venv\\Scripts\\python.exe` on Windows, or an
approved enterprise Python path. `EDGEFORGE_KS_ALLOWED_ROOTS` uses the host OS
path-list separator (`:` on POSIX, `;` on Windows).

## Cross-Repo References

These suite source-of-truth docs live in the sibling
`edgeforge-suite/EdgeForge` repository:

- `EdgeForge/docs/EdgeForge Target State Features v1.md`
- `EdgeForge/docs/studio-ks-orchestration-design.md`
- `EdgeForge/docs/studio-ux-v3-suggestion-drawer-pattern.md`
- `EdgeForge/docs/ks-broader-suggestion-scopes-design.md`
- `EdgeForge/docs/evidence-trail-design.md`
- `EdgeForge/docs/project-workspace-decision-ledger-design.md`

## Explicit Non-Goals (for now)

- no Studio UI changes
- no Engine MCP tools
- no LegacyExtractor tools
- no replacement of FTS5/BM25 with vector search or embeddings as the primary search path
- no network/SSE transport
- no auth
- no multi-user auth or shared workspace hosting
- no LLM reasoning or generation
- no generated code
- no web fetching
- no automatic manifest mutation
- no SharePoint native connector
- no COBOL structural parsing inside KS
- no broader legacy source parsing inside KS
  - those belong in LegacyExtractor MCP, not KS
