# Dependency Evidence — SBOM + License + Audit Inventory

> **Import-gate G4 / P1.** The dependency artifacts an import / compliance reviewer
> asks for first, for **Knowledge Server's Python dependency surface**.
> Part of the handover-evidence set (the G10 index links these).
>
> **Current snapshot:** dnspython / OpenTelemetry API correction, 2026-11-14 (America/Chicago).
> The generated reports below record the current inventory and scan results.
> These artifacts are **regeneratable** with named,
> pinned tools (below).

The current graph updates only transitive dnspython 2.9.0 to 2.9.2 and
OpenTelemetry API 1.45.1 to 1.45.2 for
[GHSA-vvf4-9x63-8xvv](https://github.com/advisories/GHSA-vvf4-9x63-8xvv) and
[GHSA-mf5v-w3w3-f6cg](https://github.com/advisories/GHSA-mf5v-w3w3-f6cg).
The other 82 reference versions and all direct declarations are unchanged.
The regenerated audit, SBOM and transitive licences cover the same 84-package
reference graph; this is not whole-image or Suite acceptance clearance.

The SBOM also records the existing project version 5.0.0 and the actual generator
environment's installer packages. Those components are outside the 84-pin audit
surface. The unchanged caio 0.9.25 package is reported as UNKNOWN by this host's
license-metadata scan, alongside the existing certifi MPL flag; the reports retain
that classification rather than treating it as license acceptance.

The [November 2 correction](joserfc-correction-2026-11-02.md) preserves its one
changed pin and qualification as dated evidence. The [October 28 correction](audit-correction-2026-10-28.md)
preserves its two-pin change and eight baseline findings as dated evidence. The
[source-preparation record](v5-source-preparation.md) preserves its earlier
five-pin change, graph/report identities and Python 3.11 proof as dated evidence.
The [MCP correction record](mcp-correction-2026-10-15.md) remains dated history.
The historical [dependency closure record](dependency-closure-2026-10-01.md)
identifies its earlier pin change, exact graph/report hashes, supported-install
proof, Python 3.10 differences, unresolved license flags, and historical
enforcement gap. Its [2026-10-03 correction addendum](dependency-closure-2026-10-01.md#documentation-correction-addendum---2026-10-03)
records bounded repository-advisory lookups, artifact-specific licensing and
the applied required audit check. That October 1 observation is preserved;
the generated current reports now reflect the November 14 two-pin correction.

## The artifacts

| Artifact | What it is | Tool |
|---|---|---|
| [`sbom.cdx.json`](sbom.cdx.json) | A **CycloneDX 1.6** SBOM of the resolved KS `[all,test]` environment. | `cyclonedx-py` (`cyclonedx-bom` **7.3.0**) |
| [`dependency-licenses.md`](dependency-licenses.md) (+ [`.csv`](dependency-licenses.csv)) | Resolved license inventory for KS's directly declared dependencies. | `pip-licenses` **5.5.5** |
| [`transitive-dependency-licenses.md`](transitive-dependency-licenses.md) (+ [`.csv`](transitive-dependency-licenses.csv)) | Resolved transitive license scan for the KS `[all,test]` environment, including honest flags. | `pip-licenses` **5.5.5** |
| [`pip-audit.md`](pip-audit.md) (+ [`.json`](pip-audit.json)) | Vulnerability audit report for every exact package in the resolved [`constraints.txt`](../../constraints.txt) dependency set. | `pip-audit` **2.10.1** |
| [`requirements.txt`](../../requirements.txt) | Direct dependency mirror of `pyproject.toml` core, optional parser, and test dependency declarations. | Maintained in repo |
| [`constraints.txt`](../../constraints.txt) | Resolved lock/constraints export for core + all optional parser extras + test dependencies. | `make lock` |

## KS dependency surface (from `pyproject.toml`)

- **Core runtime (always installed):** `fastmcp`, `pydantic`.
- **Optional parser extras (opt-in, off by default):** `excel` → `openpyxl`,
  `pdf` → `pdfplumber`, `docx` → `python-docx`. These are document-format
  capabilities, **not** MCP servers, and the core install does not require them.
- **Test-only:** `pytest`, `pytest-asyncio`.

KS does **not** call or depend on public hosted MCP servers at runtime; `fastmcp`
is a Python library used to expose KS's *own* local stdio MCP server.

## Reference environment

- **Reference CI/evidence platform:** CPython 3.11 on Ubuntu 24.04 x86_64.
- **Resolved graph:** the exact versions in `constraints.txt`; CI tests, live
  auditing, SBOM generation, and transitive license generation consume that same
  graph.
- **Conditional Linux graph:** the lock includes `SecretStorage` and `jeepney`,
  which `keyring` installs on the Ubuntu reference platform. The lock generator
  resolves these packages explicitly so regeneration on another host cannot
  silently omit them.
- **Supported v5 runtime is Python 3.11+.** Revision 2 raises the Python floor
  to preserve PDF support with Pillow 13. SQLite compatibility is unchanged.
  The [earlier 3.10 proof](mcp-correction-2026-10-15.md#python-310-proof)
  is preserved as dated evidence, not claimed current support. No failed
  resolver probe is repeated or new 3.10 matrix created.
- **Core-only remains supported.** CI installs `-e .` in an isolated environment
  and verifies that Excel, PDF, and DOCX parser libraries remain opt-in with
  actionable missing-dependency errors.

## Regeneration

```bash
PY=python3.11 make lock
PY=python3.11 make audit
make sbom
PY=python3.11 scripts/generate-pip-audit-evidence.sh
# or directly:
scripts/generate-dependency-evidence.sh
```

The script installs the **pinned** tools (`cyclonedx-bom==7.3.0`,
`pip-licenses==5.5.5`) into an **isolated** venv (so the tooling never pollutes
KS's own dependency surface), installs KS into a project venv constrained by
`constraints.txt`, verifies every normalized package name and version, then
emits the CycloneDX SBOM (`cyclonedx-py environment`), the declared-dependency
license inventory (`pip-licenses`, filtered to declared names), and the resolved
transitive license scan. `make lock` regenerates the resolved constraints.
`make audit` runs the blocking live check; the evidence generator records the
same pinned scanner output under this directory. Installed-inventory validation
rejects packages outside the constraints except the local KS distribution and
the documented environment bootstrap packages (`pip`, `setuptools`, and
`wheel`).

## Honest status

- `pip-audit` **2.10.1** reported all **84 of 84** constrained packages,
  including `packaging==26.2`, with **no known vulnerabilities** at scan time.
  This is the scanner's available feed result, not immediate coverage of every
  upstream repository advisory. See the [source/date correction](dependency-closure-2026-10-01.md#advisory-source-and-date-correction).
- From main `97d65b21`, only joserfc 1.7.1 -> 1.7.6 changes. The other 83
  pins, including FastMCP/slim, MCP, Authlib, cryptography, OTel, parser and
  Linux conditional packages, remain unchanged. Both Authlib and the
  FastMCP server extra's joserfc requirements are satisfied.
- The declared-dependency license scan reports no copyleft or UNKNOWN licenses
  among directly declared dependencies.
- `certifi` (MPL-2.0) and `caio` UNKNOWN for affected non-reference artifacts
  remain open for adopter/legal review, not merely historical concerns.
  The reference CPython 3.11 manylinux_2_34 x86_64 wheel declares Apache-2.0,
  reflected truthfully in the generated SBOM/license outputs. Hash-verified
  macOS, older-manylinux, fallback-wheel and sdist samples lack license
  declarations despite packaged Apache-2.0 COPYING text. These samples do not
  establish metadata for all Python/platform artifacts or accept terms.
  See the [dated artifact-specific correction and hashes](dependency-closure-2026-10-01.md#artifact-specific-license-correction).
- All evidence is time-sensitive and package-index/advisory-database dependent;
  regenerate it against the adopter's approved package mirror.

## Scope (read this)

- **Declared surface:** `requirements.txt`, `dependency-licenses.*`, and the
  pyproject dependency declarations cover KS's directly declared packages.
- **Resolved surface:** `constraints.txt`, `sbom.cdx.json`, and
  `transitive-dependency-licenses.*` cover the resolved core + optional parser
  extras + test dependency set used for handover evidence. `pip-audit.*`
  records the audit output plus exact normalized name/version coverage against
  that set.
- **Optional parser extras** (`openpyxl` / `pdfplumber` / `python-docx`) are
  opt-in; install only the formats an adopter approves.
- **Excluded from the vulnerability baseline:** the Python interpreter, OS
  packages/native libraries, and isolated audit/SBOM/license-tool dependencies.
  The SBOM may additionally record the local KS distribution and environment
  bootstrap components (`pip`, `setuptools`, and `wheel`), but those are not
  application constraints. Any other installed package fails inventory
  validation. The lock does not include hashes; adopters should install from an
  approved mirror/wheelhouse and may add organization-controlled hashes or
  attestations. Exclusion is an open coverage limit, not a not-affected finding
  or clearance of bootstrap/tool advisory concerns.

## Third-Party And KS Terms

These inventories describe third-party metadata, not blanket legal clearance.
KS's own [LICENSE](../../LICENSE) is Apache-2.0, with [NOTICE](../../NOTICE),
copyright Santosh Hommaradi and DCO 1.1/no CLA. Maintainer publication authorization
still blocks exposure. Source release does not bundle dependency wheels;
artifact-specific flags remain relevant if those artifacts are redistributed.
See [remaining operational gates](../publication-preparation.md#remaining-maintainer-decisions).

## Blocking control and snapshot evidence

CI installs and tests the constrained graph, verifies its normalized package
inventory and `pip check`, and runs `pip-audit==2.10.1` in an isolated tooling
environment. Vulnerability findings, missing packages, version mismatches, and
scanner execution failures, malformed advisory results and skipped entries all
fail the live audit job. Committed reports remain
time-specific evidence rather than a byte-for-byte CI oracle.

The **observed pre-change protection snapshot on 2026-10-01** required only
`KS test suite` and `gitleaks secret scan` (`app_id: 15368`, `strict: true`), not
`Blocking dependency audit`. No repository rulesets were returned. The exact
add-only settings handoff is retained in the closure record; this historical
snapshot is not current settings.

**Applied state, documented 2026-10-03:** the authorized change's read-back in
[PR #42](https://github.com/santosh-sh/EdgeForgeKnowledgeServer/pull/42) was
2026-10-02T03:19:06Z. The [2026-10-03 read-back note](dependency-closure-2026-10-01.md#applied-enforcement-state)
records all three checks required, each app 15368, strict true, and coordinator
rulesets `[]`. This PR does not change settings. Remaining feed, no-fix,
tooling and distribution-specific licensing decisions have
[named owners](dependency-closure-2026-10-01.md#open-owner-decisions).
