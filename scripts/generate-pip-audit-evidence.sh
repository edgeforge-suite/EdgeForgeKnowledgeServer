#!/usr/bin/env bash
# Regenerate pip-audit evidence for KS's resolved constraints surface.
#
# The audit is time-sensitive because advisory databases change. This script
# records the tool version, target surface, JSON output, and an honest markdown
# summary under docs/handover-evidence/.
set -euo pipefail

PIP_AUDIT_VERSION="2.10.1"
SNAPSHOT_DATE="${1:-$(date +%F)}"
PY_BIN="${PY:-python3}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="docs/handover-evidence"
WORK="$(mktemp -d)"
TOOLS="$WORK/tools"
trap 'rm -rf "$WORK"' EXIT

if [[ ! -f constraints.txt ]]; then
  echo "constraints.txt is missing; run 'make lock' first" >&2
  exit 2
fi

"$PY_BIN" -m venv "$TOOLS"
"$TOOLS/bin/pip" install --quiet --disable-pip-version-check \
  "pip-audit==${PIP_AUDIT_VERSION}"

set +e
"$TOOLS/bin/pip-audit" -r constraints.txt --no-deps --disable-pip \
  --format json --output "$OUT/pip-audit.json"
AUDIT_STATUS=$?
set -e

if [[ "$AUDIT_STATUS" -gt 1 ]]; then
  echo "pip-audit failed with status $AUDIT_STATUS" >&2
  exit "$AUDIT_STATUS"
fi

# Evidence generation records vulnerability findings, but incomplete inventory
# coverage or version drift is always an error.
"$PY_BIN" scripts/dependency_audit.py validate \
  --constraints constraints.txt \
  --report "$OUT/pip-audit.json" \
  --allow-vulnerabilities

SNAPSHOT_DATE="$SNAPSHOT_DATE" AUDIT_STATUS="$AUDIT_STATUS" \
  "$TOOLS/bin/python" - "$OUT/pip-audit.json" constraints.txt "$OUT/pip-audit.md" <<'PY'
import importlib.metadata
import json
import os
import re
import sys

json_path, constraints_path, md_path = sys.argv[1], sys.argv[2], sys.argv[3]


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_constraints(path: str) -> dict[str, str]:
    packages = {}
    with open(path) as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            line = line.split(";", 1)[0].strip()
            if "==" in line:
                name, version = line.split("==", 1)
            elif ">=" in line:
                name, version = line.split(">=", 1)
            else:
                name, version = re.split(r"[<>=!~]", line, maxsplit=1)[0], ""
            name = name.strip()
            if name:
                packages[norm(name)] = f"{name}=={version.strip()}" if version else name
    return packages


with open(json_path) as f:
    data = json.load(f)

dependencies = data.get("dependencies", [])
constraint_packages = parse_constraints(constraints_path)
audited_names = {norm(dep.get("name", "")) for dep in dependencies if dep.get("name")}
omitted = [
    constraint_packages[name]
    for name in sorted(set(constraint_packages) - audited_names)
]
vulnerabilities = []
seen_vulnerabilities = set()
for dep in dependencies:
    for vuln in dep.get("vulns", []):
        key = (norm(dep.get("name", "")), dep.get("version", ""), vuln.get("id", ""))
        if key in seen_vulnerabilities:
            continue
        seen_vulnerabilities.add(key)
        vulnerabilities.append((dep, vuln))

tool_version = importlib.metadata.version("pip-audit")
status = os.environ["AUDIT_STATUS"]
if vulnerabilities:
    summary = (
        f"**Vulnerabilities reported:** {len(vulnerabilities)} finding(s). "
        "Review before import and rerun against the adopter's approved mirror."
    )
else:
    summary = (
        "**No known vulnerabilities reported** for packages included in the "
        "`pip-audit` JSON output at scan time."
    )

if omitted:
    coverage = (
        f"`pip-audit` reported {len(dependencies)} package(s) from "
        f"{len(constraint_packages)} entries in `constraints.txt`. "
        "The following constraint entry/entries were not present in the JSON "
        f"output and require adopter review or rerun: {', '.join(f'`{item}`' for item in omitted)}."
    )
else:
    coverage = (
        f"`pip-audit` reported all {len(constraint_packages)} package(s) from "
        "`constraints.txt` in the JSON output."
    )

rows = []
for dep, vuln in vulnerabilities:
    aliases = ", ".join(vuln.get("aliases") or [])
    rows.append(
        "| `{name}` | {version} | {vuln_id} | {aliases} | {fix_versions} |".format(
            name=dep.get("name", ""),
            version=dep.get("version", ""),
            vuln_id=vuln.get("id", ""),
            aliases=aliases or "-",
            fix_versions=", ".join(vuln.get("fix_versions") or []) or "-",
        )
    )

table = (
    "| Package | Version | Vulnerability | Aliases | Fix versions |\n"
    "|---|---|---|---|---|\n"
    + "\n".join(rows)
    + ("\n" if rows else "| _none_ | - | - | - | - |\n")
)

md = f"""# pip-audit Evidence — EdgeForge Knowledge Server

> **Import-gate P1 evidence.** pip-audit report for the KS resolved
> [`constraints.txt`](../../constraints.txt) dependency set, with coverage
> checked against the committed constraints file.
>
> **Generated:** {os.environ['SNAPSHOT_DATE']}, with **pip-audit {tool_version}**.
> Raw JSON: [`pip-audit.json`](pip-audit.json).
> **Reference baseline:** CPython 3.11 on Ubuntu 24.04 x86_64. The scanner checks
> every exact package version in `constraints.txt` without resolving a second
> dependency graph.

## Honest status

{summary}

## Coverage

{coverage}

`pip-audit` exit status for this run: `{status}`.

This result is time-sensitive and advisory-database dependent. Regenerate it in
the adopting organization's approved package mirror before import.

## Findings

{table}
"""
with open(md_path, "w") as f:
    f.write(md.rstrip() + "\n")
print(
    f"wrote pip-audit evidence; vulnerabilities: {len(vulnerabilities)}; "
    f"omitted constraints: {len(omitted)}"
)
PY

echo "pip-audit evidence regenerated under $OUT/"
