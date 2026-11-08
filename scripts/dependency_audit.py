#!/usr/bin/env python3
"""Validate the resolved dependency baseline and pip-audit coverage."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

PIN_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)(?:\s*;.*)?$")
INSTALLED_INVENTORY_ALLOWLIST = frozenset(
    {
        "edgeforge-knowledge-server",
        "pip",
        "setuptools",
        "wheel",
    }
)


class DependencyBaselineError(RuntimeError):
    """Raised when dependency evidence does not match the committed baseline."""


@dataclass(frozen=True)
class PackagePin:
    name: str
    version: str


@dataclass(frozen=True)
class AuditSummary:
    package_count: int
    vulnerability_count: int


def normalize_package_name(name: str) -> str:
    """Return the PEP 503 normalized form used for inventory comparisons."""
    return re.sub(r"[-_.]+", "-", name).lower()


def load_constraints(path: Path) -> dict[str, PackagePin]:
    """Load exact pins from a generated constraints file."""
    packages: dict[str, PackagePin] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_PATTERN.fullmatch(line)
        if match is None:
            raise DependencyBaselineError(
                f"{path}:{line_number} must contain an exact name==version pin"
            )
        name, version = match.groups()
        normalized = normalize_package_name(name)
        if normalized in packages:
            raise DependencyBaselineError(
                f"{path}:{line_number} duplicates package {packages[normalized].name}"
            )
        packages[normalized] = PackagePin(name=name, version=version)
    if not packages:
        raise DependencyBaselineError(f"{path} contains no package pins")
    return packages


def load_audit_report(path: Path) -> tuple[dict[str, PackagePin], list[tuple[str, str]]]:
    """Load package versions and unique vulnerability IDs from pip-audit JSON."""
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DependencyBaselineError(f"could not read pip-audit report {path}: {exc}") from exc

    dependencies = payload.get("dependencies") if isinstance(payload, dict) else None
    if not isinstance(dependencies, list):
        raise DependencyBaselineError(f"{path} has no pip-audit dependencies list")

    packages: dict[str, PackagePin] = {}
    vulnerabilities: set[tuple[str, str]] = set()
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            raise DependencyBaselineError(f"{path} contains an invalid dependency entry")
        name = dependency.get("name")
        version = dependency.get("version")
        if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
            raise DependencyBaselineError(f"{path} contains a dependency without name/version")
        normalized = normalize_package_name(name)
        if normalized in packages:
            raise DependencyBaselineError(f"{path} contains duplicate package {name}")
        packages[normalized] = PackagePin(name=name, version=version)

        if "skip_reason" in dependency:
            raise DependencyBaselineError(f"{path} contains a skipped audit result for {name}")
        vulns = dependency.get("vulns")
        if not isinstance(vulns, list):
            raise DependencyBaselineError(f"{path} contains invalid vulnerabilities for {name}")
        for vulnerability in vulns:
            if not isinstance(vulnerability, dict) or not vulnerability.get("id"):
                raise DependencyBaselineError(f"{path} contains an invalid vulnerability for {name}")
            vulnerabilities.add((normalized, str(vulnerability["id"])))

    return packages, sorted(vulnerabilities)


def validate_inventory(
    expected: dict[str, PackagePin],
    actual: dict[str, PackagePin],
    *,
    actual_label: str,
    allowed_extras: frozenset[str] = frozenset(),
) -> None:
    """Require all expected normalized names and exact versions in an inventory."""
    normalized_allowed_extras = {normalize_package_name(name) for name in allowed_extras}
    missing = sorted(set(expected) - set(actual))
    mismatched = sorted(
        name
        for name in set(expected) & set(actual)
        if expected[name].version != actual[name].version
    )
    extras = sorted(set(actual) - set(expected) - normalized_allowed_extras)

    problems: list[str] = []
    if missing:
        problems.append(
            "missing package(s): " + ", ".join(
                f"{expected[name].name}=={expected[name].version}" for name in missing
            )
        )
    if mismatched:
        problems.append(
            "version mismatch(es): " + ", ".join(
                f"{expected[name].name} expected {expected[name].version}, "
                f"found {actual[name].version}"
                for name in mismatched
            )
        )
    if extras:
        problems.append(
            "unexpected package(s): " + ", ".join(
                f"{actual[name].name}=={actual[name].version}" for name in extras
            )
        )
    if problems:
        raise DependencyBaselineError(f"{actual_label} inventory mismatch: {'; '.join(problems)}")


def validate_audit_report(
    constraints_path: Path,
    report_path: Path,
    *,
    allow_vulnerabilities: bool = False,
) -> AuditSummary:
    """Validate exact audit coverage and optionally reject all findings."""
    expected = load_constraints(constraints_path)
    actual, vulnerabilities = load_audit_report(report_path)
    validate_inventory(expected, actual, actual_label="pip-audit")
    if vulnerabilities and not allow_vulnerabilities:
        formatted = ", ".join(
            f"{expected[name].name}:{vulnerability_id}"
            for name, vulnerability_id in vulnerabilities
        )
        raise DependencyBaselineError(
            f"pip-audit reported {len(vulnerabilities)} vulnerability finding(s): {formatted}"
        )
    return AuditSummary(
        package_count=len(actual),
        vulnerability_count=len(vulnerabilities),
    )


def validate_installed_environment(constraints_path: Path) -> int:
    """Verify exact baseline pins and reject non-bootstrap installed packages."""
    expected = load_constraints(constraints_path)
    actual: dict[str, PackagePin] = {}
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if not name:
            continue
        normalized = normalize_package_name(name)
        actual[normalized] = PackagePin(name=name, version=distribution.version)
    validate_inventory(
        expected,
        actual,
        actual_label="installed",
        allowed_extras=INSTALLED_INVENTORY_ALLOWLIST,
    )
    return len(expected)


def run_blocking_audit(*, scanner: Path, constraints_path: Path) -> AuditSummary:
    """Run pip-audit and fail closed on scanner, coverage, version, or finding errors."""
    with tempfile.TemporaryDirectory(prefix="edgeforge-ks-audit-") as temp_dir:
        report_path = Path(temp_dir) / "pip-audit.json"
        completed = subprocess.run(
            [
                str(scanner),
                "-r",
                str(constraints_path),
                "--no-deps",
                "--disable-pip",
                "--format",
                "json",
                "--output",
                str(report_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "no scanner output"
            raise DependencyBaselineError(
                f"pip-audit failed with status {completed.returncode}: {detail}"
            )
        return validate_audit_report(constraints_path, report_path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="run the blocking live audit")
    audit_parser.add_argument("--scanner", type=Path, required=True)
    audit_parser.add_argument("--constraints", type=Path, default=Path("constraints.txt"))

    validate_parser = subparsers.add_parser("validate", help="validate an existing audit report")
    validate_parser.add_argument("--constraints", type=Path, default=Path("constraints.txt"))
    validate_parser.add_argument("--report", type=Path, required=True)
    validate_parser.add_argument("--allow-vulnerabilities", action="store_true")

    installed_parser = subparsers.add_parser(
        "installed", help="compare the active environment with constraints"
    )
    installed_parser.add_argument("--constraints", type=Path, default=Path("constraints.txt"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "audit":
            summary = run_blocking_audit(
                scanner=args.scanner,
                constraints_path=args.constraints,
            )
            print(
                f"dependency audit passed: {summary.package_count} packages, "
                f"{summary.vulnerability_count} findings"
            )
        elif args.command == "validate":
            summary = validate_audit_report(
                args.constraints,
                args.report,
                allow_vulnerabilities=args.allow_vulnerabilities,
            )
            print(
                f"dependency audit inventory valid: {summary.package_count} packages, "
                f"{summary.vulnerability_count} findings"
            )
        else:
            package_count = validate_installed_environment(args.constraints)
            print(f"installed dependency baseline valid: {package_count} packages")
    except DependencyBaselineError as exc:
        print(f"dependency baseline check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
