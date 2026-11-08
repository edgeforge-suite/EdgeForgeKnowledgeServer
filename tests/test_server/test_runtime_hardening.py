from __future__ import annotations

import json
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import IO

import fastmcp
import pytest

from knowledge_server.safety import allowed_roots_from_env, resolve_allowed_path
from knowledge_server.server import _resolve_db_path, main, mcp

REPO_ROOT = Path(__file__).parents[2].resolve()
UPDATE_PROBE = REPO_ROOT / "tests" / "support" / "runtime_update_probe.py"
HOSTILE_FASTMCP_SETTINGS = {
    "FASTMCP_TRANSPORT": "http",
    "FASTMCP_HOST": "0.0.0.0",
    "FASTMCP_PORT": "39173",
    "FASTMCP_SHOW_SERVER_BANNER": "true",
    "FASTMCP_CHECK_FOR_UPDATES": "stable",
}


def _send(proc: subprocess.Popen[bytes], message: dict[str, object]) -> None:
    assert proc.stdin is not None
    proc.stdin.write((json.dumps(message) + "\n").encode())
    proc.stdin.flush()


def _readline_with_timeout(stream: IO[bytes], timeout: float = 10) -> bytes:
    result: queue.Queue[tuple[bytes | None, Exception | None]] = queue.Queue(maxsize=1)

    def read_line() -> None:
        try:
            result.put((stream.readline(), None))
        except Exception as exc:  # pragma: no cover - defensive pipe boundary
            result.put((None, exc))

    reader = threading.Thread(target=read_line, daemon=True)
    reader.start()
    try:
        line, error = result.get(timeout=timeout)
    except queue.Empty:
        pytest.fail("timed out waiting for stdio MCP response")
    if error is not None:
        raise error
    assert line, "expected JSON-RPC response line from stdio server"
    return line


def _recv(proc: subprocess.Popen[bytes], timeout: float = 10) -> dict[str, object]:
    assert proc.stdout is not None
    line = _readline_with_timeout(proc.stdout, timeout)
    return json.loads(line)


def _clean_child_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("FASTMCP_")}
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{REPO_ROOT}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(REPO_ROOT)
    )
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _launch_server(
    *,
    cwd: Path,
    docs_root: Path,
    db_path: Path,
    extra_env: dict[str, str] | None = None,
    command: list[str] | None = None,
) -> subprocess.Popen[bytes]:
    env = _clean_child_env()
    env["EDGEFORGE_KS_DB_PATH"] = str(db_path)
    env["EDGEFORGE_KS_ALLOWED_ROOTS"] = str(docs_root)
    if extra_env:
        env.update(extra_env)
    return subprocess.Popen(
        command or [sys.executable, "-m", "knowledge_server.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
    )


def _initialize_and_list_tools(proc: subprocess.Popen[bytes]) -> dict[str, object]:
    _send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "runtime-hardening-test", "version": "1.0"},
            },
        },
    )
    initialized = _recv(proc)
    assert "result" in initialized
    _send(
        proc,
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        },
    )
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
    assert len(response["result"]["tools"]) == 16
    return response


def _stop(proc: subprocess.Popen[bytes]) -> str:
    proc.terminate()
    try:
        _, stderr = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        _, stderr = proc.communicate(timeout=5)
    return stderr.decode(errors="replace")


def _linux_listening_sockets(pid: int) -> list[str]:
    socket_inodes: set[str] = set()
    for descriptor in Path(f"/proc/{pid}/fd").iterdir():
        try:
            target = os.readlink(descriptor)
        except OSError:
            continue
        match = re.fullmatch(r"socket:\[(\d+)\]", target)
        if match:
            socket_inodes.add(match.group(1))

    listeners: list[str] = []
    for table_name in ("tcp", "tcp6"):
        table = Path(f"/proc/{pid}/net/{table_name}")
        if not table.exists():
            continue
        for row in table.read_text(encoding="utf-8").splitlines()[1:]:
            columns = row.split()
            if len(columns) > 9 and columns[3] == "0A" and columns[9] in socket_inodes:
                listeners.append(f"{table_name}:{columns[1]}")
    return listeners


def _listening_sockets(pid: int) -> list[str]:
    if Path(f"/proc/{pid}/fd").is_dir():
        return _linux_listening_sockets(pid)

    if os.name == "nt":
        netstat = shutil.which("netstat")
        if not netstat:
            pytest.skip("cannot enumerate Windows child-process sockets: netstat is unavailable")
        return _windows_listening_sockets(pid, netstat)

    lsof = shutil.which("lsof")
    if not lsof:
        pytest.skip("cannot enumerate child-process listening sockets: lsof is unavailable")
    completed = subprocess.run(
        [lsof, "-nP", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN"],
        check=False,
        capture_output=True,
        text=True,
    )
    return [line for line in completed.stdout.splitlines()[1:] if line.strip()]


def _windows_listening_sockets(pid: int, netstat: str) -> list[str]:
    completed = subprocess.run(
        [netstat, "-ano", "-p", "tcp"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        pytest.fail(
            f"Windows child-process socket scan failed with exit code {completed.returncode}"
        )
    listeners: list[str] = []
    for line in completed.stdout.splitlines():
        columns = line.split()
        if (
            len(columns) >= 5
            and columns[0].upper() == "TCP"
            and columns[3].upper() == "LISTENING"
            and columns[4] == str(pid)
        ):
            listeners.append(f"tcp:{columns[1]}")
    return listeners


def _set_or_delete_env(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str | None,
) -> None:
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)


def test_fastmcp_direct_pin_matches_constraints() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    constraints = (REPO_ROOT / "constraints.txt").read_text(encoding="utf-8")
    requirement_lines = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    pyproject_matches = re.findall(r'^\s*"fastmcp==([^"\s]+)",\s*$', pyproject, re.MULTILINE)
    constraint_matches = re.findall(r"^fastmcp==([^\s]+)$", constraints, re.MULTILINE)
    requirements_matches = re.findall(r"^fastmcp==([^\s]+)$", requirement_lines, re.MULTILINE)

    assert len(pyproject_matches) == 1, "pyproject.toml must contain one exact fastmcp pin"
    assert len(constraint_matches) == 1, "constraints.txt must contain one fastmcp pin"
    assert pyproject_matches == constraint_matches, (
        "FastMCP pin drift: pyproject.toml and constraints.txt must pin the same version"
    )
    assert requirements_matches == pyproject_matches, (
        "FastMCP pin drift: requirements.txt must mirror pyproject.toml"
    )


def test_server_masks_error_details() -> None:
    assert mcp._mask_error_details is True


def test_main_forces_stdio_banner_off_and_update_checks_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_arguments: dict[str, object] = {}

    def fake_run(*, transport: str, show_banner: bool) -> None:
        run_arguments.update(transport=transport, show_banner=show_banner)

    monkeypatch.setattr(fastmcp.settings, "transport", "http")
    monkeypatch.setattr(fastmcp.settings, "host", "0.0.0.0")
    monkeypatch.setattr(fastmcp.settings, "port", 39173)
    monkeypatch.setattr(fastmcp.settings, "check_for_updates", "stable")
    monkeypatch.setattr(mcp, "run", fake_run)

    main()

    assert fastmcp.settings.check_for_updates == "off"
    assert run_arguments == {"transport": "stdio", "show_banner": False}


def test_hostile_process_environment_cannot_override_stdio(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    proc = _launch_server(
        cwd=tmp_path,
        docs_root=docs_root,
        db_path=tmp_path / "ks.sqlite3",
        extra_env=HOSTILE_FASTMCP_SETTINGS,
    )
    try:
        response = _initialize_and_list_tools(proc)
        assert response["result"]["tools"]
        assert proc.poll() is None
    finally:
        _stop(proc)


def test_hostile_cwd_dotenv_cannot_override_stdio(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    (tmp_path / ".env").write_text(
        "\n".join(f"{name}={value}" for name, value in HOSTILE_FASTMCP_SETTINGS.items()),
        encoding="utf-8",
    )
    proc = _launch_server(
        cwd=tmp_path,
        docs_root=docs_root,
        db_path=tmp_path / "ks.sqlite3",
    )
    try:
        response = _initialize_and_list_tools(proc)
        assert response["result"]["tools"]
        assert proc.poll() is None
    finally:
        _stop(proc)


def test_stdio_child_has_no_listening_socket_under_hostile_settings(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    (tmp_path / ".env").write_text(
        "\n".join(f"{name}={value}" for name, value in HOSTILE_FASTMCP_SETTINGS.items()),
        encoding="utf-8",
    )
    proc = _launch_server(
        cwd=tmp_path,
        docs_root=docs_root,
        db_path=tmp_path / "ks.sqlite3",
    )
    try:
        _initialize_and_list_tools(proc)
        assert _listening_sockets(proc.pid) == []
    finally:
        _stop(proc)


def test_listener_detector_positive_control() -> None:
    listener_script = (
        "import socket, sys; "
        "listener = socket.socket(); "
        "listener.bind(('127.0.0.1', 0)); "
        "listener.listen(); "
        "print(listener.getsockname()[1], flush=True); "
        "sys.stdin.buffer.read()"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", listener_script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert proc.stdout is not None
        port = int(_readline_with_timeout(proc.stdout).decode().strip())
        listeners = _listening_sockets(proc.pid)
        assert listeners, f"listener detector missed child TCP port {port}"
    finally:
        _stop(proc)


def test_windows_listener_scanner_filters_by_state_and_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    netstat_output = """
      Proto  Local Address          Foreign Address        State           PID
      TCP    0.0.0.0:8123           0.0.0.0:0              LISTENING       4321
      TCP    127.0.0.1:8124         0.0.0.0:0              LISTENING       9999
      TCP    127.0.0.1:8125         127.0.0.1:443          ESTABLISHED     4321
    """

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=netstat_output, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert _windows_listening_sockets(4321, "netstat.exe") == ["tcp:0.0.0.0:8123"]


def test_windows_listener_scanner_fails_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="scanner unavailable",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(pytest.fail.Exception, match="socket scan failed with exit code 1"):
        _windows_listening_sockets(4321, "netstat.exe")


@pytest.mark.parametrize("show_banner", ["0", "1"])
def test_update_check_http_path_is_disabled_with_banner_in_either_state(
    tmp_path: Path,
    show_banner: str,
) -> None:
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    proc = _launch_server(
        cwd=tmp_path,
        docs_root=docs_root,
        db_path=tmp_path / "ks.sqlite3",
        extra_env={
            "FASTMCP_HOME": str(tmp_path / "fastmcp-home"),
            "FASTMCP_CHECK_FOR_UPDATES": "stable",
            "KS_TEST_SHOW_BANNER": show_banner,
        },
        command=[sys.executable, str(UPDATE_PROBE)],
    )
    try:
        _initialize_and_list_tools(proc)
        assert proc.poll() is None
    finally:
        stderr = _stop(proc)
    assert "FastMCP update-check HTTP path was invoked" not in stderr


def test_rejected_ingest_hides_paths_from_client_but_logs_them_locally(tmp_path: Path) -> None:
    allowed_root = tmp_path / "operator-root-sentinel-79f1"
    allowed_root.mkdir()
    candidate = tmp_path / "candidate-path-sentinel-2c6a.md"
    candidate.write_text("not allowed", encoding="utf-8")
    proc = _launch_server(
        cwd=tmp_path,
        docs_root=allowed_root,
        db_path=tmp_path / "ks.sqlite3",
    )
    try:
        _initialize_and_list_tools(proc)
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "ingest_document",
                    "arguments": {
                        "project_id": "runtime-hardening",
                        "file_path": str(candidate),
                        "doc_type": "markdown",
                    },
                },
            },
        )
        response = _recv(proc)
        client_payload = json.dumps(response)
        assert response["result"]["isError"] is True
        assert str(candidate) not in client_payload
        assert str(allowed_root) not in client_payload
    finally:
        stderr = _stop(proc)

    assert str(candidate) in stderr
    assert str(allowed_root) in stderr


@pytest.mark.parametrize(
    "invalid_field",
    ["missing_doc_type", "invalid_path_type", "invalid_decisions_type", "invalid_decision_status"],
)
def test_malformed_tool_call_does_not_reflect_input_values(
    tmp_path: Path, invalid_field: str
) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    candidate_sentinel = "/validation-input-sentinel-S-9C2D"
    tool_name = "ingest_document"
    arguments = {"project_id": "runtime-hardening", "file_path": candidate_sentinel}
    if invalid_field == "invalid_path_type":
        arguments["file_path"] = [candidate_sentinel]
        arguments["doc_type"] = "markdown"
    elif invalid_field.startswith("invalid_decision"):
        tool_name = "submit_suggestion_decisions"
        arguments = {"project_id": "runtime-hardening", "decisions": candidate_sentinel}
        if invalid_field == "invalid_decision_status":
            arguments["decisions"] = [
                {"suggestion_id": candidate_sentinel, "status": candidate_sentinel}
            ]
    proc = _launch_server(
        cwd=tmp_path,
        docs_root=allowed_root,
        db_path=tmp_path / "ks.sqlite3",
    )
    try:
        _initialize_and_list_tools(proc)
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            },
        )
        response = _recv(proc)
        client_payload = json.dumps(response)
        assert response["result"]["isError"] is True
        assert candidate_sentinel not in client_payload
        assert "input_value" not in client_payload
        assert f"Invalid arguments for tool '{tool_name}'" in client_payload
    finally:
        _stop(proc)


def test_resolve_allowed_path_message_is_safe_and_operator_log_has_detail(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    allowed_root = tmp_path / "operator-root-sentinel"
    candidate = tmp_path / "candidate-path-sentinel.md"
    allowed_root.mkdir()
    candidate.write_text("not allowed", encoding="utf-8")

    with caplog.at_level(logging.WARNING), pytest.raises(ValueError) as exc_info:
        resolve_allowed_path(str(candidate), [allowed_root])

    assert str(candidate) not in str(exc_info.value)
    assert str(allowed_root) not in str(exc_info.value)
    assert str(candidate) in caplog.text
    assert str(allowed_root) in caplog.text


def test_rejected_path_log_escapes_control_characters(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    candidate = tmp_path / "rejected\nWARNING:forged-operator-event\x1b[31m"

    with caplog.at_level(logging.WARNING), pytest.raises(ValueError):
        resolve_allowed_path(str(candidate), [allowed_root])

    message = caplog.records[-1].getMessage()
    assert "\n" not in message
    assert "\x1b" not in message
    assert "\\nWARNING:forged-operator-event\\x1b" in message


@pytest.mark.parametrize("db_path", [None, "   "])
def test_shared_mode_missing_or_blank_db_path_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    db_path: str | None,
) -> None:
    monkeypatch.setenv("EDGEFORGE_SHARED_MODE", "1")
    _set_or_delete_env(monkeypatch, "EDGEFORGE_KS_DB_PATH", db_path)

    with pytest.raises(RuntimeError, match="EDGEFORGE_KS_DB_PATH is required"):
        _resolve_db_path()


@pytest.mark.parametrize("allowed_roots", [None, "   "])
def test_shared_mode_missing_or_blank_allowed_roots_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    allowed_roots: str | None,
) -> None:
    monkeypatch.setenv("EDGEFORGE_SHARED_MODE", "1")
    _set_or_delete_env(monkeypatch, "EDGEFORGE_KS_ALLOWED_ROOTS", allowed_roots)

    with pytest.raises(RuntimeError, match="EDGEFORGE_KS_ALLOWED_ROOTS is required"):
        allowed_roots_from_env()


def test_solo_mode_unset_paths_keep_cwd_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EDGEFORGE_SHARED_MODE", raising=False)
    monkeypatch.delenv("EDGEFORGE_KS_DB_PATH", raising=False)
    monkeypatch.delenv("EDGEFORGE_KS_ALLOWED_ROOTS", raising=False)

    assert _resolve_db_path() == str(tmp_path / "edgeforge_knowledge.sqlite3")
    assert allowed_roots_from_env() == [tmp_path.resolve()]
