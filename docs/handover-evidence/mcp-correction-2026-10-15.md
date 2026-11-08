# MCP Dependency Correction Verification — 2026-10-15

Bounded task: **EF-V5-M2-KS-MCP-CORRECTION-S1 revision 1**. Source base:
`6d7b4ea038c3d0835ba5be28cdb840e1495ec630` (merged PR #46).
The correction PR records the final head, exact-head CI and independent review;
these build receipts are not publication approval or complete Suite M2 acceptance.
Dates use America/Chicago; the UTC cutoffs below fall on October 16.
The [October 1 closure and October 3 addendum](dependency-closure-2026-10-01.md)
remain dated historical observations, not restamped current evidence.

## Correction And Transport Exposure

Only application delta: **MCP 1.28.1 -> 1.30.0**; all other **83** reference
pins remain unchanged, including **FastMCP and FastMCP-slim 3.4.2**. The existing
bounded lock generator used the prior constraints as `BASE_CONSTRAINTS` and
`UPDATE_PACKAGES=mcp==1.30.0`; no general refresh or advisory suppression.
MCP remains transitive, not newly promoted into `pyproject.toml` or
`requirements.txt`. FastMCP-slim's existing `mcp>=1.24.0,<2.0` requirement is
satisfied, and the existing graph satisfies MCP 1.30.0 without further changes.

[GHSA-84m7-p3x7-pcfv](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-84m7-p3x7-pcfv)
affects stateful Streamable HTTP session retention in MCP >=1.8.0,<1.30.0;
1.30.0 is the patched 1.x release. **The advisory excludes stdio-only servers.**
The vulnerable package range and actual KS exposure are distinct: KS's supported
entrypoint still forces stdio and disables banner/update checks. No listener,
authentication surface, tool, schema, runtime source or database change is made.

## Reference Proof

Measured **CPython 3.11.15, SQLite 3.45.1, Ubuntu 24.04.5, Linux x86_64**.
The cached task-local `ks-dependency-closure-reference:20261001` image was reused,
not rebuilt; image ID
`sha256:04909be333fbbe7f9d1751bbf34e59764890e02dcc7b5c2d9ec84b565758b90b`.
Execution is Linux/amd64 emulation on an ARM64 host, not a macOS reference run.
Its construction and system-SQLite link are described in the
[PR #45 runtime receipt](fts5-purge-verification-2026-10-10.md#identity-and-actual-runtime).
KS does not ship a container; this is only a disposable verification environment.

Clean `.[all,test]` installation passed `pip check` and exact installed-inventory
validation: **84 constrained packages**, **87 installed distributions** including
local KS, pip and setuptools. Generated SBOM contains those same 87; transitive
licenses and stored audit each cover all 84 exact application pins. The seven
directly declared dependencies still match `requirements.txt` exactly.
The `all` extra still aggregates only the three optional parser extras.

- Full reference suite: **337 passed, no skips**.
- Explicit MCP/stdio/runtime-hardening/hard-purge/atomic-intent suite:
  **103 passed, no skips**. This retains indexed-term/prefix-suffix remanence,
  real interruption/reopen/retry, pending-record removal, root confinement and
  hostile environment/CWD controls from the existing tests.
- Real baseline/candidate stdio initialize and `tools/list`: **all 16 complete
  tool objects equal**, including descriptions and input/output schemas.
  Representative ingest/search/evidence/read/generic suggestions/evidence-chain/
  decision/project-isolation/purge interactions preserve response shapes;
  repeated search is deterministic, original source is retained, and purged
  suggestion lookup fails clearly. Tool-object comparison SHA-256:
  `6cab1327be0d6fbcf08a3a1b28fcd65ee968f314882f73f26f231d99e29016f8`.
- Clean core-only installation passed `pip check`; openpyxl, pdfplumber and
  python-docx distributions were absent and their loaders returned actionable
  missing-extra errors. Each documented core/excel/pdf/docx/all+test installation
  input and the requirements mirror resolve under the selected constraints.
  Individual parser inputs were resolver checks; normal parser execution is
  covered by the full extras suite. Unconstrained installs are not claimed to
  reproduce the audited graph.
- Ruff and `git diff --check` passed; **174 local links/anchors** in changed
  Markdown passed. Required final-head CI and independent review are separate
  coordinator/reviewer evidence, not claimed by these local build results.

## Python 3.10 Proof

Measured separate **CPython 3.10.21, SQLite 3.40.1, Debian 12, Linux x86_64**,
using cached `python:3.10-bookworm` at
`sha256:0a06143d04e5207c0561a9803a007af1d3e7941634fd1a7f801079dca3644bf5`.
New task-owned container and clean venv; the image was reused, not rebuilt.

The separate input retains all corrected reference pins except the documented
`aiofile==3.9.0` and `rpds-py==0.30.0` replacements, adding `tomli==2.4.1` and
`backports-asyncio-runner==1.2.0` under Python <3.11 markers. This is the same
alternate-graph method as the historical [3.10 proof](dependency-closure-2026-10-01.md#python-310-proof),
now with MCP 1.30.0. It does not alter the reference lock or introduce a
universal lock, new supported floor or recurring matrix.

Clean install, imports, exact inventory and `pip check` passed: **86 application
packages**, **89 total distributions** including local KS and bootstrap.
Real stdio/runtime-hardening/MCP/hard-purge/atomic-intent checks: **103 passed,
no skips**, including the older SQLite regressions. This is focused support
proof, not a new full Python 3.10 suite run. Its separate inventory/audit raw
receipts are retained with the review handoff, not mixed into the committed
84-package reference SBOM/license/audit reports.

## Audits, Tools And Cutoffs

Existing isolated tooling: **pip-audit 2.10.1**, **cyclonedx-bom 7.3.0**,
**pip-licenses 5.5.5**, generator **tomli 2.0.1**. Existing generators produced
the current reports; generated data was not hand-edited. Public dependency
names/versions were sent through the established advisory service; no source,
corpus, database or whole SBOM upload to a new service.

| Check | Finished UTC | Coverage / findings |
|---|---|---|
| Stored reference audit, then strict validation (not just evidence mode) | 2026-10-16T04:12:44Z | 84/84, zero |
| Reference SBOM/license generation | 2026-10-16T04:14:11Z | 84 application pins; seven declared |
| Unchanged blocking `check-dependency-audit.sh` | 2026-10-16T04:16:33Z | 84/84, zero |
| Separate stored Python 3.10 audit, strict validation | 2026-10-16T04:13:57Z | 86/86, zero |
| Existing blocking audit implementation with 3.10 input | 2026-10-16T04:17:51Z | 86/86, zero |

These are available-feed observations at those cutoffs, not immediate coverage
of every upstream advisory or ongoing security clearance. Findings, omissions,
version drift, skipped/malformed results and scanner failures still fail the
existing gate; no enforcement, workflow or settings change is made.

## Reproduction

Use a fresh supported environment and the selected constraints; supply a
separate compatible input for Python 3.10 as specified above:

```bash
python -c 'import sys,sqlite3,platform; print(sys.version); print(sqlite3.sqlite_version); print(platform.platform(),platform.machine())'
python -m venv /tmp/ks-mcp-proof
/tmp/ks-mcp-proof/bin/python -m pip install -c constraints.txt -e '.[all,test]'
/tmp/ks-mcp-proof/bin/python scripts/dependency_audit.py installed --constraints constraints.txt
/tmp/ks-mcp-proof/bin/python -m pip check
/tmp/ks-mcp-proof/bin/python -m pytest tests/ -q
PY=python scripts/check-dependency-audit.sh
PY=python scripts/generate-pip-audit-evidence.sh 2026-10-15
PY=python scripts/generate-dependency-evidence.sh 2026-10-15
```

To reproduce the bounded update rather than a full re-resolution, use
`BASE_CONSTRAINTS=/path/to/prior-constraints.txt UPDATE_PACKAGES=mcp==1.30.0
SNAPSHOT_DATE=2026-10-15 PY=python scripts/generate-constraints.sh`.
The previous constraints are available at the exact base revision above.
For core-only proof, use a separate venv and `-e .` with the same constraints.

## Evidence Identities And Limits

SHA-256; normalized graph uses sorted PEP 503 names and `name==version` lines
with trailing LF. External support receipts avoid committing local paths or
self-referential build/review output.

| Artifact | SHA-256 |
|---|---|
| Normalized reference graph | `ae1d36c67ac567b7f3208a57d055a5950605424fd252aa571dcb3ffa08a5a5e3` |
| constraints.txt | `5dada9e6020db2d6cb23b0cc739f1eb4bb7b344de0d34a9eadf0e1e92adf44d2` |
| pip-audit.json | `38c3033064982a98b8bf0a6dc995859d44ea28cd7aa2e2aabcf67722da4584e6` |
| sbom.cdx.json | `04433ab0d427eae44dc7bf1381ea7df555f63fa8853c8dccfd979fb2492fe89d` |
| dependency-licenses.csv | `4147cde6d9996cf4eb26e353b4e3da9d8ed7d9e7acd7c6acff88157fe34575a3` |
| transitive-dependency-licenses.csv | `8e21aad8d06a5cf1aa9ee3127bc8b0f640fa38de100e11df26421390146b64cd` |
| External reference installed inventory | `e92526b31a94c1d59d266a7f3d70cdb4ac8e1cf4fd69e7a5aa3ae16a561a7ade` |
| External Python 3.10 constraints | `dd7ec355020bbc9f0310cdd0e3df7d3e0d7ae9369b8437a327e1cbf307dc30f9` |
| External Python 3.10 installed inventory | `107245074210e024f5ca7083f49bd4a1645232df4d98041a6f7d1af4c9875e67` |
| External Python 3.10 audit JSON | `97217e1adb38e88edba8438924901111f96bfe8aaab7281862143cc464c12952` |

Interpreter, OS/native libraries, bootstrap and isolated tool graphs remain
excluded from the application audit; exclusion is not clearance. Reference
bootstrap is pip 24.0/setuptools 79.0.1; Python 3.10 uses pip 23.0.1/setuptools
79.0.1. No unexpected installed application package is allowed.
Reference caio metadata still reports Apache-2.0; affected other artifacts'
UNKNOWN and certifi MPL-2.0 remain unresolved [license questions](dependency-closure-2026-10-01.md#artifact-specific-license-correction),
not accepted terms. No new OS/image, Windows or all-platform proof, Suite L5,
history scan, license/contact decision, release/tag or publication approval.
The [PR #45](fts5-purge-verification-2026-10-10.md) and
[PR #46](purge-atomic-intent-verification-2026-10-10.md) receipts remain intact;
their bounded erasure and interruption limitations are not broadened here.
