# FTS5 Purge Runtime Verification — 2026-10-10

This is a bounded synthetic-storage verification receipt for PR #45, not a
release acceptance, live dependency audit or new supported-platform matrix.
The [correction record](../publication-preparation.md#open-fts5-purge-follow-up)
preserves the original finding and the separate pre-release interruption fix.

## Identity And Actual Runtime

The correction starts at `d9443fa79d2326aa17985a9cff9968fe112beccd`.
The original reviewed correction is `dd6411b4f75eae0064d311fd6d374fa642cfd1ee`;
this receipt records its review follow-up. The final repair head and required
CI/review evidence are recorded on
[PR #45](https://github.com/santosh-sh/EdgeForgeKnowledgeServer/pull/45).

| Verification environment | Actual Python | Actual linked SQLite | Scope |
|---|---|---|---|
| Ubuntu 24.04.5 LTS, x86_64, task-owned reference image | 3.11.15 | 3.45.1 | Clean reference-constrained install, `pip check`, focused and full tests |
| Debian 12, x86_64, `python:3.10-bookworm` | 3.10.21 | 3.40.1 | Clean documented alternate-constraints install, `pip check`, focused tests |
| macOS host | 3.11.15 | 3.52.0 | Focused and full tests |

The reference image is **`ks-dependency-closure-reference:20261001`**, local
image ID `sha256:04909be333fbbe7f9d1751bbf34e59764890e02dcc7b5c2d9ec84b565758b90b`.
It is a task-local verification image, not a shipped KS container or publicly
pullable artifact. **Plain `ubuntu:24.04` has no Python installed.**
Image history records Ubuntu runtime libraries plus a copied `/usr/local`
Python installation and `LD_LIBRARY_PATH=/usr/local/lib`. A fresh runtime probe
inside that image returned:

```text
PRETTY_NAME="Ubuntu 24.04.5 LTS"
x86_64
3.11.15 (main, Aug  5 2026, 03:58:57) [GCC 12.2.0]
3.45.1
libsqlite3.so.0 => /lib/x86_64-linux-gnu/libsqlite3.so.0
```

The version above is from **Python's loaded SQLite library**, not the `sqlite3`
CLI, a version mock, or an inference from an OS name. `ldd` on Python's
`_sqlite3` extension confirmed the system library link. The original 2026-10-09
reference run used this same image, not the unmodified Ubuntu image.

## Reproduction And Results

Run this probe in the selected environment before installing/testing; record
its output alongside results. Substitute the environment's Python executable:

```bash
python -c 'import sys, sqlite3; print(sys.version); print(sqlite3.sqlite_version)'
python -m venv /tmp/ks-purge-proof-venv
/tmp/ks-purge-proof-venv/bin/python -m pip install --constraint constraints.txt -e '.[all,test]'
/tmp/ks-purge-proof-venv/bin/python -m pip check
/tmp/ks-purge-proof-venv/bin/python -m pytest tests/test_tools/test_ks_hard_purge.py tests/test_server/test_mcp_server.py tests/test_server/test_stdio_smoke.py tests/test_server/test_runtime_hardening.py -q
/tmp/ks-purge-proof-venv/bin/python -m pytest tests/ -q
```

Use a disposable checkout and unique temporary venv. Installation can access
package sources; no live advisory query was made for this receipt. For Python
3.10, replace the constraints argument with the
[documented compatible input](dependency-closure-2026-10-01.md#python-310-proof),
not the unchanged reference constraints. The reference `constraints.txt`
SHA-256 is `a090908c21348bbd0ee055fe85d2f68b9287b9e83ae66abe4631ed15d5292abc`.

The strengthened active/soft-deleted regression first proves that an erased
term is searchable even though its full bytes are absent from the compacted
FTS index block. Its distinctive suffix is positively detected there before
purge, then checked absent from all FTS shadow data and live database/WAL/SHM
files afterward. Retained-term retrieval and integrity survive reopen. The
test file SHA-256 is
`624bafc86d60356b357f60cc30ce9cce050518b02daf1da7706bfbfa0b1e3319`.

Observed follow-up results: reference environment **63 focused / 297 full
passed**; Python 3.10 environment **63 focused passed**; host **297 full passed**.
Both clean container installations reported `No broken requirements found`.
The two new prefix-compression cases fail against the starting implementation
at the retained-suffix assertion after a successful purge, then pass with the
correction. Real stdio `tools/list` exposes the interruption disclosure and
retains the 16-tool surface and existing purge schema.

Results are tied to the repair head on PR #45; required CI does not establish
an unprinted SQLite version. The actual-runtime probe above supplies that
identity separately. No Windows, power-loss, disk-full or storage-device
erasure proof is claimed. The task-local image ID identifies the measured
environment but is not a distributable or bit-reproducible image recipe.
