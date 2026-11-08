from __future__ import annotations

import asyncio

import pytest

from knowledge_server.server import _resolve_db_path, _store, mcp

INGEST_TOOL_DESCRIPTION = (
    "Ingest a local Markdown, CSV, SQL, Excel, PDF, or DOCX document into a project knowledge base. "
    "Data handling notice: submit only synthetic or approved content. Knowledge Server does not "
    "sanitize, anonymize, or redact sensitive information in submitted documents. Extracted content "
    "is persisted in the configured local SQLite store."
)


def test_server_lists_expected_tools() -> None:
    tools = asyncio.run(mcp.list_tools())
    tool_names = {tool.name for tool in tools}

    assert tool_names == {
        "compare_field_definitions",
        "find_conflicts",
        "delete_document",
        "get_evidence",
        "get_field_evidence_chain",
        "get_suggestion_evidence_chain",
        "ingest_document",
        "list_documents",
        "purge_document",
        "read_document",
        "read_field_catalog",
        "search_across_projects",
        "search_documents",
        "suggest_manifest_candidates",
        "submit_suggestion_decisions",
        "suggest_fields",
    }
    assert len(tools) == 16
    assert all(tool.description for tool in tools)
    ingest_tool = next(tool for tool in tools if tool.name == "ingest_document")
    assert " ".join(ingest_tool.description.split()) == INGEST_TOOL_DESCRIPTION
    purge_tool = next(tool for tool in tools if tool.name == "purge_document")
    assert "compact the FTS5" in " ".join(purge_tool.description.split())
    assert "does not erase source files, backups, snapshots" in purge_tool.description
    assert "Cleanup intent commits with logical deletion" in " ".join(purge_tool.description.split())
    assert "not a power-loss or universal crash-recovery guarantee" in " ".join(purge_tool.description.split())


def test_shared_mode_requires_explicit_ks_db_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDGEFORGE_SHARED_MODE", "1")
    monkeypatch.delenv("EDGEFORGE_KS_DB_PATH", raising=False)

    with pytest.raises(RuntimeError, match="EDGEFORGE_KS_DB_PATH is required"):
        _resolve_db_path()


@pytest.mark.parametrize("value", ["", "0", "false", "False", "no", "off", " OFF "])
def test_shared_mode_false_values_keep_solo_cwd_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    value: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EDGEFORGE_SHARED_MODE", value)
    monkeypatch.delenv("EDGEFORGE_KS_DB_PATH", raising=False)

    assert _resolve_db_path() == str(tmp_path / "edgeforge_knowledge.sqlite3")


def test_solo_mode_without_db_path_opens_cwd_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EDGEFORGE_SHARED_MODE", raising=False)
    monkeypatch.delenv("EDGEFORGE_KS_DB_PATH", raising=False)

    store = _store()
    try:
        assert store.db_path == tmp_path / "edgeforge_knowledge.sqlite3"
    finally:
        store.close()


def test_shared_mode_uses_explicit_ks_db_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "session-ks.sqlite3"
    monkeypatch.setenv("EDGEFORGE_SHARED_MODE", "true")
    monkeypatch.setenv("EDGEFORGE_KS_DB_PATH", str(db_path))

    store = _store()
    try:
        assert store.db_path == db_path
    finally:
        store.close()
