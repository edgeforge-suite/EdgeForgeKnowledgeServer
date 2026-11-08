from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

INGEST_TOOL_DESCRIPTION = (
    "Ingest a local Markdown, CSV, SQL, Excel, PDF, or DOCX document into a project knowledge base. "
    "Data handling notice: submit only synthetic or approved content. Knowledge Server does not "
    "sanitize, anonymize, or redact sensitive information in submitted documents. Extracted content "
    "is persisted in the configured local SQLite store."
)


def _send(proc: subprocess.Popen[bytes], msg: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
    proc.stdin.flush()


def _recv(proc: subprocess.Popen[bytes]) -> dict:
    assert proc.stdout is not None
    line = proc.stdout.readline()
    assert line, "expected JSON-RPC response line from stdio server"
    return json.loads(line)


def _call(proc: subprocess.Popen[bytes], request_id: int, tool_name: str, arguments: dict) -> dict:
    _send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        },
    )
    response = _recv(proc)
    assert "error" not in response, f"Tool call error: {response['error']}"
    return json.loads(response["result"]["content"][0]["text"])


def _write_dict_csv(path: Path) -> Path:
    """Write a minimal field dictionary CSV for smoke testing."""
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["entity", "field_name", "type", "nullable", "description"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "entity": "Account",
                "field_name": "account_id",
                "type": "string",
                "nullable": "false",
                "description": "Primary account key",
            }
        )
    return path


def _write_conflict_docs(docs_dir: Path) -> list[Path]:
    first = docs_dir / "balance-a.md"
    second = docs_dir / "balance-b.md"
    first.write_text("# Balance Rules\n\nThe balance includes memo credits.\n", encoding="utf-8")
    second.write_text("# Balance Exceptions\n\nThe balance excludes memo credits.\n", encoding="utf-8")
    return [first, second]


def _write_conflict_catalogs(docs_dir: Path) -> list[Path]:
    import csv

    legacy = docs_dir / "legacy-customer.csv"
    catalog = docs_dir / "catalog-customer.csv"
    rows_by_path = {
        legacy: {
            "entity": "CUSTOMER",
            "field_name": "CUSTOMER_ID",
            "type": "VARCHAR",
            "nullable": "false",
            "description": "Customer identifier",
        },
        catalog: {
            "entity": "Customer",
            "field_name": "customerId",
            "type": "string",
            "nullable": "false",
            "description": "Customer identifier",
        },
    }
    for path, row in rows_by_path.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["entity", "field_name", "type", "nullable", "description"],
            )
            writer.writeheader()
            writer.writerow(row)
    return [legacy, catalog]


def _write_portfolio_docs(docs_dir: Path) -> tuple[Path, Path]:
    current = docs_dir / "portfolio-current.md"
    source = docs_dir / "portfolio-source.md"
    current.write_text("# Current\n\nLocal project notes.\n", encoding="utf-8")
    source.write_text("# Balance Pattern\n\nPortfolio balance pattern.\n", encoding="utf-8")
    return current, source


def _write_transform_catalogs(docs_dir: Path) -> tuple[Path, Path]:
    import csv

    source = docs_dir / "transform-source.csv"
    target = docs_dir / "transform-target.csv"
    rows_by_path = {
        source: {
            "entity": "RORequest",
            "field_name": "paymentId",
            "type": "string",
            "nullable": "true",
            "description": "Payment identifier from router source",
        },
        target: {
            "entity": "D1Request",
            "field_name": "payment_id",
            "type": "string",
            "nullable": "true",
            "description": "Payment identifier for router target",
        },
    }
    for path, row in rows_by_path.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["entity", "field_name", "type", "nullable", "description"],
            )
            writer.writeheader()
            writer.writerow(row)
    return source, target


def _write_identity_ddl(docs_dir: Path) -> Path:
    ddl = docs_dir / "identity.sql"
    ddl.write_text(
        """
        CREATE TABLE ACCOUNT (
            account_id VARCHAR2(36) PRIMARY KEY
        );

        CREATE TABLE TRANSACTION_POSTING (
            posting_row_id VARCHAR2(36) PRIMARY KEY,
            account_id VARCHAR2(36) NOT NULL,
            CONSTRAINT fk_posting_account FOREIGN KEY (account_id) REFERENCES ACCOUNT(account_id)
        );
        """,
        encoding="utf-8",
    )
    return ddl


def _launch_server(docs_dir: Path, db_path: Path) -> subprocess.Popen[bytes]:
    repo_root = Path(__file__).parent.parent.parent.resolve()
    env = os.environ.copy()
    env["EDGEFORGE_KS_DB_PATH"] = str(db_path)
    env["EDGEFORGE_KS_ALLOWED_ROOTS"] = str(docs_dir)
    env["FASTMCP_SHOW_SERVER_BANNER"] = "0"
    return subprocess.Popen(
        [sys.executable, "-m", "knowledge_server.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=repo_root,
    )


@pytest.fixture()
def stdio_server(tmp_path: Path) -> dict[str, object]:
    docs_dir = tmp_path / "docs"
    csv_path = _write_dict_csv(docs_dir / "field-dictionary.csv")
    proc = _launch_server(docs_dir, tmp_path / "ks.sqlite3")
    try:
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "ks-smoke-test", "version": "1.0"},
                },
            },
        )
        response = _recv(proc)
        assert "result" in response
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
        )
        yield {"proc": proc, "docs_dir": docs_dir, "csv_path": csv_path}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def test_stdio_initialize_returns_protocol_version(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    _write_dict_csv(docs_dir / "field-dictionary.csv")
    proc = _launch_server(docs_dir, tmp_path / "ks.sqlite3")
    try:
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "ks-smoke-test", "version": "1.0"},
                },
            },
        )
        response = _recv(proc)
        assert "result" in response
        assert response["result"]["protocolVersion"] == "2024-11-05"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def test_stdio_tools_list_returns_all_16_tools(stdio_server: dict[str, object]) -> None:
    proc = stdio_server["proc"]
    _send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        },
    )
    response = _recv(proc)
    tools = response["result"]["tools"]

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 2
    assert len(tools) == 16
    assert {tool["name"] for tool in tools} == {
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
    ingest_tool = next(tool for tool in tools if tool["name"] == "ingest_document")
    assert " ".join(ingest_tool["description"].split()) == INGEST_TOOL_DESCRIPTION
    purge_tool = next(tool for tool in tools if tool["name"] == "purge_document")
    assert "compact the FTS5" in " ".join(purge_tool["description"].split())
    assert "does not erase source files, backups, snapshots" in purge_tool["description"]
    assert "Cleanup intent commits with logical deletion" in " ".join(purge_tool["description"].split())
    assert "not a power-loss or universal crash-recovery guarantee" in " ".join(purge_tool["description"].split())


def test_stdio_ingest_document_returns_success(stdio_server: dict[str, object]) -> None:
    proc = stdio_server["proc"]
    csv_path = stdio_server["csv_path"]

    result = _call(
        proc,
        3,
        "ingest_document",
        {
            "project_id": "smoke-proj",
            "file_path": str(csv_path),
            "doc_type": "csv",
        },
    )

    assert result["success"] is True
    assert result["tool_name"] == "ingest_document"
    assert result["document_id"]
    assert result["field_count"] >= 1
    assert result["warnings"] == []
    assert set(result) == {
        "success",
        "tool_name",
        "project_id",
        "document_id",
        "document_name",
        "doc_type",
        "section_count",
        "field_count",
        "warnings",
    }


def test_stdio_purge_document_requires_confirmation_and_removes_content(
    stdio_server: dict[str, object],
) -> None:
    proc = stdio_server["proc"]
    csv_path = stdio_server["csv_path"]
    ingest = _call(
        proc,
        4,
        "ingest_document",
        {
            "project_id": "purge-proj",
            "file_path": str(csv_path),
            "doc_type": "csv",
        },
    )
    blocked = _call(
        proc,
        5,
        "purge_document",
        {
            "project_id": "purge-proj",
            "document_id": ingest["document_id"],
        },
    )
    evidence_before = _call(
        proc,
        6,
        "get_evidence",
        {"project_id": "purge-proj", "query": "account_id"},
    )
    purged = _call(
        proc,
        7,
        "purge_document",
        {
            "project_id": "purge-proj",
            "document_id": ingest["document_id"],
            "confirm_purge": True,
        },
    )
    evidence_after = _call(
        proc,
        8,
        "get_evidence",
        {"project_id": "purge-proj", "query": "account_id"},
    )
    read_after = _call(
        proc,
        9,
        "read_document",
        {
            "project_id": "purge-proj",
            "document_id": ingest["document_id"],
        },
    )

    assert blocked["success"] is False
    assert "confirm_purge=True is required" in blocked["warnings"][0]
    assert evidence_before["chunk_count"] >= 1
    assert purged["success"] is True
    assert purged["tool_name"] == "purge_document"
    assert evidence_after["chunk_count"] == 0
    assert read_after["success"] is False


def test_stdio_get_field_evidence_chain_returns_composed_result(
    stdio_server: dict[str, object],
) -> None:
    proc = stdio_server["proc"]
    csv_path = stdio_server["csv_path"]

    _call(
        proc,
        3,
        "ingest_document",
        {
            "project_id": "smoke-proj",
            "file_path": str(csv_path),
            "doc_type": "csv",
        },
    )
    result = _call(
        proc,
        4,
        "get_field_evidence_chain",
        {
            "project_id": "smoke-proj",
            "field_name": "account_id",
        },
    )

    assert result["tool_name"] == "get_field_evidence_chain"
    assert result["suggestion"] is not None
    assert result["suggestion"]["suggestion_id"]
    assert result["suggestion"]["status"] == "pending"
    assert result["suggestion"]["entity"] == "Account"
    assert len(result["definitions"]) >= 1
    assert len(result["evidence_chunks"]) >= 1
    assert result["source_count"] >= 1


def test_stdio_submit_suggestion_decisions_persists_status(
    stdio_server: dict[str, object],
) -> None:
    proc = stdio_server["proc"]
    csv_path = stdio_server["csv_path"]

    _call(
        proc,
        6,
        "ingest_document",
        {
            "project_id": "smoke-proj",
            "file_path": str(csv_path),
            "doc_type": "csv",
        },
    )
    suggestions = _call(
        proc,
        7,
        "suggest_fields",
        {
            "project_id": "smoke-proj",
            "field_name_pattern": "account_id",
        },
    )
    suggestion = suggestions["suggestions"][0]
    decision_result = _call(
        proc,
        8,
        "submit_suggestion_decisions",
        {
            "project_id": "smoke-proj",
            "decisions": [
                {
                    "suggestion_id": suggestion["suggestion_id"],
                    "status": "accepted",
                }
            ],
        },
    )
    refreshed = _call(
        proc,
        9,
        "suggest_fields",
        {
            "project_id": "smoke-proj",
            "field_name_pattern": "account_id",
        },
    )

    assert decision_result["tool_name"] == "submit_suggestion_decisions"
    assert decision_result["success"] is True
    assert decision_result["outcomes"][0]["success"] is True
    assert refreshed["suggestions"][0]["suggestion_id"] == suggestion["suggestion_id"]
    assert refreshed["suggestions"][0]["status"] == "accepted"


def test_stdio_suggest_manifest_candidates_fields_scope(
    stdio_server: dict[str, object],
) -> None:
    proc = stdio_server["proc"]
    csv_path = stdio_server["csv_path"]

    _call(
        proc,
        10,
        "ingest_document",
        {
            "project_id": "smoke-proj",
            "file_path": str(csv_path),
            "doc_type": "csv",
        },
    )
    result = _call(
        proc,
        11,
        "suggest_manifest_candidates",
        {
            "project_id": "smoke-proj",
            "scope": "fields",
            "field_name_pattern": "account_id",
        },
    )

    assert result["tool_name"] == "suggest_manifest_candidates"
    assert result["scope"] == "fields"
    assert result["suggestions"]
    assert result["suggestions"][0]["suggestion_id"]
    assert result["suggestions"][0]["field_name"] == "account_id"


def test_stdio_get_suggestion_evidence_chain_fields_scope(
    stdio_server: dict[str, object],
) -> None:
    proc = stdio_server["proc"]
    csv_path = stdio_server["csv_path"]

    _call(
        proc,
        12,
        "ingest_document",
        {
            "project_id": "smoke-proj",
            "file_path": str(csv_path),
            "doc_type": "csv",
        },
    )
    suggestions = _call(
        proc,
        13,
        "suggest_manifest_candidates",
        {
            "project_id": "smoke-proj",
            "scope": "fields",
            "field_name_pattern": "account_id",
        },
    )
    suggestion_id = suggestions["suggestions"][0]["suggestion_id"]
    result = _call(
        proc,
        14,
        "get_suggestion_evidence_chain",
        {
            "project_id": "smoke-proj",
            "suggestion_id": suggestion_id,
            "scope": "fields",
        },
    )

    assert result["tool_name"] == "get_suggestion_evidence_chain"
    assert result["scope"] == "fields"
    assert result["suggestion_id"] == suggestion_id
    assert result["suggestion"]["suggestion_id"] == suggestion_id
    assert result["definitions"]
    assert result["evidence_chunks"]


def test_stdio_suggest_manifest_candidates_validation_scope(
    stdio_server: dict[str, object],
) -> None:
    proc = stdio_server["proc"]
    csv_path = stdio_server["csv_path"]

    _call(
        proc,
        15,
        "ingest_document",
        {
            "project_id": "smoke-proj",
            "file_path": str(csv_path),
            "doc_type": "csv",
        },
    )
    suggestions = _call(
        proc,
        16,
        "suggest_manifest_candidates",
        {
            "project_id": "smoke-proj",
            "scope": "validations",
            "field_name_pattern": "account_id",
        },
    )
    suggestion_id = suggestions["suggestions"][0]["suggestion_id"]
    evidence = _call(
        proc,
        17,
        "get_suggestion_evidence_chain",
        {
            "project_id": "smoke-proj",
            "suggestion_id": suggestion_id,
            "scope": "validations",
        },
    )

    assert suggestions["tool_name"] == "suggest_manifest_candidates"
    assert suggestions["scope"] == "validations"
    assert suggestions["suggestions"][0]["suggestion_type"] == "validation"
    assert evidence["tool_name"] == "get_suggestion_evidence_chain"
    assert evidence["suggestion"]["suggestion_id"] == suggestion_id
    assert evidence["evidence_chunks"]


def test_stdio_suggest_manifest_candidates_conflict_resolution_scope(
    stdio_server: dict[str, object],
) -> None:
    proc = stdio_server["proc"]
    docs_dir = stdio_server["docs_dir"]

    for request_id, path in enumerate(_write_conflict_catalogs(docs_dir), start=18):
        _call(
            proc,
            request_id,
            "ingest_document",
            {
                "project_id": "smoke-proj",
                "file_path": str(path),
                "doc_type": "csv",
            },
        )
    result = _call(
        proc,
        20,
        "suggest_manifest_candidates",
        {
            "project_id": "smoke-proj",
            "scope": "conflict_resolution",
            "field_name_pattern": "customerId",
        },
    )

    assert result["tool_name"] == "suggest_manifest_candidates"
    assert result["scope"] == "conflict_resolution"
    assert result["suggestions"]
    assert result["suggestions"][0]["suggestion_type"] == "conflict_resolution"
    assert result["suggestions"][0]["payload"]["difference_category"] == "compatible normalization"


def test_stdio_get_suggestion_evidence_chain_conflict_resolution_scope(
    stdio_server: dict[str, object],
) -> None:
    proc = stdio_server["proc"]
    docs_dir = stdio_server["docs_dir"]

    for request_id, path in enumerate(_write_conflict_catalogs(docs_dir), start=21):
        _call(
            proc,
            request_id,
            "ingest_document",
            {
                "project_id": "smoke-proj",
                "file_path": str(path),
                "doc_type": "csv",
            },
        )
    suggestions = _call(
        proc,
        23,
        "suggest_manifest_candidates",
        {
            "project_id": "smoke-proj",
            "scope": "conflict_resolution",
            "field_name_pattern": "customerId",
        },
    )
    suggestion_id = suggestions["suggestions"][0]["suggestion_id"]
    evidence = _call(
        proc,
        24,
        "get_suggestion_evidence_chain",
        {
            "project_id": "smoke-proj",
            "suggestion_id": suggestion_id,
            "scope": "conflict_resolution",
        },
    )

    assert evidence["tool_name"] == "get_suggestion_evidence_chain"
    assert evidence["scope"] == "conflict_resolution"
    assert evidence["suggestion"]["suggestion_id"] == suggestion_id
    assert len(evidence["evidence_chunks"]) == 2


def test_stdio_suggest_manifest_candidates_portfolio_reuse_scope(
    stdio_server: dict[str, object],
) -> None:
    proc = stdio_server["proc"]
    docs_dir = stdio_server["docs_dir"]
    current, source = _write_portfolio_docs(docs_dir)

    _call(
        proc,
        25,
        "ingest_document",
        {
            "project_id": "smoke-proj",
            "file_path": str(current),
            "doc_type": "markdown",
        },
    )
    _call(
        proc,
        26,
        "ingest_document",
        {
            "project_id": "portfolio-proj",
            "file_path": str(source),
            "doc_type": "markdown",
        },
    )
    result = _call(
        proc,
        27,
        "suggest_manifest_candidates",
        {
            "project_id": "smoke-proj",
            "scope": "portfolio_reuse",
            "field_name_pattern": "balance",
        },
    )

    assert result["tool_name"] == "suggest_manifest_candidates"
    assert result["scope"] == "portfolio_reuse"
    assert result["suggestions"]
    assert result["suggestions"][0]["suggestion_type"] == "portfolio_reuse"
    assert result["suggestions"][0]["payload"]["matched_project_id"] == "portfolio-proj"


def test_stdio_get_suggestion_evidence_chain_portfolio_reuse_scope(
    stdio_server: dict[str, object],
) -> None:
    proc = stdio_server["proc"]
    docs_dir = stdio_server["docs_dir"]
    current, source = _write_portfolio_docs(docs_dir)

    _call(
        proc,
        28,
        "ingest_document",
        {
            "project_id": "smoke-proj",
            "file_path": str(current),
            "doc_type": "markdown",
        },
    )
    _call(
        proc,
        29,
        "ingest_document",
        {
            "project_id": "portfolio-proj",
            "file_path": str(source),
            "doc_type": "markdown",
        },
    )
    suggestions = _call(
        proc,
        30,
        "suggest_manifest_candidates",
        {
            "project_id": "smoke-proj",
            "scope": "portfolio_reuse",
            "field_name_pattern": "balance",
        },
    )
    suggestion_id = suggestions["suggestions"][0]["suggestion_id"]
    evidence = _call(
        proc,
        31,
        "get_suggestion_evidence_chain",
        {
            "project_id": "smoke-proj",
            "suggestion_id": suggestion_id,
            "scope": "portfolio_reuse",
        },
    )

    assert evidence["tool_name"] == "get_suggestion_evidence_chain"
    assert evidence["scope"] == "portfolio_reuse"
    assert evidence["suggestion"]["suggestion_id"] == suggestion_id
    assert len(evidence["evidence_chunks"]) == 1


def test_stdio_transform_scope_suggests_evidence_and_decisions(
    stdio_server: dict[str, object],
) -> None:
    proc = stdio_server["proc"]
    docs_dir = stdio_server["docs_dir"]
    source, target = _write_transform_catalogs(docs_dir)

    _call(
        proc,
        32,
        "ingest_document",
        {
            "project_id": "smoke-proj",
            "file_path": str(source),
            "doc_type": "csv",
        },
    )
    _call(
        proc,
        33,
        "ingest_document",
        {
            "project_id": "smoke-proj",
            "file_path": str(target),
            "doc_type": "csv",
        },
    )
    suggestions = _call(
        proc,
        34,
        "suggest_manifest_candidates",
        {
            "project_id": "smoke-proj",
            "scope": "transforms",
            "route_name": "payment_router",
            "source_entity": "RORequest",
            "target_entity": "D1Request",
            "target_id": "ledger-core",
            "direction": "request",
        },
    )
    suggestion = suggestions["suggestions"][0]
    evidence = _call(
        proc,
        35,
        "get_suggestion_evidence_chain",
        {
            "project_id": "smoke-proj",
            "suggestion_id": suggestion["suggestion_id"],
            "scope": "transforms",
        },
    )
    decision_result = _call(
        proc,
        36,
        "submit_suggestion_decisions",
        {
            "project_id": "smoke-proj",
            "decisions": [
                {
                    "suggestion_id": suggestion["suggestion_id"],
                    "status": "edited",
                    "edited_payload": {
                        "source": "$.paymentId",
                        "target": "$.payment_id",
                        "rationale": "Reviewed router transform suggestion.",
                    },
                }
            ],
        },
    )

    assert suggestions["tool_name"] == "suggest_manifest_candidates"
    assert suggestions["scope"] == "transforms"
    assert suggestion["suggestion_type"] == "transform"
    assert suggestion["payload"]["manifest_path"] == (
        "async_routes.payment_router.router_config.targets.ledger-core.request_transform"
    )
    assert evidence["tool_name"] == "get_suggestion_evidence_chain"
    assert evidence["scope"] == "transforms"
    assert evidence["suggestion"]["suggestion_id"] == suggestion["suggestion_id"]
    assert len(evidence["evidence_chunks"]) == 2
    assert decision_result["tool_name"] == "submit_suggestion_decisions"
    assert decision_result["success"] is True
    assert decision_result["outcomes"][0]["success"] is True


def test_stdio_identity_role_scope_suggests_and_returns_evidence(
    stdio_server: dict[str, object],
) -> None:
    proc = stdio_server["proc"]
    docs_dir = stdio_server["docs_dir"]
    ddl = _write_identity_ddl(docs_dir)

    _call(
        proc,
        37,
        "ingest_document",
        {
            "project_id": "smoke-proj",
            "file_path": str(ddl),
            "doc_type": "sql",
        },
    )
    suggestions = _call(
        proc,
        38,
        "suggest_manifest_candidates",
        {
            "project_id": "smoke-proj",
            "scope": "identity_role",
            "entity": "TRANSACTION_POSTING",
        },
    )
    suggestion = suggestions["suggestions"][0]
    evidence = _call(
        proc,
        39,
        "get_suggestion_evidence_chain",
        {
            "project_id": "smoke-proj",
            "suggestion_id": suggestion["suggestion_id"],
            "scope": "identity_role",
        },
    )

    assert suggestions["tool_name"] == "suggest_manifest_candidates"
    assert suggestions["scope"] == "identity_role"
    assert suggestion["suggestion_type"] == "identity_role"
    assert suggestion["payload"]["suggested_role"] in {"persistence_id", "parent_reference"}
    assert suggestion["payload"]["signals"]
    assert evidence["tool_name"] == "get_suggestion_evidence_chain"
    assert evidence["scope"] == "identity_role"
    assert evidence["suggestion"]["suggestion_id"] == suggestion["suggestion_id"]
    assert evidence["evidence_chunks"]


def test_stdio_unknown_project_returns_empty_evidence_chain(
    stdio_server: dict[str, object],
) -> None:
    proc = stdio_server["proc"]

    result = _call(
        proc,
        5,
        "get_field_evidence_chain",
        {
            "project_id": "no-such-project",
            "field_name": "account_id",
        },
    )

    assert result["suggestion"] is None
    assert result["definitions"] == []
    assert result["evidence_chunks"] == []
    assert result["source_count"] == 0
    assert len(result["warnings"]) >= 1
