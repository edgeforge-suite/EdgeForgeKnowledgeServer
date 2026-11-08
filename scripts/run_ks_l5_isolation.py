from __future__ import annotations

# ruff: noqa: E402, I001
# Direct script execution requires sys.path insertion before local imports.

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from knowledge_server.server import _resolve_db_path
from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.evidence import get_evidence
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.portfolio import search_across_projects
from knowledge_server.tools.search import list_documents, search_documents


@dataclass(frozen=True)
class CheckResult:
    name: str
    success: bool
    detail: str | None = None


def run_ks_l5_isolation() -> dict[str, Any]:
    """Run KS-side L5 isolation checks in an ephemeral local workspace."""

    checks: list[CheckResult] = []
    with tempfile.TemporaryDirectory(prefix="edgeforge-ks-l5-") as raw_root:
        root = Path(raw_root)
        checks.append(_run_check("per_session_db_isolation", lambda: _check_per_session_db(root)))
        checks.append(
            _run_check("project_scoped_search_no_bleed", lambda: _check_project_scope(root))
        )
        checks.append(
            _run_check(
                "explicit_cross_project_filter_no_bleed",
                lambda: _check_cross_project_filter(root),
            )
        )
        checks.append(
            _run_check("allowed_root_rejects_outside_read", lambda: _check_allowed_root(root))
        )
        checks.append(
            _run_check(
                "shared_mode_requires_explicit_db_path",
                _check_shared_mode_requires_explicit_db_path,
            )
        )
        checks.append(
            _run_check("results_do_not_leak_absolute_paths", lambda: _check_no_path_leak(root))
        )

    return {
        "success": all(check.success for check in checks),
        "tool_name": "run_ks_l5_isolation",
        "checks": [
            {
                "name": check.name,
                "success": check.success,
                **({"detail": check.detail} if check.detail else {}),
            }
            for check in checks
        ],
    }


def _run_check(name: str, check: Callable[[], None]) -> CheckResult:
    try:
        check()
    except Exception as exc:  # pragma: no cover - exercised by failed acceptance runs.
        return CheckResult(name=name, success=False, detail=str(exc))
    return CheckResult(name=name, success=True)


def _check_per_session_db(root: Path) -> None:
    session_a_docs = root / "session-a-docs"
    session_b_docs = root / "session-b-docs"
    session_a_db_root = root / "session-a"
    session_b_db_root = root / "session-b"
    session_a_docs.mkdir()
    session_b_docs.mkdir()
    session_a_db_root.mkdir()
    session_b_db_root.mkdir()
    session_a_doc = _write_doc(session_a_docs / "rules.md", "l5sessionalpha")
    session_b_doc = _write_doc(session_b_docs / "rules.md", "l5sessionbeta")

    session_a_store = KnowledgeStore(session_a_db_root / "ks.sqlite3")
    session_b_store = KnowledgeStore(session_b_db_root / "ks.sqlite3")
    try:
        ingest_document(
            store=session_a_store,
            allowed_roots=[session_a_docs.resolve()],
            project_id="same-project-id",
            file_path=str(session_a_doc),
            doc_type="markdown",
        )
        ingest_document(
            store=session_b_store,
            allowed_roots=[session_b_docs.resolve()],
            project_id="same-project-id",
            file_path=str(session_b_doc),
            doc_type="markdown",
        )

        assert (
            search_documents(
                store=session_a_store,
                project_id="same-project-id",
                query="l5sessionalpha",
            ).result_count
            == 1
        )
        assert (
            search_documents(
                store=session_a_store,
                project_id="same-project-id",
                query="l5sessionbeta",
            ).result_count
            == 0
        )
        assert (
            search_documents(
                store=session_b_store,
                project_id="same-project-id",
                query="l5sessionbeta",
            ).result_count
            == 1
        )
        assert (
            search_documents(
                store=session_b_store,
                project_id="same-project-id",
                query="l5sessionalpha",
            ).result_count
            == 0
        )
        assert (
            search_across_projects(
                store=session_a_store,
                query="l5sessionalpha",
            ).total_result_count
            == 1
        )
        assert (
            search_across_projects(
                store=session_a_store,
                query="l5sessionbeta",
            ).total_result_count
            == 0
        )
        assert (
            search_across_projects(
                store=session_b_store,
                query="l5sessionbeta",
            ).total_result_count
            == 1
        )
        assert (
            search_across_projects(
                store=session_b_store,
                query="l5sessionalpha",
            ).total_result_count
            == 0
        )
    finally:
        session_a_store.close()
        session_b_store.close()


def _check_project_scope(root: Path) -> None:
    docs_root = root / "project-scope-docs"
    docs_root.mkdir()
    project_a_doc = _write_doc(docs_root / "project-a.md", "l5projectalpha sharedtopic")
    project_b_doc = _write_doc(docs_root / "project-b.md", "l5projectbeta sharedtopic")
    store = KnowledgeStore(root / "project-scope.sqlite3")
    try:
        ingest_document(
            store=store,
            allowed_roots=[docs_root.resolve()],
            project_id="project-a",
            file_path=str(project_a_doc),
            doc_type="markdown",
        )
        ingest_document(
            store=store,
            allowed_roots=[docs_root.resolve()],
            project_id="project-b",
            file_path=str(project_b_doc),
            doc_type="markdown",
        )

        assert (
            list_documents(store=store, project_id="project-a").documents[0].name
            == "project-a.md"
        )
        assert (
            list_documents(store=store, project_id="project-b").documents[0].name
            == "project-b.md"
        )
        assert (
            search_documents(
                store=store,
                project_id="project-a",
                query="l5projectalpha",
            ).result_count
            == 1
        )
        assert (
            search_documents(
                store=store,
                project_id="project-a",
                query="l5projectbeta",
            ).result_count
            == 0
        )
        assert (
            search_documents(
                store=store,
                project_id="project-b",
                query="l5projectbeta",
            ).result_count
            == 1
        )
        assert (
            search_documents(
                store=store,
                project_id="project-b",
                query="l5projectalpha",
            ).result_count
            == 0
        )
    finally:
        store.close()


def _check_cross_project_filter(root: Path) -> None:
    docs_root = root / "portfolio-docs"
    docs_root.mkdir()
    project_a_doc = _write_doc(docs_root / "project-a.md", "l5portfoliocommon from project a")
    project_b_doc = _write_doc(docs_root / "project-b.md", "l5portfoliocommon from project b")
    store = KnowledgeStore(root / "portfolio.sqlite3")
    try:
        ingest_document(
            store=store,
            allowed_roots=[docs_root.resolve()],
            project_id="project-a",
            file_path=str(project_a_doc),
            doc_type="markdown",
        )
        ingest_document(
            store=store,
            allowed_roots=[docs_root.resolve()],
            project_id="project-b",
            file_path=str(project_b_doc),
            doc_type="markdown",
        )

        broad = search_across_projects(store=store, query="l5portfoliocommon")
        filtered = search_across_projects(
            store=store,
            query="l5portfoliocommon",
            project_ids=["project-a"],
        )

        assert {entry.project_id for entry in broad.by_project} == {"project-a", "project-b"}
        assert [entry.project_id for entry in filtered.by_project] == ["project-a"]
        assert filtered.total_result_count == 1
    finally:
        store.close()


def _check_allowed_root(root: Path) -> None:
    allowed_root = root / "allowed"
    outside_root = root / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    outside_doc = _write_doc(outside_root / "outside.md", "outside-token")
    store = KnowledgeStore(root / "allowed-root.sqlite3")
    try:
        try:
            ingest_document(
                store=store,
                allowed_roots=[allowed_root.resolve()],
                project_id="project-a",
                file_path=str(outside_doc),
                doc_type="markdown",
            )
        except ValueError as exc:
            assert "allowed root" in str(exc)
        else:
            raise AssertionError("outside allowed root ingest unexpectedly succeeded")
    finally:
        store.close()


def _check_shared_mode_requires_explicit_db_path() -> None:
    original_shared_mode = os.environ.get("EDGEFORGE_SHARED_MODE")
    original_db_path = os.environ.get("EDGEFORGE_KS_DB_PATH")
    try:
        os.environ["EDGEFORGE_SHARED_MODE"] = "1"
        os.environ.pop("EDGEFORGE_KS_DB_PATH", None)
        try:
            _resolve_db_path()
        except RuntimeError as exc:
            assert "EDGEFORGE_KS_DB_PATH is required" in str(exc)
        else:
            raise AssertionError("shared mode unexpectedly allowed cwd DB fallback")
    finally:
        _restore_env("EDGEFORGE_SHARED_MODE", original_shared_mode)
        _restore_env("EDGEFORGE_KS_DB_PATH", original_db_path)


def _check_no_path_leak(root: Path) -> None:
    docs_root = root / "no-path-leak-docs"
    docs_root.mkdir()
    source = _write_doc(docs_root / "rules.md", "path leak guard token")
    store = KnowledgeStore(root / "no-path-leak.sqlite3")
    try:
        ingest_document(
            store=store,
            allowed_roots=[docs_root.resolve()],
            project_id="project-a",
            file_path=str(source),
            doc_type="markdown",
        )
        payloads = [
            list_documents(store=store, project_id="project-a").model_dump(),
            search_documents(store=store, project_id="project-a", query="guard").model_dump(),
            get_evidence(store=store, project_id="project-a", query="guard").model_dump(),
        ]
        serialized = json.dumps(payloads, sort_keys=True)
        assert str(root) not in serialized
    finally:
        store.close()


def _write_doc(path: Path, token: str) -> Path:
    path.write_text(f"# L5 Fixture\n\nThis synthetic fixture contains {token}.\n", encoding="utf-8")
    return path


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def main() -> int:
    parser = argparse.ArgumentParser(description="Run KS L5 isolation acceptance helpers.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the JSON result.")
    args = parser.parse_args()

    result = run_ks_l5_isolation()
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
