# Dependency Audit Correction — 2026-10-28

**EF-V5-KS-AUDIT-CORRECTION-S1 revision 1**, updating draft PR #49 without
rewriting its documentation commit. Refreshed main was
`242886bd3e57c256da2cb80f2b12ce9975a876d5`; initial PR head was
`8026ab18b3336be2860cc0d3cc857dcdf4086716`. Final head, exact-head CI and
independent review are recorded on the PR. This is not M2 or release clearance.

## Baseline And Fix Evidence

One baseline scan with **pip-audit 2.10.1**, using the existing options
`-r constraints.txt --no-deps --disable-pip --format json --output ...`,
returned status 1: **84 packages, eight findings, no omitted/skipped packages**.
Its JSON was retained outside the temporary wrapper before cleanup, not
replaced by a green report or inferred from the old CI summary.

| Affected coordinate | Finding / upstream advisory | Feed fix | Candidate |
|---|---|---|---|
| Authlib 1.7.2 | [CVE-2026-96760 / empty JWS signatures](https://github.com/authlib/authlib/security/advisories/GHSA-6v38-4h7w-rj9h) | 1.9.0 | 1.9.1 |
| Authlib 1.7.2 | [CVE-2026-114618 / JWT audience](https://github.com/authlib/authlib/security/advisories/GHSA-fch4-3c6x-j4gc) | 1.9.0 | 1.9.1 |
| Authlib 1.7.2 | [CVE-2026-114615 / asymmetric key as HMAC](https://github.com/authlib/authlib/security/advisories/GHSA-7vr2-2fgp-9w7p) | 1.9.0 | 1.9.1 |
| Authlib 1.7.2 | [CVE-2026-114617 / nonce validation](https://github.com/authlib/authlib/security/advisories/GHSA-c5mf-xmp2-59rc) | 1.9.0 | 1.9.1 |
| Authlib 1.7.2 | [CVE-2026-114620 / request URI retrieval](https://github.com/authlib/authlib/security/advisories/GHSA-x4rv-c3wx-4cr8) | 1.9.0 | 1.9.1 |
| Authlib 1.7.2 | [CVE-2026-114614 / loopback userinfo](https://github.com/authlib/authlib/security/advisories/GHSA-jj7h-c3hg-m23x) | 1.8.0 | 1.9.1 |
| Authlib 1.7.2 | [CVE-2026-114616 / empty HMAC](https://github.com/authlib/authlib/security/advisories/GHSA-8m4g-j4wp-wgcg) | 1.9.1 | 1.9.1 |
| dnspython 2.8.0 | [CVE-2026-114605 / name decompression](https://github.com/rthalley/dnspython/security/advisories/GHSA-45c3-73f7-pv4m) | 2.9.0 | 2.9.0 |

The empty-HMAC repository advisory still says patched versions "None" and
affected <=1.7.2, whereas the scanner feed names 1.9.1. This is not silently
treated as approval: the [tagged 1.9.1 changelog](https://github.com/authlib/authlib/blob/v1.9.1/docs/upgrades/changelog.rst)
explicitly records empty-key rejection, and the published wheel's
`OctKey._check_key` / `get_op_key` checks were inspected. Wheel SHA-256 was
verified against PyPI:
`8b9be8b1e5174dcbf5520e984f1a22dc2edae5b6e40a61d4cedbf86b97e9e69b`.
The [1.8/1.9 release changes](https://docs.authlib.org/en/stable/upgrades/changelog.html)
also explain the other Authlib fixes; [dnspython 2.9](https://dnspython.readthedocs.io/en/stable/whatsnew.html)
limits compression chains to 16. Metadata requires Python >=3.10 for Authlib
and >=3.11 for dnspython: both fit KS's existing Python 3.11 minimum.

Six bounded offline controls detected baseline acceptance and candidate
rejection: empty raw/JWK HMAC keys, leading-PEM HMAC material, spoofed loopback
userinfo, empty JWS signatures, and a 20-pointer DNS chain. A correctly signed
synthetic JWS passed in both environments. The first one-off harness missed
Authlib's signature exception class; it was corrected before the valid runs.
These controls support the released fixes, not a claim that KS exposes OAuth,
an authorization server or DNS request endpoints. No live target was probed.

## Compatibility And Current Evidence

Only **Authlib 1.7.2 -> 1.9.1** and **dnspython 2.8.0 -> 2.9.0** change.
All other 82 pins remain fixed, including FastMCP/slim 3.4.11, MCP 1.30.0,
OTel API 1.45.1 and Pillow 13.0.0. Existing cryptography/joserfc satisfy the
new Authlib requirements; no new transitive is needed. The reference constraints
received a minimal explicit correction, not an unrestricted lock refresh.
No Python/SQLite floor, runtime source, tool/schema or parser/storage change.

Actual clean environment: **Ubuntu 24.04.5, x86_64, Python 3.11.15, loaded SQLite
3.45.1**. Reused the cached reference verification environment in a new disposable
container/venvs; no image build or image assessment. Clean constrained all/test
install, exact installed inventory and `pip check` pass. Core-only install keeps
PDF/XLSX/DOCX libraries absent with actionable missing-extra errors.

Focused local checks: **126 passed, no skips**, covering real stdio/MCP,
16-tool listing, runtime hardening, PDF, purge/atomic retry, foundation retrieval
and field suggestions. The extended privacy regression separately passes
**23 tests**, including malformed decision-container and decision-status inputs.
The complete suite is intentionally left to exact-head CI, not duplicated
locally. CI/review results and any subsequent repair proof are on the PR.

Established generators refreshed the current audit/SBOM/licenses with their
existing pinned tooling. Candidate stored and strict live audits report
**84/84 packages, zero findings, no skipped entries** at execution on October 28.
The installed inventory and SBOM have 87 components including KS/pip/setuptools;
transitive licenses cover 84 and declared licenses seven. Existing inventory
controls verify normalized name/version agreement. Earlier October 1/15/25 and
purge records are preserved as dated evidence, not restamped acceptance.

| Current artifact | SHA-256 |
|---|---|
| `constraints.txt` | `f12058296cde6fa60c7da118320fa7162cbe1a7d983ba6c41e30989d10e71f9f` |
| `pip-audit.json` | `3c2fadc51344be3f0f7bc1fa351a2e608d4c3b276275f3ff49682fd8c9d16c66` |
| `sbom.cdx.json` | `059f087c2c7ab732c90aa8c8afaa3a580bcd9c35f1206ec05fab0a1cf0d02bab` |
| `transitive-dependency-licenses.csv` | `418c9b38d30201e3009a8dc1a8e632b04cb486277a994f1b308579fb29ecc1ca` |

## Limits And Preservation

No advisory suppression, audit-gate change, live-service addition or risk
acceptance. Feed freshness, OS/native/interpreter/bootstrap/tool exclusions,
platform-specific licensing and distribution obligations remain as described in
[dependency guidance](dependencies.md). Zero findings is dated available-feed
evidence, not universal or continuing security clearance.

PR #49's project-intent, Apache terms, no promised service/support, adopter
responsibilities and project-owned reporting/publication gates remain intact.
KS remains local stdio, deterministic, suggestion-only and manifest-independent;
source files and unrelated projects retain the existing purge protections.
Raw baseline/candidate JSON and concise validation/review evidence are retained
in the maintainer's existing private artifact location outside iCloud, not
committed as another archive. No merge, publication, version or settings change.

**Retention clarification — 2026-11-07:** the October 28 record's "outside
iCloud" claim is not established by the verified retention location. The known
copy is retained privately outside Git in a cloud-synced personal folder. This
does not establish whether another copy existed earlier. The dated dependency
results and hashes are unchanged. The November 2 correction has a separate
retention record and does not establish the October 28 location.
