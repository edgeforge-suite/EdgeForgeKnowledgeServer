#!/usr/bin/env bash
# Regenerate the G4 dependency evidence artifacts:
#   - docs/handover-evidence/sbom.cdx.json            (CycloneDX SBOM, resolved env)
#   - docs/handover-evidence/dependency-licenses.csv  (license inventory, declared deps)
#   - docs/handover-evidence/dependency-licenses.md   (same, + notable-licenses summary)
#   - docs/handover-evidence/transitive-dependency-licenses.csv  (resolved env licenses)
#   - docs/handover-evidence/transitive-dependency-licenses.md   (same, + honest summary)
#
# Named tools (pinned) are installed in an ISOLATED venv so they never pollute the
# project's own dependency surface. KS is installed (with extras) into a project
# venv; the SBOM is taken from that resolved environment, and the license
# inventory is filtered to the declared names in pyproject.toml.
#
# Requires network access to the package index. Usage:
#   scripts/generate-dependency-evidence.sh [SNAPSHOT_DATE]
set -euo pipefail

CYCLONEDX_BOM_VERSION="7.3.0"
PIP_LICENSES_VERSION="5.5.5"
SNAPSHOT_DATE="${1:-$(date +%F)}"
PY_BIN="${PY:-python3}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="docs/handover-evidence"
WORK="$(mktemp -d)"
TOOLS="$WORK/tools"
PROJ="$WORK/proj"

if [[ ! -f constraints.txt ]]; then
  echo "constraints.txt is missing; run 'make lock' first" >&2
  exit 2
fi

# Pinned SBOM/license tooling in an isolated venv.
"$PY_BIN" -m venv "$TOOLS"
"$TOOLS/bin/pip" install --quiet --disable-pip-version-check \
  "cyclonedx-bom==${CYCLONEDX_BOM_VERSION}" "pip-licenses==${PIP_LICENSES_VERSION}" "tomli==2.0.1"

# Materialize the full Ubuntu reference lock even when evidence is regenerated
# on another host, then install KS without allowing dependency drift.
"$PY_BIN" -m venv "$PROJ"
"$PROJ/bin/pip" install --quiet --disable-pip-version-check \
  --no-deps --requirement constraints.txt
"$PROJ/bin/pip" install --quiet --disable-pip-version-check \
  --constraint constraints.txt -e ".[all,test]"
"$PROJ/bin/python" scripts/dependency_audit.py installed --constraints constraints.txt
"$PROJ/bin/python" -m pip check

# 1. CycloneDX SBOM from the resolved project environment.
"$TOOLS/bin/cyclonedx-py" environment "$PROJ" \
  --of JSON --output-reproducible -o "$OUT/sbom.cdx.json"

# cyclonedx-py records editable local package sources as file:// URLs. Those are
# not useful for adopters and can leak personal checkout paths into evidence.
"$TOOLS/bin/python" - "$OUT/sbom.cdx.json" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path) as f:
    bom = json.load(f)

for component in bom.get("components", []):
    refs = component.get("externalReferences")
    if not refs:
        continue
    scrubbed = [
        ref
        for ref in refs
        if not str(ref.get("url", "")).startswith("file://")
    ]
    if scrubbed:
        component["externalReferences"] = scrubbed
    else:
        component.pop("externalReferences", None)

with open(path, "w") as f:
    json.dump(bom, f, indent=2)
    f.write("\n")
PY

# 2. License inventory, filtered to the names declared in pyproject.toml.
"$TOOLS/bin/pip-licenses" --python "$PROJ/bin/python" --format json > "$WORK/all.json"
SNAPSHOT_DATE="$SNAPSHOT_DATE" PIP_LICENSES_VERSION="$PIP_LICENSES_VERSION" \
  "$TOOLS/bin/python" - "$WORK/all.json" "$OUT" pyproject.toml <<'PY'
import csv, json, os, re, sys
try:
    import tomllib
except ModuleNotFoundError:  # Compatibility fallback for tooling interpreters
    import tomli as tomllib
all_json, outdir, pyproject = sys.argv[1], sys.argv[2], sys.argv[3]
norm = lambda n: n.lower().replace("-", "").replace("_", "")
with open(pyproject, "rb") as f:
    proj = tomllib.load(f)["project"]
# Map each declared name to its scope (core / optional-<group> / test) so the
# regenerated evidence keeps the runtime/optional/test distinction.
scope_of = {}
def _reg(deps, scope):
    for d in deps:
        scope_of.setdefault(norm(re.split(r"[<>=!;\[ ]", d, 1)[0]), scope)
_reg(proj.get("dependencies", []), "core")
for grp, deps in proj.get("optional-dependencies", {}).items():
    if grp == "all":
        continue  # 'all' re-aggregates the other extras; skip to avoid double-listing
    _reg(deps, "test" if grp == "test" else f"optional-{grp}")
project_name = norm(proj["name"])
all_rows = sorted(
    (r for r in json.load(open(all_json)) if norm(r["Name"]) != project_name),
    key=lambda r: r["Name"].lower(),
)
rows = [r for r in all_rows if norm(r["Name"]) in scope_of]

with open(os.path.join(outdir, "dependency-licenses.csv"), "w", newline="") as f:
    w = csv.writer(f, lineterminator="\n"); w.writerow(["Name", "Version", "License", "Scope"])
    for r in rows:
        w.writerow([r["Name"], r["Version"], r["License"], scope_of[norm(r["Name"])]])

copyleft = re.compile(r"GPL|LGPL|AGPL|MPL|EPL", re.I)
flagged = [r for r in rows if copyleft.search(r["License"]) or r["License"].strip().upper() == "UNKNOWN"]
summary = ("**Flagged licenses present:** " + ", ".join(f"`{r['Name']}` ({r['License']})" for r in flagged)
           + ". Review before import.") if flagged else (
           "**All declared dependencies are permissive (MIT / Apache-2.0 / BSD). No copyleft "
           "(GPL / LGPL / AGPL / MPL / EPL) and no UNKNOWN-license packages are present among the "
           "declared surface.**")
table = "| Package | Version | License | Scope |\n|---|---|---|---|\n" + "".join(
    f"| `{r['Name']}` | {r['Version']} | {r['License']} | {scope_of[norm(r['Name'])]} |\n" for r in rows)
md = f"""# Dependency License Inventory — EdgeForge Knowledge Server (declared deps)

> **Import-gate G4 evidence.** Resolved license inventory of KS's declared
> dependencies. See [`dependencies.md`](dependencies.md) for scope and tooling.
>
> **Generated:** {os.environ['SNAPSHOT_DATE']}, with **pip-licenses {os.environ['PIP_LICENSES_VERSION']}**.
> **Reference baseline:** CPython 3.11 on Ubuntu 24.04 x86_64, using the exact
> versions in `constraints.txt`.

## Notable licenses — summary

{summary}

## Declared dependencies (resolved)

Machine-readable copy: [`dependency-licenses.csv`](dependency-licenses.csv).

{table}
## Scope & transitive note

Covers the **directly declared** dependencies. The resolved transitive license
scan is recorded separately in
[`transitive-dependency-licenses.md`](transitive-dependency-licenses.md). A full
adopter-side audit should rerun both scans against the approved package mirror.
"""
open(os.path.join(outdir, "dependency-licenses.md"), "w").write(md.rstrip() + "\n")

with open(os.path.join(outdir, "transitive-dependency-licenses.csv"), "w", newline="") as f:
    w = csv.writer(f, lineterminator="\n"); w.writerow(["Name", "Version", "License"])
    for r in all_rows:
        w.writerow([r["Name"], r["Version"], r["License"]])

transitive_flagged = [
    r for r in all_rows
    if copyleft.search(r["License"]) or r["License"].strip().upper() == "UNKNOWN"
]
transitive_summary = (
    "**Flagged licenses present:** "
    + ", ".join(f"`{r['Name']}` ({r['License']})" for r in transitive_flagged)
    + ". Review before import."
) if transitive_flagged else (
    "**No copyleft (GPL / LGPL / AGPL / MPL / EPL) or UNKNOWN-license packages "
    "were reported in the resolved `[all,test]` environment by pip-licenses.**"
)
transitive_table = "| Package | Version | License |\n|---|---|---|\n" + "".join(
    f"| `{r['Name']}` | {r['Version']} | {r['License']} |\n" for r in all_rows)
transitive_md = f"""# Transitive Dependency License Scan — EdgeForge Knowledge Server

> **Import-gate G4 / P1 evidence.** Resolved license scan of the KS
> `[all,test]` environment, including transitive dependencies. This complements
> the declared-dependency inventory in [`dependency-licenses.md`](dependency-licenses.md).
>
> **Generated:** {os.environ['SNAPSHOT_DATE']}, with **pip-licenses {os.environ['PIP_LICENSES_VERSION']}**.
> **Reference baseline:** CPython 3.11 on Ubuntu 24.04 x86_64, using the exact
> versions in `constraints.txt`.

## Honest status

{transitive_summary}

This scan is package-metadata based and should be regenerated in the adopting
organization's approved package mirror before import.

## Resolved packages

Machine-readable copy: [`transitive-dependency-licenses.csv`](transitive-dependency-licenses.csv).

{transitive_table}
"""
open(os.path.join(outdir, "transitive-dependency-licenses.md"), "w").write(transitive_md.rstrip() + "\n")
print(
    f"wrote {len(rows)} declared deps; flagged declared: {len(flagged)}; "
    f"transitive packages: {len(all_rows)}; flagged transitive: {len(transitive_flagged)}"
)
PY

rm -rf "$WORK"
echo "dependency evidence regenerated under $OUT/"
