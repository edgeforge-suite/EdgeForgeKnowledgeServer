# Purge Atomic-Intent Verification — 2026-10-10

Bounded correction: **EF-V5-KS-PURGE-ATOMIC-INTENT revision 1**.
Base: `c338d557c5cccaeb8336119cab6368ace3f95d63` (merged PR #45).
The correction PR records the final head, CI and independent review; this is
not publication acceptance or a refresh of dependency/security scan evidence.
The [dated PR #45 record](fts5-purge-verification-2026-10-10.md) is unchanged.

## Baseline And Fixed Proof

An export of the exact base ran the same task-owned child synchronization:
active and soft-deleted purges were killed after logical deletion committed,
before maintenance. Reopening found missing document rows, no pending intent,
positively detected indexed suffix residue and a failed same-ID retry.

`tests/test_tools/test_purge_atomic_intent.py` adds 24 cases. Ten kill real child
processes after a ready handshake, not a timed sleep, at maintenance entry,
FTS optimize/checkpoint/VACUUM SQL-entry callbacks and before the final
intent-removal commit. The callbacks/proxy exist only in the test child;
production has no interruption hooks. Committed intent survives reopen for
active/soft-deleted inputs; confirmed same-ID retry removes it only after
cleanup. Other cases test SQL-trigger and simulated commit rollback, pending
update/removal failures, transaction ordering, binding and multiple intents.

The remanence control first positively detects a distinctive indexed suffix
while the full term is absent from prefix-compressed index bytes. Successful
retry removes the suffix from all FTS shadow tables and live DB/WAL/SHM bytes.
Retained search/evidence, accepted decisions, source-file bytes, SQLite/FTS
integrity and FTS format 4 survive reopen; persistent secure-delete is absent.
PR #45's multiple-segment, reader-contention and maintenance-failure proofs
also remain in the focused suite.

## Measured Environments And Commands

Cached images were reused; new task-owned containers and clean virtual
environments were created, not newly rebuilt images. Both installs used
`.[all,test]`, the unchanged reference constraints or its existing documented
[Python 3.10-compatible input](dependency-closure-2026-10-01.md#python-310-proof).

| Environment | Actual Python / loaded SQLite | Dependency input |
|---|---|---|
| Ubuntu 24.04.5 x86_64 task-local reference image | 3.11.15 / 3.45.1 | `constraints.txt` |
| Debian 12 x86_64 `python:3.10-bookworm` | 3.10.21 / 3.40.1 | Separate documented 3.10 constraints |
| macOS host, storage-focused supplemental proof | 3.11.15 / 3.52.0 | Existing host environment; not reference MCP acceptance |

Reference image identity and its Python/system-SQLite link are described in
the [PR #45 receipt](fts5-purge-verification-2026-10-10.md#identity-and-actual-runtime).
The runtime probe was repeated inside each new verification environment:

```bash
python -c 'import sys, sqlite3; print(sys.version); print(sqlite3.sqlite_version)'
python -m pip install --constraint constraints.txt -e '.[all,test]'
python -m pip check
python -m pytest tests/test_tools/test_purge_atomic_intent.py tests/test_tools/test_ks_hard_purge.py tests/test_server/test_mcp_server.py tests/test_server/test_stdio_smoke.py tests/test_server/test_runtime_hardening.py -q
python -m pytest tests/ -q
```

Execute in a disposable checkout with that environment's venv Python; substitute
the documented separate constraints file for Python 3.10. The full suite is
required in the reference environment; Python 3.10 proof is focused.

Observed builder results: reference **321 full / 87 focused passed**; Python
3.10 **87 focused passed**; host supplemental storage **40 passed**. Both clean
container installs reported `No broken requirements found`. Ruff, diff hygiene
and **145 local links/anchors** passed. Exact-head CI and independent review
are recorded on the correction PR, separately from these local runs.
In-process and real stdio `tools/list` verify the revised wording; the existing
stdio confirmation/purge round-trip and 16-tool surface remain covered.

## Limits

No power-loss, disk-full, physical-media or universal crash-recovery proof.
SQL-entry callbacks synchronize at statement entry, not arbitrary internal
SQLite instructions; injected exceptions are not described as process kills.
No new Windows execution, platform matrix, cross-version database transfer,
live local advisory scan, dependency evidence regeneration or Suite L5.
Historical purges without intent do not acquire retroactive same-ID recovery.
No real stores or operator corpora were used. See the
[current correction and remaining limits](../publication-preparation.md#atomic-cleanup-intent-correction--2026-10-10).

## Pending-Record Follow-Up — 2026-10-11

The [independent review](https://github.com/santosh-sh/EdgeForgeKnowledgeServer/pull/46#issuecomment-6105197320)
identified ID/timestamp residue after successful intent removal at `b3f0f983`.
Before the follow-up fix, all 14 initial added regressions failed on that head:
12 byte-removal cases and two final-checkpoint failure controls. The original
dated proof and counts above have not been restamped.

The follow-up adds 16 cases: active/soft-deleted initial purges and pending
retries with core `secure_delete` OFF, ON and FAST; real reader obstruction;
injected checkpoint and intent-restoration failures; and re-ingest while pending.
The byte controls positively detect ID and both timestamps in the main file
immediately before removal, then require absence from live DB/WAL/SHM while the
store is open and after close. They verify retained evidence/accepted decisions,
source files, integrity, FTS format 4 and connection-setting restoration.
The combined host storage suites pass **56 tests** on Python 3.11.15 / SQLite
3.52.0. Reference/older-SQLite reruns, exact head, CI and independent review are
recorded separately on PR #46; the commands and dependency inputs above apply.

Finalization uses core SQLite zeroing only for intent removal, followed by a
checked bounded checkpoint; it does not set FTS5 secure-delete. A handled final
checkpoint failure restores committed retry state or explicitly reports failed
restoration. A process stop after intent removal commits but before checkpoint
or restoration can leave ID/time residue without same-ID retry state. The
document-content scrub has already finished; no universal crash guarantee or
risk acceptance is implied. Pending-record contents and re-ingest retention
are disclosed in the [current correction](../publication-preparation.md#pending-record-privacy-correction--2026-10-11).
