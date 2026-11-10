# Private v5 Source Preparation — Revision 2

Scope: **EF-V5-SOURCE-PREP-KS-S1 revision 2**, under maintainer-approved
**EF-V5-RELEASE-SCOPE-RESET revision 3**. Actual refreshed base:
`2d039891f485b1448d9dbf98898cbd065a13ca1e` (merged PR #47).
This resumes the original goal after its Python-compatibility pause, not a new
goal or release. The PR records final head, CI and independent exact-head review.
Dates use October 25, 2026 America/Chicago; UTC execution falls on October 26.

## Frozen Dependency And Python Decisions

One target set was resolved and verified; no alternative set was needed.
Only five of 84 application pins change from the base:

| Distribution | Before | Selected |
|---|---|---|
| fastmcp | 3.4.2 | 3.4.11 |
| fastmcp-slim | 3.4.2 | 3.4.11 |
| certifi | 2026.6.17 | 2026.10.23 |
| pillow | 12.3.0 | 13.0.0 |
| opentelemetry-api | 1.43.0 | 1.45.1 |

MCP remains 1.30.0; the other 79 pins are unchanged. Existing lock generation
used a seed retaining all unrelated pins, not blanket upgrades. FastMCP's
[3.4.10 authorization fix](https://github.com/PrefectHQ/fastmcp/releases/tag/v3.4.10)
and [3.4.11 certifi update](https://github.com/PrefectHQ/fastmcp/releases/tag/v3.4.11)
were checked against official advisories, rather than copying Engine's pin as
clearance. OTel API 1.45.1 is the fix named in
[GHSA-xcq7-p3pf-p88h](https://github.com/open-telemetry/opentelemetry-python/security/advisories/GHSA-xcq7-p3pf-p88h).
Package corrections do not imply that KS exposes HTTP, OAuth, OpenAPI proxy or
telemetry-exporter surfaces. KS still forces stdio and disables startup updates.
Updating certifi does not update system, custom or installer trust stores.

Pillow is required through the supported pdfplumber extra, not removed.
[Pillow 13 drops Python 3.10](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html#python-3-10).
The approved amendment raises **KS v5 to Python 3.11+**, preserving PDF support
without replacing the parser. The prior failed resolver probe was not repeated.
[October 15 Python 3.10 evidence](mcp-correction-2026-10-15.md#python-310-proof)
is preserved as history, not continued support. No SQLite support-floor change.

## Actual Proof

| Clean verification environment | Actual Python / loaded SQLite | Result |
|---|---|---|
| Ubuntu 24.04.5 x86_64 reference | 3.11.15 / 3.45.1 | Exact 84-package install, pip check; 338 full tests passed, no skips |
| Debian 12 x86_64 older-SQLite check | 3.11.15 / 3.40.1 | Clean same constrained graph, pip check; 108 PDF/stdio/hardening/purge/atomic-retry tests passed, no skips |

Cached task-local images were reused in new disposable containers and clean
venvs; they were not rebuilt or shipped as KS images. Linux/amd64 execution is
not a macOS reference run. Python's loaded SQLite was measured, not inferred
from the CLI or OS. Existing FTS format 4 and pre-3.42-compatible maintenance
remain unchanged; storage/parser source is unchanged.

The first full run had four stale evidence-inventory failures before generation
finished and one validation-error compatibility failure. FastMCP now wraps
Pydantic argument errors as its own ValidationError. The minimal repair catches
both types and retains KS's generic error, with missing-argument and wrong-type
real-stdio regressions. The repaired full run passes; no failure is called a
skip or a successful run. Existing root masking/no-listener/no-egress, real
purge interruption/reopen/retry, unrelated-state and remanence controls pass.

A separate clean Python 3.11 core install leaves all three parser libraries
absent with actionable loader errors. The all-extras install executes normal
PDF/XLSX/DOCX parsing. Actual stdio initialize/tools-list returns the same 16
tool names; public signatures and result models are unchanged. No exhaustive
cross-version byte comparison of every result is claimed.

Built and installed wheel plus sdist checks confirm `License-Expression:
Apache-2.0`, `Requires-Python: >=3.11`, unchanged package version 4.1.0, no
proprietary classifier, and LICENSE/NOTICE inclusion matching the source files.
The setuptools floor is 77.0.3 for SPDX/license-files support; the actual sdist
backend is recorded in the build log. No release package is published.

## Dependency Evidence And Limits

Existing tools: pip-audit 2.10.1, cyclonedx-bom 7.3.0, pip-licenses 5.5.5 and
generator tomli 2.0.1, isolated from the application environment. Current
stored audit and the unchanged strict live gate cover **84/84, zero findings**
at their execution times. Installed inventory and SBOM each have 87 records
including local KS, pip and setuptools; transitive licenses cover exactly 84,
declared licenses seven. Normalized names/versions agree across all artifacts.
Reports were generated using existing scripts, not manually edited.

Command-log completion times were 2026-10-26T02:32:17Z (strict live gate),
02:35:10Z (stored audit generation) and 02:35:34Z (SBOM/license generation).
These identify execution, not an authoritative advisory-feed update cutoff.
SHA-256 identities:

| Artifact | SHA-256 |
|---|---|
| `constraints.txt` | `17c82334507539e458225215e584256b4ffd451defa93823b3e1d99cf787f432` |
| `pip-audit.json` | `9dc63453678ddba18085a1f1986c8d02661286a59534af9b8df9292b2ccf6cc0` |
| `sbom.cdx.json` | `227e8481239158d5d9e57d7e8659bf4049d40f8472f3a37a64b66fb68b3327a6` |
| `transitive-dependency-licenses.csv` | `642773319435155d6a8ae575a5c5eb24dd92167dda58e5e1b8c3aa6aa8e86486` |

Interpreter, OS/native libraries, bootstrap and isolated-tool dependencies are
not cleared by the application audit. Available-feed zero findings are dated,
not exhaustive ongoing advisory coverage. certifi MPL-2.0 and historical caio
artifact-specific metadata questions remain relevant if those third-party
artifacts are distributed; source release does not bundle their wheels.
No license-risk acceptance or public exposure is authorized by these results.
Historical October 1/15 and PR #45/#46 receipts remain unchanged.

Reproduction uses the committed constraints in a clean Python 3.11 environment:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -c constraints.txt -e '.[all,test]'
.venv/bin/python scripts/dependency_audit.py installed --constraints constraints.txt
.venv/bin/python -m pip check
.venv/bin/python -m pytest tests/ -q
PY=python3.11 scripts/check-dependency-audit.sh
PY=python3.11 scripts/generate-pip-audit-evidence.sh 2026-10-25
PY=python3.11 scripts/generate-dependency-evidence.sh 2026-10-25
```

## Bounded Current-Content And Publication Check

At the October 25 preparation head, reviewed tracked files and prepared changes,
fixtures, metadata, docs, workflow/config references and attribution. The only tracked compressed fixture
is the XLSX dictionary: nine ZIP entries, fabricated Account/Customer field
rows, creator `openpyxl`, no embedded source corpus. Plain fixtures contain
generic fabricated requirements/DDL, not production records. No private
planning material or non-public correspondence was added or found in this bounded
current-tree pass. This is not synthetic-only certification or a history scan.
This dated pass does not establish a content review of later corrections,
the private import or the v5 release-preparation head.
Existing gitleaks 8.30.1 current-directory scanning reports no configured-pattern
findings; no new scanner/evidence tooling or archive campaign was introduced.
Generated build outputs were moved out of the checkout and are not committed.

Apache-2.0, short NOTICE/copyright Santosh Hommaradi, DCO 1.1/no CLA and the
edgeforge-suite destination are applied. Selected PVR/email routes are not
claimed operational. Maintainer publication authorization, email activation/test,
PVR enablement/verification at cutover and final release refs remain pending.
No DNS/settings/visibility/version/tag/release/website or sibling edits.
See [current operational gates](../publication-preparation.md#remaining-maintainer-decisions).

Remaining purge limitations include the disclosed post-intent-removal metadata
checkpoint window and external copies/backups/snapshots; no power-loss or
universal crash guarantee. No old-history scan, Suite L5, new platform matrix
or public upload. Required exact-head CI and the separately attributed review
are recorded on the draft PR; nonblocking improvements are listed once there.
