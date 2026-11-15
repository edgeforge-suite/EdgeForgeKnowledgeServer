# KS Publication Preparation

## Current v5 Publication Guidance

Authority: maintainer-approved **EF-V5-RELEASE-SCOPE-RESET revision 3** and
**EF-V5-RELEASE-PREP-KS-S1 revision 2** for the current version/documentation
closeout. Earlier **EF-V5-SOURCE-PREP-KS-S1 revision 2** proof remains dated.
This is the
`edgeforge-suite/EdgeForgeKnowledgeServer` repository. These authorities
supersede conflicting older gates.
The selected successor sources, execution and justified reuse are recorded in
the [November 14 results](https://github.com/edgeforge-suite/EdgeForge/blob/e33869e6ba595e280a4631dbf11e451fb33fe2a6/docs/handover-evidence/v5-dependency-acceptance-2026-11-14.md)
and [pairing guide](https://github.com/edgeforge-suite/EdgeForge/blob/e33869e6ba595e280a4631dbf11e451fb33fe2a6/docs/suite-release-pairing.md).
Later independent approval is recorded separately. The
[November 10 results](https://github.com/edgeforge-suite/EdgeForge/blob/92d0de224d127525b3b3db1365cf931188ccfffb/docs/handover-evidence/v5-acceptance-2026-11-10.md)
retain the preceding selection's scope.
Maintainer publication authorization is required before public exposure;
technical acceptance does not grant it. Source repositories/tags are the
selected distribution; website hosting is separate. No package/image publishing
is selected here. Python 3.11 is the v5 minimum; SQLite compatibility is unchanged.

The [project-intent statement](../README.md#project-intent-and-community) applies
to this preparation. The maintainer's choice not to monetize adds no restriction
to Apache-2.0 or commercial use by adopters and does not grant publication
authority.

**Wording clarification (2026-11-05):** the public gate is described as
maintainer publication authorization. Applicable rights and permissions must
still be verified before exposure; supporting non-public records stay private.
This editorial change grants no clearance and does not change dated proof.

Apache-2.0, short NOTICE, copyright Santosh Hommaradi, DCO 1.1/no CLA and the
destination `edgeforge-suite/EdgeForgeKnowledgeServer` are settled.
GitHub PVR is the selected primary reporting route and
`security@edgeforgesuite.com` the selected email route. PVR enablement at public
cutover and email delivery/reply tests before exposure are operator requirements,
not operation established by this guidance.
See [SECURITY](../SECURITY.md) and the [dated October 25 proof](handover-evidence/v5-source-preparation.md).

References to pre-v5 commits, pull requests, issues and workflow runs point to the private development archive and may be inaccessible to public readers.

## Historical October 8 Preparation Context

The original decision-independent slice below is dated history. Its former
license, destination, reporting-selection and Python-floor gates are superseded
by the current authority above; its observations and later purge findings remain.

**Preparation slice:** EF-V5-KS-PUBLICATION-PREP-S1, revision 1, 2026-10-08.
This is decision-independent contributor/documentation preparation, not approval
to publish KS, select a release, accept risk or grant contribution rights.
The intended initial distribution is source repositories and tags; official
packages, binaries and images are not selected for publication by this plan.
Website hosting is a separate Suite responsibility.

Suite authority is the Engine repository's `docs/external-review-backlog.md`
at `64f51d0bac92b4c70f26c8f5f067888717df7b14`: E1/XR-2,
RP-EVIDENCE-PURPOSE and XR-5. KS source reviewed for this slice is
`543a9785752ac0c0c285913fffdd6d82c1b6328b`. These are observation pins, not a
release tuple. Engine and Studio work may proceed independently.

## Remaining Maintainer Decisions

| Decision | Owner | Evidence needed before public release |
|---|---|---|
| Maintainer publication authorization | Maintainer | Verify applicable rights and permissions before authorizing public exposure; keep supporting non-public records private. Apache-2.0, copyright, NOTICE and DCO 1.1/no CLA are selected and applied; no new license choice is pending. |
| Reporting-route operation | Maintainer / security owner | Verify security@edgeforgesuite.com delivery and replies before public exposure; confirm accountable handling and actual reply identity. Enable and verify GitHub PVR at public cutover, including an appropriate non-admin reporter check before Release publication/announcement. Selection is not availability and no SLA is invented. |
| Distribution-specific third-party obligations | Maintainer / distribution owner | Source release does not bundle dependency wheels. Preserve dependency notices and artifact-specific evidence; review obligations separately if publishing third-party binaries or bundles. No legal-risk acceptance is made here. |
| Final release metadata and public cutover | Suite release owner / KS maintainer | Preserve the accepted successor E/S/K selection and P/R records identified by the November 14 results links above. Obtain approval of the actual refreshed main trees and associated PR/Actions material before exposure. Tags, Release publication and visibility changes require their separate authorizations; documentation successors are not replacement tag targets. |

These are public-project responsibilities. Enterprise adopters separately own
their local import approval, package mirrors, host security, corpus policy and
internal support. Operating deployments and handling confidential adopter data
are not maintainer services offered by this project.
Neither an adopter's later assessment nor green preparation CI closes the
project's publication gates. Final audit freshness and the existing
[dependency owner decisions](handover-evidence/dependency-closure-2026-10-01.md#open-owner-decisions)
remain with release/security owners; no new audit schedule is established here.

## Contributor Entry Points

Read [CONTRIBUTING](../CONTRIBUTING.md), use the repository's
[bug](../.github/ISSUE_TEMPLATE/bug_report.md) or
[feature](../.github/ISSUE_TEMPLATE/feature_request.md) template for non-security
reports, and use the [PR template](../.github/pull_request_template.md) for scoped
changes. Submit synthetic reproductions and manually redacted diagnostics only.
Follow [SECURITY](../SECURITY.md) for PVR when available, the designated security
email and how to request a private channel if neither route is available.

The issue chooser links this repository's security policy. Use ordinary issue
templates for non-security work when you have repository access.
Blank issues remain available; guidance is not technical disclosure prevention.

## Starter Issue Drafts

**Unpublished, not assignments or recruitment.** No existing KS issues were
returned by the issue inventory on 2026-10-08. The drafts below reuse existing
backlog work rather than creating new release requirements. A maintainer must
confirm prerequisites, scope and ownership before publishing or assigning one;
public contribution terms must be settled before inviting contributions.

### Draft 1: Establish A Blocking Lint Baseline After v5

- **Owner:** KS developer-tooling maintainer; contributor implements a separately
  approved slice, independent reviewer verifies it.
- **Backlog:** Engine `docs/external-review-backlog.md`, XR-3 (post-v5, not a
  publication-preparation gate).
- **Prerequisites:** v5 released; maintainer approves the exact checker/version,
  existing-rule baseline and treatment of residual findings. Any required-check
  settings change needs separate explicit admin authorization.
- **Scope:** resolve the agreed existing findings with behavior-preserving edits
  and make the selected lint job fail on violations once the baseline is clean.
- **Exclusions:** new rule families, mass formatting, incremental typing,
  dependency upgrades and unapproved repository-setting changes.
- **Completion:** the pinned checker passes on the candidate; a controlled
  deliberate violation makes the CI job fail; regression tests remain green;
  review confirms no runtime changes. Record required-check enforcement if
  separately authorized, or explicitly leave it pending rather than calling an
  unrequired job merge-blocking.

### Historical Draft 2: Python 3.10 Recurring Proof

The October 8 draft is retired by the approved v5 Python 3.11 amendment.
The [dated 3.10 evidence](handover-evidence/mcp-correction-2026-10-15.md#python-310-proof)
is preserved, not rerun or claimed as current support. Any nonblocking future
work from this slice is listed once in its PR, not automatically assigned here.

## Bounded Review And Release Handoff

The retained September 23 publication audit is dated evidence. This slice
reviews current public-facing guidance and changes from audited main
`893fba4783e4bdaa6cde2efbc2176e886c257880` to the October 8 observation above.
Delivered cross-project/evidence corrections (#41), dependency closure and audit
enforcement (#42), and documentation corrections (#43) are reused, not reopened.
No new history scan or live advisory campaign is claimed by this prose review.
Private reports and raw logs are not publication artifacts.

Templates and guidance now expose the pending reporting route, data-submission
rules and maintainer decisions; the evidence index explains audience, identity,
scope and refresh triggers. Documentation validation and CI results belong to
the PR's reviewed commit. They are not fresh runtime or release acceptance.

Next order: **maintainer decisions, separately authorized application of those
decisions, final release reconciliation, then revalidation of selected refs**.
Final content/history and disclosure checks remain part of release selection;
this bounded review does not certify every reachable historical object for
publication. No issues, tags, releases or repository settings are changed here.

## Open FTS5 Purge Follow-Up

**Historical finding, confirmed 2026-10-08; open at that observation.** The
[independent PR #44 review](https://github.com/santosh-sh/EdgeForgeKnowledgeServer/pull/44#issuecomment-6069280840)
demonstrated that a successful `purge_document` can remove content rows while
deleted document terms remain in FTS5 index segments and the SQLite file. A
separate synthetic probe of the actual KS purge path reproduced this on SQLite
3.52.0. This is storage remanence, even though normal retrieval no longer returns
the purged document. Checkpoint/VACUUM completion is not physical-erasure proof;
ordinary FTS5 deletion can leave terms until index segments merge.

**Original disposition (PR #44):** KS storage/security maintainer; the release owner must track its
disposition. This documentation repair discloses the limitation; it does not fix
the runtime, accept risk or decide that the defect can be deferred past release.
Do not rely on the current success result as a physical-erasure guarantee.

**Original required separate fix and verification:** address retained FTS5 terms as well
as content rows, preserving unrelated active documents and existing scrub-retry
behavior. Evaluate FTS5 secure deletion where supported and segment compaction
for older supported SQLite versions; do not silently narrow Python 3.10+ support.
Regression proof must inspect tokenized terms in `document_chunks_data` and the
database/WAL bytes, not only the original untokenized sentinel. Include active
and soft-deleted inputs, unrelated retained documents, reader contention/retry
and the relevant SQLite versions. The precise implementation belongs in a
separately authorized runtime PR; the two starter drafts above remain unchanged.

### Correction And Verification — 2026-10-09

The authorized FTS5 purge correction compacts the **whole** `document_chunks`
index using FTS5 `optimize`, commits that maintenance, then performs the existing
checkpoint/VACUUM/checkpoint sequence. This merges deleted entries out before
reclaiming pages and truncating WAL. It does **not** enable persistent FTS5
`secure-delete`, change tokenization, rebuild the database or raise the runtime
floor. SQLite documents both [whole-index optimize](https://www.sqlite.org/fts5.html#the_optimize_command)
and the [pre-3.42 compatibility hazard of secure-delete](https://www.sqlite.org/fts5.html#the_secure_delete_configuration_option).

Synthetic active/soft-deleted, multiple-segment regressions detect exclusive
indexed terms before purge and verify their absence from FTS shadow data and
live database/WAL bytes afterward. They failed against `d9443fa` before the
correction. Tests preserve unrelated project search/evidence and accepted
decisions, source files, project/document binding and dependent review cleanup.
Injected compaction/checkpoint/VACUUM failures and reader contention report
non-success, restore connection settings and retain pending retry state across
reopening. Retry uses the same `purge_document` IDs and explicit confirmation;
it reruns compaction as well as storage cleanup.

Actual verification environments (not version mocks):

| Environment | Python | SQLite |
|---|---|---|
| macOS | 3.11.15 | 3.52.0 |
| Ubuntu 24.04 x86_64 reference constrained install | 3.11.15 | 3.45.1 |
| Debian 12 x86_64, documented separate Python 3.10 constraints | 3.10.21 | 3.40.1 |

Baseline-populated synthetic databases were purged with newer SQLite and
reopened/searched with SQLite 3.40.1; integrity checks passed and FTS format
version remained 4. The 3.10 input is the existing
[compatible dependency proof input](handover-evidence/dependency-closure-2026-10-01.md#python-310-proof),
not an unchanged reference lock or new platform matrix. Exact-head test/CI and
independent-review results belong to the correction PR, not the dated #44 finding.

**Earlier purge residue:** a subsequent successful confirmed purge of an
existing document (or a pending scrub retry) compacts the entire index, so it
also removes older deleted index entries in that same live store. Verified with
residue produced by the actual baseline implementation, including cross-version
reopen. This does not happen automatically at startup. A previously successful
purge with no pending record still returns not found if retried for its absent
document; it does not initiate maintenance. No new global cleanup API is added.

**Cost and limits:** whole-index compaction and VACUUM can take substantial time,
I/O, temporary disk space and a write lock; lock waits/retries remain bounded,
not total maintenance duration. Run with adequate space and competing readers
closed. This is cleanup of controlled live SQLite/index/WAL storage, not secure
erasure of backups, filesystem snapshots, storage-device remnants, external
copies or processes that already read the content. Source files stay
operator-owned. Human merge and final selected-ref Suite acceptance remain
separate; this record grants neither publication approval nor risk acceptance.

### Review Follow-up — 2026-10-10

This is the dated PR #45 observation. The atomic-intent correction below
supersedes its current-behavior caveat without rewriting the finding.

**Interruption disclosure (inherited behavior):** on an initial purge, process
interruption after logical deletion commits but before pending state is saved
can leave indexed/storage residue without a pending record. Nothing can be
reported by a terminated process; a same-ID retry then returns not found. A
subsequent successful purge of another document, or an existing pending retry,
in the same store performs whole-index/storage cleanup and removes that residue.
This is distinct from the handled maintenance failures verified above.

**Separate pre-release follow-up:** record pending cleanup intent atomically
with logical deletion and clear it only after successful maintenance. Verify
interruption, reopen and same-ID retry without changing project binding. This
storage change is not part of the FTS correction; disclosure does not accept its
residual risk or close publication readiness.

The strengthened regression checks a distinctive suffix in prefix-compressed
FTS index data, not only contiguous full-term bytes. The
[runtime verification receipt](handover-evidence/fts5-purge-verification-2026-10-10.md)
identifies the actual Python/SQLite environments and reference image used;
plain `ubuntu:24.04` does not itself supply the recorded Python runtime.

### Atomic Cleanup Intent Correction — 2026-10-10

Starting from PR #45's merge, `c338d557c5cccaeb8336119cab6368ace3f95d63`,
the purge now writes cleanup intent in the **same transaction** as dependent
suggestion/review cleanup and document/chunk/catalog deletion. Its private
intent write does not own or commit a transaction. Either all those effects
commit or all roll back. Maintenance begins only after that commit.

Committed intent remains through FTS compaction and checkpoint/VACUUM/checkpoint.
It is removed in a committed transaction only after cleanup succeeds. Handled
maintenance errors or final intent-update failures report non-success; the
committed intent remains retryable. No schema, dependency, tokenizer, runtime
floor or public tool contract change is required.

Real child processes were synchronized at maintenance entry, FTS optimize,
checkpoint, VACUUM and immediately before intent-removal commit, then killed.
For active and soft-deleted documents, reopening retains committed intent and
confirmed same-project/same-document retry completes cleanup. Rollback controls
cover intent-write, late-deletion and commit failures, including dependent
review state. Prefix-compressed suffix detection, retained project retrieval,
accepted decisions, source files, integrity and FTS format 4 remain covered.
See the [atomic-intent verification receipt](handover-evidence/purge-atomic-intent-verification-2026-10-10.md)
for measured environments, commands and limits; exact-head CI and independent
review belong to the correction PR.

**Remaining limits:** these are tested process-termination and injected-error
scenarios, not power-loss, disk-full, device erasure or universal crash-recovery
proof. Source files, backups, snapshots and prior-reader copies remain outside
cleanup. Whole-index maintenance cost remains as described above. No startup
cleanup or global API is added. Historical successful/interrupted purges that
already lost document rows without pending intent do **not** gain same-ID
recovery: they still return not found. A later successful purge of another
document or existing pending retry can clean earlier residue in that store.
This correction closes the bounded interruption-window work, not publication
readiness, human merge or final selected-revision Suite acceptance.

### Pending-Record Privacy Correction — 2026-10-11

The [independent PR #46 review](https://github.com/santosh-sh/EdgeForgeKnowledgeServer/pull/46#issuecomment-6105197320)
found that the post-scrub intent deletion left its ID/timestamp bytes in live
SQLite storage at reviewed head `b3f0f983a40485e08f70a1b84871e8a49a7cb167`.
That dated finding and the original interruption proofs above remain intact.

Final intent removal now temporarily enables **core SQLite** `secure_delete`,
commits deletion and checks a bounded final WAL-truncation checkpoint before
success. Both connection settings are restored, including `secure_delete=FAST`.
This is not FTS5's persistent secure-delete option and does not change FTS format
4 or the supported SQLite floor. Handled final-checkpoint failures report
non-success and restore a committed same-ID intent. If restoration also fails,
the result explicitly disclaims verified retry availability.

An outstanding intent retains project/document IDs, creation/update times and
any cleanup warning until successful retry. Re-ingesting the same file preserves
it until the next confirmed purge. There is no startup reconciliation. A
process stop **after intent removal commits but before the final checkpoint or
restoration commits** can leave ID/time residue without same-ID retry state;
document content/index cleanup has already succeeded by that stage. This narrow
metadata-finalization window is not an extension of the tested pre-removal
interruption guarantee. No power-loss or universal crash-recovery claim is made.

The [verification receipt](handover-evidence/purge-atomic-intent-verification-2026-10-10.md#pending-record-follow-up--2026-10-11)
records the follow-up proof separately from the original dated runs.
