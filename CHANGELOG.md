# Changelog

All notable Knowledge Server baseline changes are tracked here. KS follows the
EdgeForge suite version when it participates in a suite baseline.

## Versioning Scheme

- KS package and standalone tags align to the suite baseline they carry.
- The planned first standalone KS baseline was originally discussed as
  `v1.0.0`, but enterprise-handover alignment moved the first tagged standalone
  baseline to `v4.0.0` so KS, Studio, and Engine version posture stayed coherent.
- Patch-level and feature branches still use normal PR titles (`[FIX]`,
  `[FEATURE]`, `[DOCS]`, `[CHORE]`); releases collect those merged changes into
  suite-aligned tags.

## 5.0.0 — Source Changes

- Set package and runtime versions to 5.0.0 in the
  `edgeforge-suite/EdgeForgeKnowledgeServer` repository. This section collects
  source changes, not a release date or proof that a tag or Release is published.
  Successor selected-source execution and justified reuse are recorded in the
  [November 14 results](https://github.com/edgeforge-suite/EdgeForge/blob/e33869e6ba595e280a4631dbf11e451fb33fe2a6/docs/handover-evidence/v5-dependency-acceptance-2026-11-14.md).
  Later independent approval is recorded separately.
  Dependencies, the 16-tool contract and storage behavior are
  unchanged by this version/documentation closeout.

- Clarify independent community maintenance and optional self-managed enterprise
  adoption; use neutral publication-authorization wording in preparation
  guidance. Publication prerequisites, license terms and dated proof results
  remain unchanged.

- Correct only joserfc 1.7.1 -> 1.7.6 in the 84-package reference graph;
  qualify the early compact-JWS size guard, retain the other 83 pins and
  refresh current dependency evidence. See the
  [November 2 receipt](docs/handover-evidence/joserfc-correction-2026-11-02.md).
- Correct the reference Authlib 1.7.2 -> 1.9.1 and dnspython 2.8.0 -> 2.9.0
  pins for the eight findings blocking PR #49. Other 82 pins and supported
  behavior remain unchanged; refresh current audit/SBOM/license evidence.
  See the [dated correction receipt](docs/handover-evidence/audit-correction-2026-10-28.md).
- Raise the v5 minimum Python from 3.10 to 3.11 under the approved revision 2
  amendment, preserving PDF support with Pillow 13. Historical Python 3.10
  evidence remains dated; the SQLite support floor is unchanged.
- Pin FastMCP/slim 3.4.11, certifi 2026.10.23, OTel API 1.45.1 and Pillow
  13.0.0; preserve MCP 1.30.0 and other reference pins. Sanitize the new FastMCP
  validation wrapper to preserve the existing non-disclosing error contract.
- Apply Apache-2.0 SPDX metadata, LICENSE/NOTICE, copyright Santosh Hommaradi
  and DCO 1.1 sign-off guidance (no CLA). Select the edgeforge-suite destination,
  GitHub PVR and security@edgeforgesuite.com; verify route operation and obtain
  maintainer publication authorization before exposure.
- Earlier dependency and packaging checks remain dated evidence, not final v5
  acceptance. See the [October 25 preparation proof](docs/handover-evidence/v5-source-preparation.md).

### Earlier MCP Dependency Correction — 2026-10-15

- Updates the reference MCP SDK constraint from 1.28.1 to 1.30.0 for
  GHSA-84m7-p3x7-pcfv; FastMCP and FastMCP-slim remain at 3.4.2 and the other
  83 application pins are unchanged. The advisory excludes stdio-only servers;
  KS continues to force local stdio, with no transport or tool contract change.
- Refreshes dated reference dependency evidence and separately verifies the
  documented Python 3.10 graph. See the
  [2026-10-15 verification record](docs/handover-evidence/mcp-correction-2026-10-15.md).

## v4.1.0 — Handover Consistency Baseline

- Refreshes docs/messaging for the suite `v4.1.0` posture.
- Adds packaging metadata, a console script entry point, docs navigation, Ruff
  baseline config, and suite-style developer targets.
- Keeps KS runtime behavior and MCP tool contracts unchanged.

## v4.0.0 — First Standalone KS Baseline

- Marks the first standalone KS baseline aligned to the EdgeForge suite
  enterprise-readiness handoff.
- Includes the 16-tool local stdio MCP surface, including hard purge and
  suggestion decision write-back.
- Includes deterministic broader suggestion scopes: fields, validations, rules,
  cross-entity rules, mappings, transforms, conflict resolution, portfolio reuse,
  and identity role.
- Includes stable suggestion IDs, persisted review status, stale suggestion
  invalidation on reingest/delete, Oracle DDL ingest hardening, parser resource
  guards, and handover evidence artifacts.
