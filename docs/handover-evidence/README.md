# Knowledge Server Evidence — Maintainers, Contributors, Users And Adopters

> **Evidence front door, including import-gate G10.** This index connects each
> concern to a dated record and its limits. Read the linked artifact for its
> actual source revision, environment, tool and observation; a summary here is
> not a new scan or acceptance result.
>
> **Ownership:** public-project decisions are owned by project maintainers;
> enterprise import and deployment choices remain adopter responsibilities.
> The [publication decision table](../publication-preparation.md#remaining-maintainer-decisions)
> separates them. The historical import-oriented open-list heading is retained
> [below](#open--adopter-decides--post-import-nothing-hidden) for existing links.
>
> **Source-preparation pointers updated:** 2026-10-25. KS is part of a multi-repo suite; this pack covers
> the **Knowledge Server** repository. What KS is, its 16-tool vocabulary, and its
> boundaries: [`README.md`](../../README.md).
>
> **Scope clarification:** The index distinguishes current KS boundaries from
> dated evidence. G4 was refreshed for the v5 target set; G3 and the historical boundary
> observations retain their original dates.

> **Documentation correction:** 2026-10-03; see the
> [dated closure addendum](dependency-closure-2026-10-01.md#documentation-correction-addendum---2026-10-03)
> for advisory-feed limits, artifact-specific license flags and applied enforcement.

> **Audience/ownership clarification: 2026-10-08.** This updates how to use the
> records, not their dates, scan results or source identities.

## What this pack is

These records help **maintainers** assess changes and release claims,
**contributors** reproduce relevant checks and understand coverage,
**users** judge supported behavior and limitations, and **enterprise adopters**
perform their own import and deployment assessment. Historical `handover-evidence`
paths remain stable; the folder name does not transfer public-project security,
licensing or release responsibilities to adopters.

KS is a local stdio process doing deterministic FTS5/BM25 retrieval and
suggestion-only guidance. It neither produces nor consumes `app-definition.yaml`.
Studio Knowledge Assist is a separate optional consumer. The pack supports
bounded claims; it is not production certification or publication approval.

## Reading Identity, Coverage And Limits

- **Dependency records:** [G4](dependencies.md) identifies the CPython 3.11 /
  Ubuntu 24.04 reference graph, tools, snapshot date and scope. The
  [November 2 correction](joserfc-correction-2026-11-02.md) records the current
  84-package graph and joserfc qualification. The
  [October 28 correction](audit-correction-2026-10-28.md) preserves its eight
  baseline findings as history; the earlier
  [source-preparation receipt](v5-source-preparation.md) preserves its Python
  3.11 proof. The October 15 MCP/3.10 receipt is
  dated history, not a current support claim. The historical
  [closure record](dependency-closure-2026-10-01.md) adds source/report hashes and
  dated support proof. SBOM/license metadata describe that resolved environment
  and artifact; they do not settle legal obligations for every platform.
- **Vulnerability records:** the 84-package report is a result at its stated
  cutoff using the scanner's available feed. Repository advisories can precede
  feed ingestion. Read the [source/date addendum](dependency-closure-2026-10-01.md#advisory-source-and-date-correction)
  and exclusions; a later green CI check does not restamp a stored report.
- **Secret/data records:** [G3](secret-and-data-scan.md) records configured-pattern
  scanning and bounded human observations. The current-tree CI scan is not a
  history scan and neither proves synthetic-only data nor absence of all secrets.
- **Behavior/CI records:** source tests and run results apply to the named commit,
  environment and executed checks. Inspect skipped steps and scope. Green
  documentation CI is not fresh runtime, coordinated Suite or release acceptance.
  Reference checks do not establish all-platform support proof.
- **Availability:** the committed reports, generators and tests provide the
  public reproduction starting point. Some historical support proof used
  separately retained receipts, as stated in its record; a clean clone does not
  contain all those raw logs. Do not promise exact replay of time-sensitive
  advisory results or copy private source archives/logs into this folder.

## Concern → evidence

| Import-review concern | Evidence (authoritative — click through) | Honest status |
|---|---|---|
| **License & dependencies** | [`dependencies.md`](dependencies.md) (cover) · [`mcp-correction-2026-10-15.md`](mcp-correction-2026-10-15.md) (historical graph/proof) · [`dependency-closure-2026-10-01.md`](dependency-closure-2026-10-01.md) (historical provenance, support proof, dated corrections) · [`sbom.cdx.json`](sbom.cdx.json) (CycloneDX) · [`dependency-licenses.md`](dependency-licenses.md) / [`.csv`](dependency-licenses.csv) (G4) · [`transitive-dependency-licenses.md`](transitive-dependency-licenses.md) / [`.csv`](transitive-dependency-licenses.csv) · [`pip-audit.md`](pip-audit.md) / [`.json`](pip-audit.json) · [`LICENSE`](../../LICENSE) | The current [November 2 snapshot](joserfc-correction-2026-11-02.md), CPython 3.11 / Ubuntu 24.04 reference snapshot covers **84/84** constrained packages; `pip-audit` reported no findings **at that scan time** in its available feed, not every repository advisory or all platforms. The October 1 record and pre-change protection snapshot are retained; the [2026-10-03 applied-state note](dependency-closure-2026-10-01.md#applied-enforcement-state) records the live audit as required. `certifi` MPL-2.0 and [caio UNKNOWN for affected non-reference artifacts](dependency-closure-2026-10-01.md#artifact-specific-license-correction) remain unresolved; packaged COPYING text and the reference wheel's Apache-2.0 metadata are not legal acceptance. Public terms and distribution dispositions remain [maintainer decisions](../publication-preparation.md#remaining-maintainer-decisions). |
| **Secrets & real data** | [`secret-and-data-scan.md`](secret-and-data-scan.md) · [`secret-scan` workflow](../../.github/workflows/secret-scan.yml) (G3) | Pinned **gitleaks `8.30.1`** scans the committed tree on PRs and main pushes for configured patterns; the dated observation found no matches. Synthetic-only content is a contributor policy requiring human review, not a scanner guarantee. |
| **Compliance & portability** | [`compliance-and-portability.md`](../compliance-and-portability.md) (G7) | The supported KS server runtime uses local stdio and sends no ingested content to a network service. Dependency installation and separately invoked audit/evidence tools can use the network. KS remains deterministic, with no LLM; retention and at-rest caveats remain. |
| **Security boundaries & attack surface** | [`security-boundary-map.md`](../security-boundary-map.md) (G8) | **Mapped + verified.** Local-stdio tool, no network surface; ingestion guarded by **resolve-then-contain path-allowlist + 50 MB cap + parser resource guards** (`safety.py`); **parameterized SQL + FTS5 query normalization** (verified). Honest open items: optional parser-library hostile-input risk, at-rest cleartext, soft-delete retention. |
| **Governance files** | [`CONTRIBUTING.md`](../../CONTRIBUTING.md) · [`SECURITY.md`](../../SECURITY.md) · [`.github/CODEOWNERS`](../../.github/CODEOWNERS) · [`pull_request_template.md`](../../.github/pull_request_template.md) · [issue templates](../../.github/ISSUE_TEMPLATE/) (G2) | Contributor/review guidance and non-security templates are present. CODEOWNERS remains a commented template, not enforced ownership. PVR/email are selected; the maintainer must verify their operation at cutover. |
| **CI evidence** | [`secret-scan.yml`](../../.github/workflows/secret-scan.yml) · [`ks-tests.yml`](../../.github/workflows/ks-tests.yml) | Workflows define tree scanning, constrained tests, core-only proof and live dependency audit. Consult the actual run and commit for its result; this index does not assert present-day green checks or release acceptance. |

## Open / adopter-decides / post-import (nothing hidden)

Caveats from the underlying records retain their historical import labels.
`[now-ours]` denotes a project responsibility; `[adopter-decides]` applies to local
import/deployment decisions; `[post-import]` records the older enterprise plan,
not a waiver of public-project responsibilities. Publication decisions are
consolidated in the [maintainer table](../publication-preparation.md#remaining-maintainer-decisions).

| Open item | Tag | Where it's authoritative |
|---|---|---|
| **KS terms applied; maintainer publication authorization pending** — Apache-2.0, NOTICE and DCO 1.1/no CLA are selected. Maintainer publication authorization and operational cutover remain required before exposure. | `[now-ours]` | [Publication decisions](../publication-preparation.md#remaining-maintainer-decisions) · [G7 §1](../compliance-and-portability.md#1-license-posture) |
| **Adopter rerun of dependency / license / vulnerability scans** — current P1 evidence is committed; rerun against the approved package mirror and review transitive / audit coverage flags before import. | `[adopter-decides]` | [G4 scope](dependencies.md#scope-read-this) · [pip-audit evidence](pip-audit.md) |
| **KS dependency follow-up decisions** — feed lag/cadence, future no-fix handling, tool-transitive pinning and excluded bootstrap/tool assessment, plus artifact-specific licensing; no policy or scheduled audit selected here. | `[now-ours]` / `[adopter-decides]` | [Owner-specific open list](dependency-closure-2026-10-01.md#open-owner-decisions) |
| **Optional document-parser surface** — `pdf`/`xlsx`/`docx` extras parse complex formats. KS now enforces ZIP resource/path guards for `xlsx`/`docx` and PDF page/text caps, but malformed-file parser-library risk remains. Ingest only trusted roots; keep extras disabled unless approved. | `[partly-hardened]` | [G8 §5.1](../security-boundary-map.md#5-honest-open-items--recommendations) |
| **At-rest index is cleartext** — local SQLite holds ingested content unencrypted; use host filesystem encryption for sensitive corpora. | `[adopter-decides]` (host posture) | [G8 §5.2](../security-boundary-map.md#5-honest-open-items--recommendations) |
| **Soft-delete retains data; purge cleanup has a bounded scope** — `delete_document` hides a document from active retrieval and keeps indexed data for audit. `purge_document(confirm_purge=True)` deletes document-scoped logical records, compacts FTS5, then scrubs SQLite freelist/WAL storage, with cleanup intent committed atomically with deletion and retained until successful cleanup and committed removal. Intent removal uses core SQLite zeroing and a checked final checkpoint; a process stop between removal and that checkpoint can leave ID/time residue without retry state. The tested pre-removal interruptions support confirmed same-ID retry; this is not power-loss, disk-full or universal crash-recovery proof. Historical purges without intent do not gain retroactive same-ID recovery. This is controlled live database/WAL cleanup, not erasure of backups, snapshots, storage-device remnants or copies held by other processes. Neither operation deletes the original source file. | `[operator-owned]` retention / external copies | [FTS5 purge correction record](../publication-preparation.md#open-fts5-purge-follow-up) · [G8 §5.3](../security-boundary-map.md#5-honest-open-items--recommendations) |
| **Cross-project reuse (intentional surface)** — `search_across_projects` can read all active indexed projects when `project_ids` is omitted. Generic `suggest_manifest_candidates(scope="portfolio_reuse")` searches other projects; persisted suggestions and `get_suggestion_evidence_chain(scope="portfolio_reuse")` can expose the matched source evidence. A caller-selected `project_id` is not tenant authorization; trust-separated corpora need separate database/process boundaries. | `[by-design]` | [G8 §5.8](../security-boundary-map.md#5-honest-open-items--recommendations) |
| **Optional AI** — **none in the codebase today** (deterministic FTS5/BM25 only). If ever added, it is gated by the **KS-B5** PII/sanitization design. | `[adopter-decides]` / posture-now | [G7 §5](../compliance-and-portability.md#5-data-handling-posture) |
| **Full threat model + supply-chain provenance maturity** (signed tags, attestation, enterprise scanners) | `[post-import]` | [G8 §5.7](../security-boundary-map.md#5-honest-open-items--recommendations) |

> **Reading the tags:** deployment approval belongs to the adopter; public
> project support, licensing, security routing and releases belong to project
> owners. `[by-design]` describes a surface to account for, not a security or
> risk-acceptance verdict. No pending item is closed by this index.

## Reproduce the evidence yourself

Use an isolated checkout/environment and record the source SHA, platform,
Python/tool versions, constraints identity, command, UTC time and result. Use the
[reference environment and exclusions](dependencies.md#reference-environment)
and the [current Python 3.11 proof](v5-source-preparation.md).
The earlier 3.10 record is historical only. Installation and advisory tooling may contact package/advisory
services and disclose dependency names/versions; run them under the applicable
authorization. These instructions do not schedule scans or request a new scan
merely because documentation changed.

- **Resolved constraints:** `PY=python3.11 make lock` regenerates
  [`constraints.txt`](../../constraints.txt).
- **SBOM + license inventory (G4):** `PY=python3.11 make sbom` (pinned
  `cyclonedx-py` + `pip-licenses` in an isolated venv) regenerates the resolved
  SBOM plus declared and transitive license inventories.
- **Vulnerability audit:** `PY=python3.11 scripts/generate-pip-audit-evidence.sh`
  regenerates [`pip-audit.md`](pip-audit.md) and [`pip-audit.json`](pip-audit.json).
  `PY=python3.11 make audit` runs the separate blocking live control.
- **Secret scan (G3):** runs automatically in CI
  ([`secret-scan.yml`](../../.github/workflows/secret-scan.yml)); locally,
  `gitleaks dir . --redact --exit-code 1` with pinned `8.30.1`.
- **Tests:** `make test` (or `python -m pytest`); the suite runs in CI
  ([`ks-tests.yml`](../../.github/workflows/ks-tests.yml)).

`make lock` resolves a new graph; it is a deliberate update, not replay of the
committed lock. To reproduce that graph, install with the existing constraints.
Regeneration commands overwrite report files: use the isolated checkout, retain
prior evidence, and review changes with new provenance. Scanners and package
indexes change, so results need not be byte-identical to historical snapshots.

## When To Refresh

Refresh the affected evidence when selected dependency pins, artifact/platform,
parser extras, scanner/configuration, runtime/storage boundaries or release refs
change materially, or when a newly relevant advisory requires disposition.
Record the reason and coverage, preserving previous observations. A prose-only
edit requires link/content validation and applicable CI, not a restamped audit.
The release owner selects final proof and audit freshness for the actual release;
feed/cadence and no-fix policy decisions remain open in the
[owner list](dependency-closure-2026-10-01.md#open-owner-decisions).

## Where to go next

- **What KS is / tool vocabulary / boundaries:** [`README.md`](../../README.md)
- **Compliance answer-sheet:** [`compliance-and-portability.md`](../compliance-and-portability.md) (G7)
- **Security boundary map:** [`security-boundary-map.md`](../security-boundary-map.md) (G8)
- **Authoritative rules:** [`CONTRIBUTING.md`](../../CONTRIBUTING.md)
