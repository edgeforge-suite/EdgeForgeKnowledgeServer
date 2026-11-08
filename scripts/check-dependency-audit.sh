#!/usr/bin/env bash
# Run the blocking live vulnerability audit in an isolated tooling environment.
set -euo pipefail

PIP_AUDIT_VERSION="2.10.1"
PY_BIN="${PY:-python3}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
WORK="$(mktemp -d)"
TOOLS="$WORK/tools"
trap 'rm -rf "$WORK"' EXIT

"$PY_BIN" -m venv "$TOOLS"
"$TOOLS/bin/python" -m pip install --quiet --disable-pip-version-check \
  "pip-audit==${PIP_AUDIT_VERSION}"
"$TOOLS/bin/pip-audit" --version
"$PY_BIN" scripts/dependency_audit.py audit \
  --scanner "$TOOLS/bin/pip-audit" \
  --constraints constraints.txt
