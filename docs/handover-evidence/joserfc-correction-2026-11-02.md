# joserfc Correction — 2026-11-02

**EF-V5-KS-JOSERFC-CORRECTION-S1 revision 1.** Refreshed main/base:
`97d65b21fe064a6ed484779d1a57c651988bef65`. No intervening main changes or
duplicate open PR were found at setup. Local proof used the isolated correction
on this base; the PR records the final tested CI head and independent review.
Dates use America/Chicago; execution continues into November 3 UTC.

## One-Pin Qualification

Only **joserfc 1.7.1 -> 1.7.6** changes among **84** reference pins.
The other **83**, including FastMCP/slim 3.4.11, MCP 1.30.0, Authlib 1.9.1,
cryptography 50.0.1, OTel and parser dependencies, are unchanged. No new direct
dependency, unrestricted lock refresh, support-floor or runtime-source change.

The [reviewed advisory](https://github.com/advisories/GHSA-9pg5-8c7x-5hfx)
identifies <1.7.6 as affected and 1.7.6 as patched. The
[repository advisory](https://github.com/authlib/joserfc/security/advisories/GHSA-9pg5-8c7x-5hfx)
still identifies <=1.7.4 / 1.7.5. Both observations are retained; the reviewed
range, released code and actual installed behavior qualify this selection.
No broad investigation or assertion that the upstream records agree is made.

The [released compact-JWS implementation](https://github.com/authlib/joserfc/blob/1.7.6/src/joserfc/_rfc7797/compact.py)
calls `validate_compact_value_size` before `split`. PyPI metadata requires
Python >=3.10 and cryptography >=45.0.1, fitting KS Python >=3.11 and its
unchanged cryptography pin. Wheel and sdist hashes were checked against PyPI;
their relevant compact/registry source matches the release tag and installed
candidate bytes. Only the selected 1.7.6 candidate was evaluated.

| Published artifact | SHA-256 |
|---|---|
| `joserfc-1.7.6-py3-none-any.whl` | `e2d72e3fa937ed8ddd42ad8c1cc337a43e7ffd02efa572a2aa15e2764a05b506` |
| `joserfc-1.7.6.tar.gz` | `fb1cf6d2977318bef976c2ed2ef2167cc5f8ade8fc96f034e38f7abd656907c4` |

Actual installed metadata confirms **both** introducing paths:

- FastMCP 3.4.11 -> fastmcp-slim server extra -> `joserfc>=1.1.0`.
- FastMCP/slim -> Authlib 1.9.1 -> `joserfc>=1.6.8`.

The bounded canary approach reuses the qualification pattern recorded in
[Engine #338](https://github.com/santosh-sh/EdgeForge/pull/338); KS executes its
own candidate and controls, rather than inheriting Engine acceptance.

## Actual Proof And Evidence

Reference: **Ubuntu 24.04.5 x86_64, CPython 3.11.15, loaded SQLite 3.45.1**.
The cached reference environment was reused in a new disposable container and
clean venvs, not rebuilt or assessed as a shipped image. No platform matrix.

Clean constrained all/test installation, exact installed inventory and
`pip check` pass. Separate core-only installation keeps PDF/XLSX/DOCX absent
with actionable loader errors. Both dependency-path requirements accept 1.7.6.

A small byte-subclass canary raises if `split` is reached under a 96-byte
configured compact limit. On actual 1.7.1, it fails at that assertion; the
valid-signature/wrong-key control passes. On actual 1.7.6, both tests pass:
oversized input is rejected first, valid signatures verify and wrong keys fail.
The old minimal probe emits two harmless pytest-asyncio configuration warnings
because that plugin is absent there. No memory-exhaustion benchmark or live
target was used; these are behavioral tests, not version-assertion tests.

**130 focused tests passed, no skips**: new controls, real stdio/MCP, 16-tool
listing, malformed ingest/decision privacy, root/no-listener/update protections,
PDF, retrieval/field suggestions, hard purge and atomic intent/retry. Existing
dependency inventory/control tests separately pass **42**, no skips. The full
suite is reserved for normal exact-head CI, not duplicated locally.

One retained baseline pip-audit 2.10.1 scan covered **84/84** packages, exit 1:
two findings, both in joserfc 1.7.1, and no unrelated affected package:

- CVE-2026-119284 / GHSA-9pg5-8c7x-5hfx: reviewed fix 1.7.6.
- [CVE-2026-119283 / GHSA-jpxq-7h8p-2q76](https://github.com/advisories/GHSA-jpxq-7h8p-2q76): JWE recipient exhaustion, reviewed fix 1.7.5, included in the selected later release. No additional package change is needed.

Candidate stored and strict live audits cover **84/84**, **zero findings**, no
omitted/skipped versions or scanner errors at execution. Established generators
use pip-audit 2.10.1, cyclonedx-bom 7.3.0 and pip-licenses 5.5.5 (isolated tools).
SBOM/installed inventory includes KS and bootstrap components separately;
transitive licenses cover 84 and declared licenses seven. Normalized inventory
tests verify agreement. The audit gate and advisory lint policy are unchanged.

## Boundaries And Handoff

The [October 28 receipt](audit-correction-2026-10-28.md) and earlier October
records/hashes remain dated history.
Detailed logs, official-source receipts, baseline/candidate JSON and review evidence are retained privately by the maintainer, outside Git.
No wheels, advisory bodies or host paths are committed. Final exact-head CI
and review references belong to the PR.

KS still exposes only local stdio, deterministic evidence and suggestions, not
network authentication endpoints or manifest mutation. Root/project binding,
parser optionality, known purge/retry limits, Apache/NOTICE/DCO and support
boundaries are unchanged. No exploitability conclusion follows solely from a
package advisory. Feed freshness, native/OS/interpreter/bootstrap/tool exclusions
and artifact-specific license flags remain as in [dependency guidance](dependencies.md).

Maintainer publication authorization, reporting-route operation and final release
selection remain separate gates.
Independent review of the exact candidate head and the human merge decision are recorded on the PR.
No merge, publication, settings change, release bump or M2 clearance.
