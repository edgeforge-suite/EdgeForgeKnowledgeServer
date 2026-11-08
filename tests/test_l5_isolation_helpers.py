from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_ks_l5_isolation import run_ks_l5_isolation


def test_ks_l5_isolation_helper_passes_all_checks() -> None:
    result = run_ks_l5_isolation()

    assert result["success"] is True
    assert {check["name"] for check in result["checks"]} == {
        "per_session_db_isolation",
        "project_scoped_search_no_bleed",
        "explicit_cross_project_filter_no_bleed",
        "allowed_root_rejects_outside_read",
        "shared_mode_requires_explicit_db_path",
        "results_do_not_leak_absolute_paths",
    }
    assert all(check["success"] is True for check in result["checks"])


def test_ks_l5_isolation_script_outputs_parseable_json() -> None:
    script = Path("scripts/run_ks_l5_isolation.py")

    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["success"] is True
    assert payload["tool_name"] == "run_ks_l5_isolation"
