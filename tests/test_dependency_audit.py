from __future__ import annotations

import csv
import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.dependency_audit import (
    INSTALLED_INVENTORY_ALLOWLIST,
    DependencyBaselineError,
    PackagePin,
    load_constraints,
    normalize_package_name,
    run_blocking_audit,
    validate_audit_report,
    validate_installed_environment,
    validate_inventory,
)

REPO_ROOT = Path(__file__).parent.parent
INCOMPLETE_ADVISORY_RESULTS = [
    pytest.param({}, id="missing-vulns"),
    pytest.param({"vulns": None}, id="null-vulns"),
    pytest.param({"vulns": {}}, id="mapping-vulns"),
    pytest.param({"vulns": "[]"}, id="string-vulns"),
    pytest.param({"vulns": 0}, id="integer-vulns"),
    pytest.param({"vulns": False}, id="boolean-vulns"),
    pytest.param({"skip_reason": "advisory data unavailable"}, id="skipped-with-version"),
    pytest.param(
        {"vulns": [], "skip_reason": "advisory data unavailable"},
        id="skipped-with-version-and-vulns",
    ),
    pytest.param({"vulns": [], "skip_reason": None}, id="malformed-skip-reason"),
]


def _inventory(records: list[tuple[str, str]]) -> dict[str, PackagePin]:
    packages: dict[str, PackagePin] = {}
    for name, version in records:
        normalized = normalize_package_name(name)
        assert normalized not in packages, f"duplicate inventory package: {name}"
        packages[normalized] = PackagePin(name=name, version=version)
    return packages


def _write_constraints(path: Path) -> Path:
    path.write_text("Example_Package==1.2.3\nsecond-package==4.5.6\n", encoding="utf-8")
    return path


def _write_report(
    path: Path,
    *,
    first_version: str = "1.2.3",
    include_second: bool = True,
    vulnerabilities: list[dict[str, object]] | None = None,
) -> Path:
    dependencies = [
        {
            "name": "example-package",
            "version": first_version,
            "vulns": vulnerabilities or [],
        }
    ]
    if include_second:
        dependencies.append({"name": "Second_Package", "version": "4.5.6", "vulns": []})
    path.write_text(json.dumps({"dependencies": dependencies, "fixes": []}), encoding="utf-8")
    return path


def test_clean_complete_audit_inventory_passes(tmp_path: Path) -> None:
    constraints = _write_constraints(tmp_path / "constraints.txt")
    report = _write_report(tmp_path / "audit.json")

    summary = validate_audit_report(constraints, report)

    assert summary.package_count == 2
    assert summary.vulnerability_count == 0


@pytest.mark.parametrize("advisory_fields", INCOMPLETE_ADVISORY_RESULTS)
@pytest.mark.parametrize("allow_vulnerabilities", [False, True])
def test_incomplete_advisory_result_fails_in_both_validation_modes(
    tmp_path: Path,
    advisory_fields: dict[str, object],
    allow_vulnerabilities: bool,
) -> None:
    constraints = _write_constraints(tmp_path / "constraints.txt")
    report = _write_report(tmp_path / "audit.json")
    payload = json.loads(report.read_text(encoding="utf-8"))
    dependency = payload["dependencies"][0]
    dependency.pop("vulns")
    dependency.update(advisory_fields)
    report.write_text(json.dumps(payload), encoding="utf-8")
    error = "skipped" if "skip_reason" in advisory_fields else "invalid vulnerabilities"

    with pytest.raises(DependencyBaselineError, match=error):
        validate_audit_report(constraints, report, allow_vulnerabilities=allow_vulnerabilities)


def _mock_report_scanner(monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]) -> None:
    def emit_report(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert "--no-deps" in arguments
        assert "--disable-pip" in arguments
        output = Path(arguments[arguments.index("--output") + 1])
        output.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(arguments, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("scripts.dependency_audit.subprocess.run", emit_report)


@pytest.mark.parametrize("advisory_fields", INCOMPLETE_ADVISORY_RESULTS)
def test_blocking_audit_rejects_incomplete_result_with_exact_full_inventory(
    monkeypatch: pytest.MonkeyPatch,
    advisory_fields: dict[str, object],
) -> None:
    payload = json.loads(
        (REPO_ROOT / "docs/handover-evidence/pip-audit.json").read_text(encoding="utf-8")
    )
    dependency = next(
        item for item in payload["dependencies"] if normalize_package_name(item["name"]) == "pyjwt"
    )
    dependency.pop("vulns")
    dependency.update(advisory_fields)
    _mock_report_scanner(monkeypatch, payload)
    error = "skipped" if "skip_reason" in advisory_fields else "invalid vulnerabilities"

    with pytest.raises(DependencyBaselineError, match=error):
        run_blocking_audit(
            scanner=Path("synthetic-scanner"), constraints_path=REPO_ROOT / "constraints.txt"
        )


def test_blocking_audit_accepts_explicit_clean_full_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.loads(
        (REPO_ROOT / "docs/handover-evidence/pip-audit.json").read_text(encoding="utf-8")
    )
    for dependency in payload["dependencies"]:
        dependency["vulns"] = []
    _mock_report_scanner(monkeypatch, payload)

    summary = run_blocking_audit(
        scanner=Path("synthetic-scanner"), constraints_path=REPO_ROOT / "constraints.txt"
    )

    assert summary.package_count == len(load_constraints(REPO_ROOT / "constraints.txt"))
    assert summary.vulnerability_count == 0


def test_simulated_vulnerability_fails(tmp_path: Path) -> None:
    constraints = _write_constraints(tmp_path / "constraints.txt")
    report = _write_report(
        tmp_path / "audit.json",
        vulnerabilities=[{"id": "TEST-2026-0001", "fix_versions": ["1.2.4"]}],
    )

    with pytest.raises(DependencyBaselineError, match="TEST-2026-0001"):
        validate_audit_report(constraints, report)


def test_evidence_validation_can_record_vulnerability(tmp_path: Path) -> None:
    constraints = _write_constraints(tmp_path / "constraints.txt")
    report = _write_report(
        tmp_path / "audit.json",
        vulnerabilities=[{"id": "TEST-2026-0001", "fix_versions": ["1.2.4"]}],
    )

    summary = validate_audit_report(constraints, report, allow_vulnerabilities=True)

    assert summary.vulnerability_count == 1


def test_missing_audited_package_fails(tmp_path: Path) -> None:
    constraints = _write_constraints(tmp_path / "constraints.txt")
    report = _write_report(tmp_path / "audit.json", include_second=False)

    with pytest.raises(DependencyBaselineError, match="missing package.*second-package==4.5.6"):
        validate_audit_report(constraints, report)


def test_audited_version_mismatch_fails(tmp_path: Path) -> None:
    constraints = _write_constraints(tmp_path / "constraints.txt")
    report = _write_report(tmp_path / "audit.json", first_version="1.2.4")

    with pytest.raises(DependencyBaselineError, match="expected 1.2.3, found 1.2.4"):
        validate_audit_report(constraints, report)


def test_unlisted_installed_application_dependency_fails() -> None:
    expected = _inventory([("expected-package", "1.0.0")])
    actual = _inventory(
        [
            ("expected-package", "1.0.0"),
            ("unlisted-linux-dependency", "2.0.0"),
        ]
    )

    with pytest.raises(
        DependencyBaselineError,
        match=r"unexpected package\(s\): unlisted-linux-dependency==2.0.0",
    ):
        validate_inventory(
            expected,
            actual,
            actual_label="installed",
            allowed_extras=INSTALLED_INVENTORY_ALLOWLIST,
        )


def test_documented_installed_bootstrap_packages_are_allowed() -> None:
    expected = _inventory([("expected-package", "1.0.0")])
    actual = _inventory(
        [
            ("expected-package", "1.0.0"),
            ("edgeforge-knowledge-server", "5.0.0"),
            ("pip", "26.0.1"),
            ("setuptools", "82.0.0"),
            ("wheel", "0.46.3"),
        ]
    )

    validate_inventory(
        expected,
        actual,
        actual_label="installed",
        allowed_extras=INSTALLED_INVENTORY_ALLOWLIST,
    )


def test_installed_environment_rejects_unlisted_application_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constraints = tmp_path / "constraints.txt"
    constraints.write_text("expected-package==1.0.0\n", encoding="utf-8")
    distributions = [
        SimpleNamespace(metadata={"Name": "expected-package"}, version="1.0.0"),
        SimpleNamespace(metadata={"Name": "edgeforge-knowledge-server"}, version="5.0.0"),
        SimpleNamespace(metadata={"Name": "pip"}, version="26.0.1"),
        SimpleNamespace(metadata={"Name": "unlisted-application-package"}, version="9.9.9"),
    ]
    monkeypatch.setattr(
        "scripts.dependency_audit.metadata.distributions",
        lambda: distributions,
    )

    with pytest.raises(
        DependencyBaselineError,
        match=r"unexpected package\(s\): unlisted-application-package==9.9.9",
    ):
        validate_installed_environment(constraints)


def test_scanner_execution_failure_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constraints = _write_constraints(tmp_path / "constraints.txt")

    def fail_scanner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=2, stdout="", stderr="scanner failed")

    monkeypatch.setattr("scripts.dependency_audit.subprocess.run", fail_scanner)

    with pytest.raises(DependencyBaselineError, match="status 2: scanner failed"):
        run_blocking_audit(scanner=Path("pip-audit"), constraints_path=constraints)


def test_committed_audit_inventory_matches_constraints() -> None:
    summary = validate_audit_report(
        REPO_ROOT / "constraints.txt",
        REPO_ROOT / "docs/handover-evidence/pip-audit.json",
        allow_vulnerabilities=True,
    )

    assert summary.package_count == len(load_constraints(REPO_ROOT / "constraints.txt"))


def test_committed_license_inventory_matches_constraints() -> None:
    expected = load_constraints(REPO_ROOT / "constraints.txt")
    with (REPO_ROOT / "docs/handover-evidence/transitive-dependency-licenses.csv").open(
        newline="",
        encoding="utf-8",
    ) as stream:
        rows = list(csv.DictReader(stream))
    actual = _inventory([(row["Name"], row["Version"]) for row in rows])

    validate_inventory(expected, actual, actual_label="license evidence")


def test_committed_sbom_contains_constrained_inventory() -> None:
    expected = load_constraints(REPO_ROOT / "constraints.txt")
    sbom = json.loads(
        (REPO_ROOT / "docs/handover-evidence/sbom.cdx.json").read_text(encoding="utf-8")
    )
    actual = _inventory(
        [
            (component["name"], component["version"])
            for component in sbom["components"]
            if component.get("name") and component.get("version")
        ]
    )

    validate_inventory(
        expected,
        actual,
        actual_label="SBOM",
        allowed_extras=INSTALLED_INVENTORY_ALLOWLIST,
    )


def test_reference_constraints_include_linux_keyring_dependencies() -> None:
    constraints = load_constraints(REPO_ROOT / "constraints.txt")

    assert constraints["secretstorage"].version == "3.5.0"
    assert constraints["jeepney"].version == "0.9.0"


def test_live_and_evidence_audit_tool_pins_match() -> None:
    scripts = [
        REPO_ROOT / "scripts/check-dependency-audit.sh",
        REPO_ROOT / "scripts/generate-pip-audit-evidence.sh",
    ]
    pins = []
    for script in scripts:
        match = re.search(
            r'^PIP_AUDIT_VERSION="([^"]+)"$',
            script.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        assert match is not None, f"{script} must contain one exact pip-audit version"
        pins.append(match.group(1))

    assert pins[0] == pins[1], "live and evidence pip-audit tool pins must match"
