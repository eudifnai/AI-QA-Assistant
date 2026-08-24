import contextlib
import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from backend.app.core.network import API_LOOPBACK_HOST
from backend.app.desktop import (
    PARENT_HEARTBEAT_ENVIRONMENT_VARIABLE,
    create_startup_message,
    generate_session_token,
    parent_heartbeat_is_current,
)


def _linux_listening_ipv4_addresses(port: int) -> set[str]:
    addresses: set[str] = set()
    for line in Path("/proc/net/tcp").read_text(encoding="ascii").splitlines()[1:]:
        fields = line.split()
        local_address, local_port = fields[1].split(":")
        if int(local_port, 16) == port and fields[3] == "0A":
            addresses.add(socket.inet_ntoa(bytes.fromhex(local_address)[::-1]))
    return addresses


def _windows_listening_ipv4_addresses(port: int) -> set[str]:
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    addresses: set[str] = set()
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0].upper() != "TCP" or fields[2] != "0.0.0.0:0":
            continue
        local_address, separator, local_port = fields[1].rpartition(":")
        if separator and local_port == str(port):
            addresses.add(local_address)
    return addresses


def _listening_ipv4_addresses(port: int, process_id: int) -> set[str]:
    if sys.platform == "win32":
        return _windows_listening_ipv4_addresses(port)
    if sys.platform.startswith("linux"):
        return _linux_listening_ipv4_addresses(port)
    pytest.skip("监听地址证据当前只支持 Windows 和 Linux。")


def test_session_tokens_are_high_entropy_and_unique() -> None:
    first = generate_session_token()
    second = generate_session_token()

    assert first != second
    assert len(first) >= 43
    assert len(second) >= 43


def test_parent_heartbeat_expires(tmp_path: Path) -> None:
    heartbeat_path = tmp_path / "parent.heartbeat"
    heartbeat_path.touch()

    assert parent_heartbeat_is_current(
        heartbeat_path,
        current_time=heartbeat_path.stat().st_mtime + 4.9,
    )
    assert not parent_heartbeat_is_current(
        heartbeat_path,
        current_time=heartbeat_path.stat().st_mtime + 5.1,
    )


def test_desktop_server_listens_only_on_ipv4_loopback_and_accepts_authenticated_connections(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "profile" / "ai_qa_assistant.db"
    heartbeat_path = tmp_path / "runtime" / "parent.heartbeat"
    heartbeat_path.parent.mkdir()
    heartbeat_path.touch()
    environment = {
        **os.environ,
        "AI_QA_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
        PARENT_HEARTBEAT_ENVIRONMENT_VARIABLE: str(heartbeat_path),
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "backend.app.desktop",
        ],
        cwd=Path(__file__).resolve().parents[3],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    )
    try:
        assert process.stdout is not None
        with ThreadPoolExecutor(max_workers=1) as executor:
            startup_line = executor.submit(process.stdout.readline).result(timeout=20)
        connection = json.loads(startup_line)
        assert _listening_ipv4_addresses(connection["port"], process.pid) == {API_LOOPBACK_HOST}
        url = f"http://{API_LOOPBACK_HOST}:{connection['port']}/health"

        invalid_request = urllib.request.Request(
            url,
            headers={"Authorization": "Bearer invalid", "Connection": "close"},
        )
        try:
            urllib.request.urlopen(invalid_request, timeout=5)
        except urllib.error.HTTPError as exception:
            assert exception.code == 401
        else:
            raise AssertionError("invalid desktop token must be rejected")

        for _ in range(2):
            request = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {connection['token']}",
                    "Connection": "close",
                },
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                assert response.status == 200
        heartbeat_path.unlink()
        assert process.wait(timeout=10) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        with contextlib.suppress(FileNotFoundError):
            heartbeat_path.unlink()

    assert database_path.is_file()


def test_startup_message_contains_only_connection_material() -> None:
    payload = json.loads(create_startup_message(port=54321, token="session-token"))

    assert payload == {
        "type": "backend_ready",
        "port": 54321,
        "token": "session-token",
    }
