# KS Dependency Closure Snapshot

Approved scope: EF-V5-M2-KS-DEPENDENCY-CLOSURE-S1 revision 1. Snapshot date is
2026-10-01 in America/Chicago; UTC audit cutoff is **2026-10-02T02:18:22Z**.
Base: `d5cf86b6f77ab4d12a898707f4048e04beb2702f`. Final candidate SHA, draft PR,
command logs and review receipts are external to the reviewed commit to avoid
self-reference. This is KS-only build evidence, not Suite M2/release acceptance.

## Bounded graph and advisory basis

Only normalized application delta: **`pyjwt` 2.13.0 -> 2.15.0**. The other 83
reference pins are unchanged. Direct FastMCP 3.4.2 mirrors, MCP 1.28.1, Python
3.10+ metadata, optional parser extras and runtime/API source are unchanged.
PyJWT 2.15.0 declares Python >=3.9 and satisfies MCP's `pyjwt[crypto]>=2.10.1`.
Real KS subprocess compatibility tests passed before selection of the pin.

Public per-version PyPI metadata and ranges for the advisory identities it
listed were queried without uploading source, documents, an inventory or an SBOM. PyPI
returned 26 records for 2.13.0 (13 GHSA identities plus alias records), and none
for 2.15.0. These are metadata observations, not a replacement for the complete
blocking audit or an exhaustive upstream list. The table below preserves the
PyPI-selected identities/ranges observed during that run; see the
[2026-10-03 correction](#advisory-source-and-date-correction) for two named
repository records not represented by that selection:

| Advisory | Affected range | First patched version reported |
|---|---|---|
| GHSA-2gx3-rcp4-g85q | <=2.13.0 | 2.14.0 |
| GHSA-42vr-xj54-vc7v | >=2.0.0a1, <=2.14.0 | 2.15.0 |
| GHSA-8wjv-2p76-3863 | >=2.13.0, <2.14.0 | 2.14.0 |
| GHSA-9j54-fg26-wv3r | >=2.13.0, <2.14.0 | 2.14.0 |
| GHSA-9v7f-9g4p-ffgj | <=2.13.0 | 2.14.0 |
| GHSA-ffc3-869f-jxw9 | <=2.13.0 | 2.14.0 |
| GHSA-gvp8-978c-rx2q | >=2.11.0, <=2.13.0 | Not supplied by advisory metadata |
| GHSA-hxm8-2xgr-2p9m | <=2.13.0 | 2.14.0 |
| GHSA-jwrc-g2q2-pq5p | <=2.13.0 | 2.14.0 |
| GHSA-p4g4-x82p-q773 | >=2.4.0, <2.14.0 | 2.14.0 |
| GHSA-r6x4-923q-g947 | =2.13.0 | 2.14.0 |
| GHSA-w2cx-738m-mc7w | =2.13.0 | 2.14.0 |
| GHSA-w6j9-cwv2-h6wq | >=2.9.0, <=2.13.0 | 2.14.0 |

No fixed version is invented for GHSA-gvp8-978c-rx2q: 2.15.0 is outside its
published affected range and the candidate's complete PyPI audit reported no
findings. No advisory suppressions were made; the AC2 repair below tightens the
existing validator without changing this dependency graph.

## Reference evidence and runtime proof

The 261-test receipts below describe the initial submitted head
`6c3d0c537248a0fa387c89e57bb63a7b1f964f65`. New-head repair proof is retained
externally as described under AC2 repair, not substituted by those older receipts.

Executed platform: **CPython 3.11.15, Ubuntu 24.04.5, Linux x86_64**, glibc 2.39,
SQLite 3.45.1. Docker Linux/amd64 execution was emulated on an ARM64 host, not
macOS Python output. Ubuntu base digest:
`sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3`.
CPython was copied from the public 3.11.15-bookworm runtime into Ubuntu with
Ubuntu runtime libraries; source runtime digest:
`sha256:a8f8fbe1a0edc9e4dddafa64ba73f7e04be7be5ebc23f332362e779e0a2e4e52`.
This establishes the declared installation platform, not an image assessment.

Existing generators used isolated tools: **pip-audit 2.10.1**, **cyclonedx-bom
7.3.0**, **pip-licenses 5.5.5**, and the generator's **tomli 2.0.1**. The
blocking audit ran from 02:17:59Z to 02:18:12Z; the stored audit finished at
02:18:22Z. Both covered **84/84 exact pins, zero findings**, with strict stored
report validation. SBOM/license regeneration finished at 02:19:11Z. Coherence
validation matched 84 constrained packages across installed inventory, SBOM,
audit and transitive licenses; SBOM/installed totals are 87 including the local
KS distribution and two bootstrap packages. Direct licenses cover seven names.

The full constrained `[all,test]` install passed exact inventory validation,
`pip check` and **261 tests with no skips**. The delivered stdio smoke and
runtime-hardening files separately passed **36 tests with no skips**. These
exercise initialization, all 16 tools, synthetic ingestion and suggestions,
explicit portfolio reuse/evidence, root confinement, redacted errors,
shared-mode requirements and hostile FastMCP settings without a listener.
A supplementary real stdio round-trip proved ingest/search/read/evidence,
deterministic repeated search, project-scoped retrieval and suggestion
evidence. The existing KS L5 isolation helper passed all six checks; this is
not a full Suite L5 run. A separate core-only venv passed `pip check` and proved
all three parser distributions absent with actionable missing-extra errors.

Reproduction uses existing repository entry points:

```bash
# Start from an isolated CPython 3.11 Ubuntu 24.04 x86_64 environment.
python3.11 -m pip install -c constraints.txt -e '.[all,test]'
python3.11 scripts/dependency_audit.py installed --constraints constraints.txt
python3.11 -m pip check
python3.11 -m pytest -v --tb=short
python3.11 scripts/run_ks_l5_isolation.py --pretty
PY=python3.11 scripts/check-dependency-audit.sh
PY=python3.11 scripts/generate-pip-audit-evidence.sh 2026-10-01
PY=python3.11 scripts/generate-dependency-evidence.sh 2026-10-01
```

## Python 3.10 proof

Actual separate platform: **CPython 3.10.21, Debian 12, Linux x86_64** using
`python:3.10-bookworm` at
`sha256:0a06143d04e5207c0561a9803a007af1d3e7941634fd1a7f801079dca3644bf5`.
The first attempt using the reference constraints failed resolution; it is
retained as failed evidence, not skipped success. Per-package metadata showed
two reference pins require Python >=3.11. A separate applicable constraint
input kept all other pins, replacing `aiofile` 3.11.1 with **3.9.0** (Python
>=3.8, <4; satisfies py-key-value-aio >=3.5.0) and `rpds-py` 2026.5.1 with
**0.30.0** (Python >=3.10; satisfies jsonschema >=0.25.0). This did not change
the committed reference lock or narrow package support.

Resolution additionally installed **tomli 2.4.1** for cyclopts/pytest and
**backports-asyncio-runner 1.2.0** for pytest-asyncio, under their Python <3.11
markers. PyJWT's Python <3.11 typing-extensions requirement is satisfied by the
unchanged 4.15.0 pin. The resulting 86-package graph passed exact validation
against its exported pins, `pip check`, imports and **36 actual subprocess
stdio/hardening tests, no skips**. The complete Python 3.10 suite also passed
**261 tests, no skips**, with a supplementary real ingest/search/read/evidence/
suggestion stdio round-trip. Its separate strict audit covered **86/86,
zero findings**, finishing at 2026-10-02T02:22:44Z. It is supplemental supported
runtime proof, not the committed 84-package Ubuntu reference evidence set.
Unconstrained installation remains supported; to reproduce this bounded proof,
use the reference pins with these two replacements and two marker-added pins
as a separate Python 3.10 constraints input for `-e '.[all,test]'`.

## Evidence identities

SHA-256; normalized graph means PEP 503 names, sorted `name==version` lines,
UTF-8, each with a trailing LF. External installed/support receipts are retained
with the draft PR handoff, not committed as self-certifying review output.

| Identity | SHA-256 |
|---|---|
| Normalized reference graph | `a5d37a1803510e804911754309c2e829176f4c0f5321fce20889026019755d12` |
| constraints.txt | `a090908c21348bbd0ee055fe85d2f68b9287b9e83ae66abe4631ed15d5292abc` |
| pip-audit.json | `66bf017d96a6c26acbce5397eaf744b586bc94a06dea39dcdf8c91e4697def5e` |
| sbom.cdx.json | `18a00799ffab8f36f741a688bdab1b7b667637190b8f03e575b4cceedcf64680` |
| dependency-licenses.csv | `4147cde6d9996cf4eb26e353b4e3da9d8ed7d9e7acd7c6acff88157fe34575a3` |
| transitive-dependency-licenses.csv | `e5eeeedeaac20aa794617a665fb5621598871ec2bbd793cbd1aa40716d40e91b` |
| External reference installed inventory | `7f6525759b52565eb2a7a80794423ebbf3fbbee564f218bd517a75c9a57edec6` |
| External Python 3.10 resolved pins | `3a1859bbe4622aab8b777df386645137edb8452792f8ae57e2ce689cf83325ac` |
| External Python 3.10 installed inventory | `85538fbd9aee547abf63c387f69203092bec2e225747eba22c613cfea24f7b87` |
| External Python 3.10 audit JSON | `4e5fbf0c523d6194e500c40ceed81fb4b2bebeaa170e9168fd20930ecde20c83` |

## License flags and exclusions

**No license/ownership acceptance.** `certifi` remains MPL-2.0; the historical
`caio` UNKNOWN flag remains unresolved. The new Linux CPython 3.11 `caio` wheel
declares `License-Expression: Apache-2.0`, so its generated inventory and SBOM
report that metadata rather than fabricating UNKNOWN. The specific artifact,
`caio-0.9.25-cp311-cp311-manylinux_2_34_x86_64.whl`, has SHA-256
`fc220b8533dcf0f238a6b1a4a937f92024c71e7b10b5a2dfc1c73604a25709bc`.
Metadata differences are not legal reconciliation of earlier artifacts. The
[2026-10-03 artifact correction](#artifact-specific-license-correction) below
qualifies the earlier "historical" wording: UNKNOWN is still an open metadata
flag for affected non-reference artifacts, not merely a past concern.

Application audit exclusions remain interpreter/OS/native libraries, local KS,
isolated audit/SBOM/license tooling and bootstrap packages. Reference bootstrap
is pip 24.0 and setuptools 79.0.1 (previous SBOM: 26.0.1 and 82.0.0); wheel is
not installed. These explain the SBOM-only version deltas, not application
security fixes. Python 3.10 uses pip 23.0.1 and setuptools 79.0.1. All other
unexpected installed packages fail validation. No OS/image, all-platform,
cryptographic provenance, license clearance or ongoing advisory claim is made.

## Read-only enforcement handoff

**Observed pre-change main protection snapshot, 2026-10-01 (not an assertion of
later/current settings):** `strict: true`; required `KS test suite` and
`gitleaks secret scan`, each `app_id: 15368` (github-actions). The existing
`Blocking dependency audit` check has that same verified binding but is omitted
from requirements. Repository rulesets returned `[]`. Admin enforcement and
conversation resolution are enabled; force pushes/deletions are disabled;
required human approvals are zero. The snapshot supplies no additional bypass
allowance field, so none is inferred.

**Historical proposed add-only required-status-check update**, not applied by
the builder; later applied state is recorded [below](#applied-enforcement-state):

```json
{
  "strict": true,
  "checks": [
    {"context": "KS test suite", "app_id": 15368},
    {"context": "gitleaks secret scan", "app_id": 15368},
    {"context": "Blocking dependency audit", "app_id": 15368}
  ]
}
```

At snapshot time, the handoff required the coordinator/administrator to verify
exact-head green CI and independent review, re-read concurrent settings, apply
only the authorized narrow add-only update, and retain read-back proving the
expected union and unchanged strictness/bindings/unrelated policies/rulesets.
The snapshot itself claimed no settings mutation, merge, tag, release or risk acceptance.
Engine's M2 completion contract remains proposed, not adopted. Independent
review and exact-head CI are separate from these build receipts.
The separately authorized coordinator action followed those gates; its
application/read-back evidence is in the PR discussion, referenced in the
dated applied-state note below. It was external to the original reviewed commit.

## AC2 repair round 1

Independent review found that exact name/version coverage could pass without
an explicit advisory result. The existing validator now requires list-valued
`vulns` on every resolved entry and rejects any `skip_reason` field, including
entries retaining their version and an empty vulnerability list. Both evidence
and blocking modes reject incomplete results; valid findings can still be
recorded by evidence mode but fail the live blocking control.

Focused deterministic tests cover missing/null/non-list `vulns`, explicit
skipped/unavailable results and ordinary clean output through the validator and
the live wrapper with an exact full inventory. The audit test file expands from
14 to 42 cases. Tool pins, normalized inventory rules and the 84/86-package
reference/support graphs remain unchanged. The original inventory/SBOM/license/
audit hashes above remain valid dated evidence; no blanket regeneration is
needed. New-head full Python 3.11/3.10 runtime proof, strict revalidation of both
stored reports and a fresh existing live gate have separate external receipts.
Prior-head review/check conclusions are not approval of the repaired head.

## Documentation correction addendum - 2026-10-03

Scope: EF-V5-KS-DEPENDENCY-DOCS-CLOSEOUT revision 1, based on the
[full independent review of PR #42](https://github.com/santosh-sh/EdgeForgeKnowledgeServer/pull/42#issuecomment-5964841348)
(published 2026-10-03T02:55:26Z). This addendum corrects documentation, not the
stored 2026-10-01 scan, reference pins, generated reports or #41 boundary policy.
No fresh whole-graph scan or runtime rerun is claimed.

### Advisory source and date correction

The original 26 PyPI records/13 GHSA identities describe that feed observation,
not all advisories already published by the PyJWT repository. Direct lookup of
the two named repository records on **2026-10-03 UTC** confirms:

| Repository advisory | Published / last updated (UTC) | Published affected range | Patched version |
|---|---|---|---|
| [GHSA-x33g-cr3x-6449](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-x33g-cr3x-6449), CVE-2026-102275 | 2026-09-23T19:17:22Z / 2026-09-28T20:44:43Z | >=2.1.0, <=2.14.0 | 2.15.0 |
| [GHSA-pxh4-856f-4h89](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-pxh4-856f-4h89), no CVE identifier returned | 2026-09-11T13:37:17Z / 2026-09-11T13:37:18Z | <=2.13.0 | 2.14.0 |

Both records are published and not withdrawn. Their release updates supersede
older unreleased-fix language retained in their descriptions. The OKP record
independently supports why 2.14.0 was insufficient alongside the already-listed
GHSA-42vr-xj54-vc7v; 2.15.0 is outside both named affected ranges.

The empty-HMAC JWK report GHSA-pxh4 overlaps the already-listed
[GHSA-9j54-fg26-wv3r / CVE-2026-102266](https://github.com/advisories/GHSA-9j54-fg26-wv3r)
(global record published 2026-09-29T23:43:19Z, updated 23:43:20Z; range
>=2.13.0, <2.14.0; fixed 2.14.0). Both describe empty symmetric JWK material
reaching verification; the descriptions identify distinct complementary fixes:
`from_jwk` rejects empty material in `af8181ca0bec5e6b372fbba9afbe23702b787ceb`,
while PyJWK verification invokes `prepare_key` in
`f91ed44dd65baaf457f4b3353ed35e98a753934c`. This is an overlapping/possible
duplicate report, not a demonstrated additional unique vulnerability. Neither
returned identifier list formally aliases the other GHSA. Keep both source
identities/ranges; do not turn 13 plus two records into a unique-vulnerability total.

The current pip-audit/PyPI gate reports its **available advisory feed**, not
every repository advisory immediately. Exact inventory and strict result
validation establish scan completeness for that feed, not exhaustive upstream
coverage. These bounded lookups do not establish current whole-graph clearance
or rewrite what the earlier audit observed.

### Artifact-specific license correction

On **2026-10-03 UTC**, downloads were checked against SHA-256 digests in the
[public caio 0.9.25 per-artifact metadata](https://pypi.org/pypi/caio/0.9.25/json).
These five examples, not every supported Python/platform artifact, were inspected:

| Artifact (all caio 0.9.25) | PyPI upload date (UTC) | METADATA / PKG-INFO license declaration | Artifact SHA-256 |
|---|---|---|---|
| `caio-0.9.25-cp311-cp311-manylinux_2_34_x86_64.whl` (reference) | 2026-03-04 | `License-Expression: Apache-2.0` | `fc220b8533dcf0f238a6b1a4a937f92024c71e7b10b5a2dfc1c73604a25709bc` |
| `caio-0.9.25-cp311-cp311-macosx_10_9_universal2.whl` | 2025-12-26 | No `License` / `License-Expression` or license classifier | `d6956d9e4a27021c8bd6c9677f3a59eb1d820cc32d0343cea7961a03b1371965` |
| `caio-0.9.25-cp311-cp311-manylinux2010_x86_64.manylinux2014_x86_64.manylinux_2_12_x86_64.manylinux_2_17_x86_64.whl` | 2025-12-26 | No `License` / `License-Expression` or license classifier | `bf84bfa039f25ad91f4f52944452a5f6f405e8afab4d445450978cd6241d1478` |
| `caio-0.9.25-py3-none-any.whl` | 2025-12-26 | No `License` / `License-Expression` or license classifier | `06c0bb02d6b929119b1cfbe1ca403c768b2013a369e2db46bfa2a5761cf82e40` |
| `caio-0.9.25.tar.gz` (sdist; not a built-install claim) | 2025-12-26 | No `License` / `License-Expression` or license classifier | `16498e7f81d1d0f5a4c0ad3f2540e65fe25691376e0a5bd367f558067113ed10` |

Each sampled artifact declares `License-File: COPYING` and packages Apache-2.0
COPYING text. The fallback wheel uses CRLF instead of LF; after line-ending
normalization the five texts match. Packaged text, machine-readable license
declaration, scanner-reported UNKNOWN, and adopter/legal acceptance are distinct.
The reference SBOM/CSV truthfully reports its wheel's Apache-2.0 metadata;
it does not describe these other artifacts or resolve their **UNKNOWN** flag.
Keep UNKNOWN open for affected non-reference artifacts and **certifi MPL-2.0**
open for owner/legal review. No all-platform metadata conclusion, source-build
reproduction, license selection or legal acceptance follows from this sample.
Generated reports are unchanged, with this caveat linked from their evidence index.

### Applied enforcement state

The pre-change 2026-10-01 protection snapshot above remains historical evidence.
The authorized add-only change's read-back was **2026-10-02T03:19:06Z** in
[PR #42](https://github.com/santosh-sh/EdgeForgeKnowledgeServer/pull/42);
the [independent review read-back on 2026-10-03](https://github.com/santosh-sh/EdgeForgeKnowledgeServer/pull/42#issuecomment-5964841348)
confirmed required `KS test suite`, `gitleaks secret scan`, and
`Blocking dependency audit`, all `app_id: 15368`, with `strict: true`.
The closeout builder's 2026-10-03 read-only full-protection response reconfirmed
those contexts/bindings/strictness; the coordinator's current full protection
and rulesets read-back also confirmed rulesets `[]`. The builder's separate
rulesets requests returned unavailable/503, not independent confirmation.
No settings change is made or authorized by this documentation closeout.

Enforcement is not coverage or risk clearance: bootstrap packages and isolated
audit/SBOM/license-tool graphs remain excluded from the application baseline.
The prior review identified bootstrap advisory concerns; exclusions do not
dispose of those concerns. Tool versions are pinned, but tool transitives are
not fully pinned/hashed. Engine's broader M2 contract remains proposed;
no Suite M2/publication, image/native-library or licensing acceptance is implied.

### Open owner decisions

No policy is selected and no audit is scheduled by this PR.

| Owner | Remaining decision |
|---|---|
| KS security maintainer | Available-feed lag/coverage and whether critical packages need a second source; audit cadence between PRs remains undecided. |
| KS maintainer / security owner | Handling a future required-gate finding with no upstream fix: accountable exception/disposition authority, mitigation and review trigger. The existing gate stays blocking with no suppression added. |
| KS runtime / CI owner | Recurring Python 3.10 graph/audit coverage versus the existing dated 86-package proof; no new maintained lock/matrix is delivered here. |
| KS build / supply-chain owner | Pinning/hashing isolated tool transitives and assessment/disposition of excluded bootstrap/tool graphs; exclusion is not clearance. |
| Adopter / Suite legal and ownership owners | caio artifact-specific UNKNOWN, certifi MPL-2.0 and definitive KS rights/terms remain unresolved. |
