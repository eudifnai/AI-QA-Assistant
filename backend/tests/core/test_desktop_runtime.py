import json
import os

from backend.app.desktop import (
    create_startup_message,
    generate_session_token,
    open_loopback_socket,
    parent_process_is_alive,
)


def test_session_tokens_are_high_entropy_and_unique() -> None:
    first = generate_session_token()
    second = generate_session_token()

    assert first != second
    assert len(first) >= 43
    assert len(second) >= 43


def test_loopback_socket_uses_random_port() -> None:
    listener = open_loopback_socket()
    try:
        host, port = listener.getsockname()
    finally:
        listener.close()

    assert host == "127.0.0.1"
    assert 1024 <= port <= 65535


def test_startup_message_contains_only_connection_material() -> None:
    payload = json.loads(create_startup_message(port=54321, token="session-token"))

    assert payload == {
        "type": "backend_ready",
        "port": 54321,
        "token": "session-token",
    }


def test_parent_process_liveness_is_detected_without_signalling_it() -> None:
    assert parent_process_is_alive(os.getpid()) is True
    assert parent_process_is_alive(2_147_483_647) is False
