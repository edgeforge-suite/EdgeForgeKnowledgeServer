# Compliance & Portability Checklist — Knowledge Server

> **Import-gate G7.** A reviewer's answer-sheet: the questions an import /
> compliance review asks, each **pre-answered and linked to real evidence** — with
> honest caveats where something is pending or nuanced. Claims about code were
> **verified against the source** (the method is stated where it matters), not
> asserted.
>
> **Last updated:** 2026-08-02. This checklist **links** the evidence pack (G3
> secret scan, G4 SBOM/licenses) as the single source of truth; it does not
> re-derive it. The G10 [handover-evidence index](handover-evidence/README.md)
> links this doc.
>
> **Scope clarification (2026-09-26):** Cross-project reuse and the limits of
> dated dependency and secret-scan evidence are stated below. The evidence
> snapshots retain their original dates.

> **Dependency documentation correction (2026-10-03):** current G4 pointers,
> artifact-specific license flags, support guidance and applied enforcement
> link to the dated closure addendum; original evidence dates are unchanged.

> **Publication ownership clarification (2026-10-08):** the import-oriented
> record below does not defer public-source licensing, contribution or reporting
> decisions to a future adopter. See the
> [remaining maintainer decisions](publication-preparation.md#remaining-maintainer-decisions).

## At a glance

| # | Question | Short answer | Evidence |
|---|---|---|---|
| 1 | License posture | Direct declared dependency metadata reports Apache-2.0 / MIT; transitive artifact flags remain. KS uses Apache-2.0 with NOTICE and DCO 1.1; maintainer publication authorization and operational cutover remain pending | [§1](#1-license-posture) |
| 2 | Secrets / real data | CI scans the committed tree for configured secret patterns; synthetic-only content is a contributor policy requiring human review; submitted content is not sanitized | [§2](#2-secrets-and-real-data) |
| 3 | Telemetry / phone-home | The KS server runtime performs no application-initiated network request during startup or MCP tool execution. The FastMCP startup banner and its package-version check are disabled in code. Dependency installation and separately invoked maintenance tooling are outside this guarantee. | [§3](#3-telemetry-and-phone-home) |
| 4 | Standalone / coupling | Self-contained local stdio server; suggestion-only; no hosted-service dependency at runtime | [§4](#4-standalone-and-no-runtime-coupling) |
| 5 | Data-handling posture | Deterministic FTS5/BM25; **no LLM/AI**; ordinary project scoping with explicit cross-project reuse paths; root-constrained ingestion | [§5](#5-data-handling-posture) |
| 6 | Dependency hygiene | Declared in `pyproject.toml` / `requirements.txt`; resolved constraints, SBOM, pip-audit, and license scans committed | [§6](#6-dependency-hygiene) |
| 7 | Portability | Python 3.11+ for v5, SQLite, local stdio; fully air-gappable | [§7](#7-portability) |

---

## 1. License posture

**Third-party dependencies:** all declared dependencies are permissive
(Apache-2.0 / MIT) — no copyleft. Core runtime is `fastmcp` (Apache-2.0) +
`pydantic` (MIT); optional parser extras and test deps are MIT / Apache-2.0.
Inventory + machine-readable SBOM:
[`dependency-licenses.md`](handover-evidence/dependency-licenses.md) ·
[`sbom.cdx.json`](handover-evidence/sbom.cdx.json) ·
[`dependencies.md`](handover-evidence/dependencies.md) (G4).

**KS's own license:** [LICENSE](../LICENSE) is Apache-2.0, with copyright Santosh
Hommaradi and a short [NOTICE](../NOTICE). Package metadata uses the SPDX
expression; contributions use DCO 1.1 sign-off, not a CLA. These are approved
terms, not new choices for an adopter. Maintainer publication authorization
remains pending and blocks public exposure; private preparation is authorized.
See the [operational gates](publication-preparation.md#remaining-maintainer-decisions).

> **Caveat (carried from G4 / P1):** transitive license and vulnerability
> evidence is committed for the current resolved constraints. It is
> time-sensitive and package-index dependent; rerun it against the adopter's
> approved package mirror and review the transitive license flags before import.
> `certifi` MPL-2.0 and `caio` UNKNOWN for affected non-reference artifacts remain
> unresolved; packaged Apache-2.0 COPYING text is not license acceptance. See
> [verified artifact examples](handover-evidence/dependency-closure-2026-10-01.md#artifact-specific-license-correction).

## 2. Secrets and real data

**Secret-pattern scan:** **gitleaks** (pinned `8.30.1`) scans the committed tree
in CI on every PR and push to `main`. The recorded scan found no matches to its
configured patterns in that scope. This does not prove the absence of every
secret or establish the origin of submitted data.

**Synthetic-only contributor policy:** fixtures and examples must be fabricated;
contributors must review them before committing. The dated manual review and
secret scan have bounded scope and do not certify that all content is synthetic
or free of PII. The local SQLite index (`EDGEFORGE_KS_DB_PATH`) and ingested
corpus are not intended for version control (see `.gitignore`).

**Standalone ingestion notice:** submit only synthetic or approved content. KS
does not technically enforce that classification and does not sanitize,
anonymize, or redact submitted documents. It persists extracted metadata,
chunks, and catalog entries in the configured local SQLite store. The original
source file remains operator-owned and is not copied into KS-managed storage;
neither document deletion operation removes that source file.

Evidence: [`secret-and-data-scan.md`](handover-evidence/secret-and-data-scan.md)
and the [`secret-scan` workflow](../.github/workflows/secret-scan.yml) (G3).

## 3. Telemetry and phone-home

**Verified result:** The KS server runtime performs no application-initiated
network request during startup or MCP tool execution. The FastMCP startup banner
and its package-version check are disabled in code. Dependency installation and
separately invoked maintenance tooling are outside this guarantee.

**Verification method:** the supported entrypoint calls
`mcp.run(transport="stdio", show_banner=False)` and disables FastMCP update
checks in [`server.py`](../knowledge_server/server.py). Runtime-hardening tests
exercise stdio startup and hostile transport settings. The KS server runtime
exchanges MCP messages only over its inherited stdio streams and persists data
to the configured local SQLite store. It transmits no ingested content to a
network service. Dependency installation and separately invoked evidence/audit
tools can use the network; they are outside this runtime claim.

## 4. Standalone and no runtime coupling

**KS is a self-contained local stdio MCP server.** At runtime it depends only on
its declared Python libraries and a local SQLite file — **no hosted MCP server, no
SaaS, no network service**. `fastmcp` is a library used to expose KS's *own* local
stdio server, not a call to a hosted MCP.

**Suggestion-only boundary.** KS suggests candidates and returns evidence; **Studio**
owns review/decisions, lifecycle, and manifest/package state; **Engine** consumes
only approved Studio artifacts. KS neither produces nor consumes
`app-definition.yaml` and does not import or call Studio/Engine at runtime — the
coupling is one-way and contract-based (the MCP tool vocabulary).

## 5. Data-handling posture

- **Deterministic, no AI/LLM.** KS performs deterministic SQLite **FTS5 / BM25**
  search and citation. There is **no LLM, no embeddings, and no AI inference** in
  the codebase (verified: no `openai`/`anthropic`/embedding/vector libraries; the
  README lists "no LLM reasoning or generation" as an explicit non-goal). Any
  future optional-AI capability would be gated by the **KS-B5** PII/sanitization
  design — it does **not** exist today.
- **No data egress.** The KS server runtime exchanges MCP messages only over its
  inherited stdio streams and persists data to the configured local SQLite
  store. It transmits no ingested content to any network service.
- **Project scoping and cross-project reuse.** Documents are namespaced per
  `project_id` and ingestion is root-constrained (`EDGEFORGE_KS_ALLOWED_ROOTS`,
  50 MB cap). `search_across_projects` searches all active indexed projects when
  `project_ids` is omitted. Separately,
  `suggest_manifest_candidates(scope="portfolio_reuse")` searches other active
  projects and persists a suggestion under the requesting project; its
  `get_suggestion_evidence_chain(scope="portfolio_reuse")` reads cited chunks
  from the matched source project. A `project_id` scopes ordinary operations;
  it is not tenant authorization. Trust-separated corpora need separate
  database/process boundaries, not reliance on a caller-selected ID or avoidance
  of one tool (see [G8 §3a](security-boundary-map.md#3-attack-surfaces-per-component)
  and [§5](security-boundary-map.md#5-honest-open-items--recommendations)).
- **Retention caveat.** `delete_document` is a **soft delete** that removes the
  document from active retrieval while retaining indexed data for audit.
  `purge_document(confirm_purge=True)` deletes document-scoped logical records,
  compacts the whole FTS5 index, then runs checkpoint/VACUUM/checkpoint storage
  scrubbing. Cleanup intent commits in the same transaction as logical deletion;
  either both commit or neither does. It remains until cleanup succeeds and
  intent removal commits. Committed intent survives the tested process
  interruptions, allowing a confirmed retry with the same project/document IDs.
  Handled maintenance or final intent-update failures report non-success.
  Until a successful retry, the pending row retains the project/document IDs,
  creation/update timestamps and any cleanup warning. Re-ingesting the same
  file keeps that intent; a later confirmed purge of that ID clears it.
  Successful finalization zeroes the removed intent with core SQLite
  `secure_delete` and checks a final WAL checkpoint; it does not enable FTS5
  secure-delete. A handled final-checkpoint failure reports non-success and
  restores intent; if restoration also fails, KS explicitly reports that retry
  state is unavailable or unverified. A process stop after the removal commit
  but before checkpoint/restoration can leave ID/time residue without same-ID
  retry state; the document-content scrub has already completed at that point.
  This is not proof of power-loss, disk-full or universal crash recovery.
  Historical purges without a pending record still return not found for the
  absent document; no retroactive same-ID recovery or startup cleanup is added.
  This cleans the controlled live database/WAL, not
  backups, snapshots, storage-device remnants or copies held by other processes.
  Neither delete operation removes the operator's original source file. See the
  [FTS5 purge correction record](publication-preparation.md#open-fts5-purge-follow-up)
  and [G8 §5.3](security-boundary-map.md#5-honest-open-items--recommendations).
- **At-rest caveat.** The SQLite index stores ingested content in cleartext; rely
  on host filesystem encryption for sensitive corpora ([G8 §5.2](security-boundary-map.md#5-honest-open-items--recommendations)).

## 6. Dependency hygiene

- **Declared surface:** [`pyproject.toml`](../pyproject.toml) declares the core
  runtime (`fastmcp`, `pydantic`), opt-in parser extras, and test deps;
  [`requirements.txt`](../requirements.txt) mirrors those direct declarations.
- **Resolved surface:** [`constraints.txt`](../constraints.txt) is regenerated by
  `make lock` and pins the resolved core + optional parser extras + test
  dependency set used by CI and handover scans. The reference evidence
  environment is CPython 3.11 on Ubuntu 24.04 x86_64; the supported KS runtime
  is Python 3.11+ for v5; SQLite compatibility is unchanged. The [current G4 snapshot](handover-evidence/dependencies.md)
  covers all 84 constrained packages, refreshed for the v5 source-preparation target set;
  its zero-finding audit result applies at
  that scan time, not to current advisory status or every supported platform.
- **Reproducible SBOM + license / audit evidence:** regenerated by named tools via
  `make sbom` / [`scripts/generate-dependency-evidence.sh`](../scripts/generate-dependency-evidence.sh)
  and [`scripts/generate-pip-audit-evidence.sh`](../scripts/generate-pip-audit-evidence.sh)
  (G4 / P1). A separate CI job runs pinned `pip-audit`; findings, incomplete
  coverage, version drift, and scanner failures fail that job. Optional parser
  extras stay opt-in; install only approved formats.
  The gate uses its available PyPI advisory feed, not an exhaustive immediate
  view of repository advisories. The
  [2026-10-03 applied-state note](handover-evidence/dependency-closure-2026-10-01.md#applied-enforcement-state)
  records the audit as a required main check; the pre-change snapshot is retained.

## 7. Portability

- **Runtime:** Python **3.11+** for v5 plus the standard library (SQLite via `sqlite3` is
  stdlib) and a small permissive dependency set (§1). No proprietary SaaS or vendor
  runtime is required.
  The committed constraints target CPython 3.11 / Ubuntu 24.04, not all supported
  platforms. [Earlier Python 3.10 proof](handover-evidence/mcp-correction-2026-10-15.md#python-310-proof)
  remains dated history, not current support. See the [current proof](handover-evidence/v5-source-preparation.md).
- **Air-gapped / restricted networks:** Once dependencies are provisioned from an
  approved offline source, the KS server runtime starts and executes its tools
  without network access.
- **Optional parsers:** the `excel` / `pdf` / `docx` extras add three permissive
  libraries. KS applies parser resource guards for ZIP-based `xlsx`/`docx`
  inputs and PDF page/text extraction, but keep extras disabled unless the
  document type is approved.

---

## Caveats summary (not buried)

- **Maintainer publication authorization and cutover pending** — Apache-2.0,
  NOTICE and DCO 1.1/no CLA are applied. Maintainer publication authorization, selected
  reporting-route operation and public cutover remain project-owned gates (§1).
- **Adopter dependency scan rerun pending** — current P1 evidence is committed;
  rerun `make lock`, `make sbom`, and `scripts/generate-pip-audit-evidence.sh`
  against the approved package mirror and review transitive flags (§1, §6).
- **Soft-delete retains data; purge cleanup has a bounded scope** —
  `purge_document(confirm_purge=True)` deletes document-scoped logical records
  and compacts FTS5 before SQLite storage scrubbing. Atomic cleanup intent enables
  confirmed same-ID retry after the tested process interruptions, not universal
  crash recovery (§5). This is not erasure of source files or external copies.
  Whole-index compaction and VACUUM may be costly; see the
  [correction record](publication-preparation.md#open-fts5-purge-follow-up).
- **At-rest index is cleartext SQLite** — host-level encryption for sensitive
  corpora (§5).
- **Optional document parsers** are an untrusted-content surface — resource
  guards are in place, but ingest only trusted roots and keep extras disabled
  unless approved
  ([G8 §5.1](security-boundary-map.md#5-honest-open-items--recommendations)).
