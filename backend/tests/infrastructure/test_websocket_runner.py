from __future__ import annotations

from typing import Any

import pytest

from backend.app.infrastructure.websocket_runner import WebSocketRunner, WebSocketRunnerError


class FakeConnection:
    def __init__(self, response: str | bytes) -> None:
        self.response = response
        self.sent: list[str] = []

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def send(self, message: str) -> None:
        self.sent.append(message)

    def recv(self, timeout: float | None = None) -> str | bytes:
        assert timeout == 8
        return self.response


class SequenceConnection(FakeConnection):
    def __init__(self, responses: list[str | bytes]) -> None:
        super().__init__("")
        self.responses = iter(responses)

    def recv(self, timeout: float | None = None) -> str | bytes:
        assert timeout == 8
        return next(self.responses)


def test_websocket_runner_disables_proxy_and_redacts_text_response() -> None:
    connection = FakeConnection("token=top-secret")
    captured: dict[str, Any] = {}

    def connect(uri: str, **kwargs: Any) -> FakeConnection:
        captured.update(uri=uri, **kwargs)
        return connection

    result = WebSocketRunner(connect).execute(
        url="wss://api.example.test/socket",
        headers={"Authorization": "Bearer top-secret"},
        message="hello",
        timeout_seconds=8,
        secrets=("top-secret",),
    )

    assert connection.sent == ["hello"]
    assert result.message == "token=***"
    assert result.encoding == "text"
    assert captured["proxy"] is None
    assert captured["max_size"] == 2 * 1024 * 1024
    assert "top-secret" not in repr(result)


def test_websocket_runner_encodes_binary_response() -> None:
    result = WebSocketRunner(lambda *_args, **_kwargs: FakeConnection(b"\xff\x00")).execute(
        url="ws://127.0.0.1:9000/socket",
        headers={},
        message="hello",
        timeout_seconds=8,
        secrets=(),
    )

    assert result.message == "/wA="
    assert result.encoding == "base64"
    assert result.size_bytes == 2


def test_websocket_runner_maps_receive_timeout_to_safe_reason() -> None:
    class TimeoutConnection(FakeConnection):
        def recv(self, timeout: float | None = None) -> str:
            raise TimeoutError

    with pytest.raises(WebSocketRunnerError, match="timeout") as raised:
        WebSocketRunner(lambda *_args, **_kwargs: TimeoutConnection("unused")).execute(
            url="wss://api.example.test/socket",
            headers={},
            message="hello",
            timeout_seconds=8,
            secrets=(),
        )
    assert raised.value.reason == "timeout"


def test_websocket_runner_sends_and_receives_ordered_sequences_with_ping() -> None:
    connection = SequenceConnection(['{"state":"ready"}', "done", b"\xff\x00"])
    captured: dict[str, Any] = {}

    def connect(uri: str, **kwargs: Any) -> SequenceConnection:
        captured.update(uri=uri, **kwargs)
        return connection

    result = WebSocketRunner(connect).execute(
        url="wss://api.example.test/socket",
        headers={},
        message="subscribe",
        additional_messages=("next", "finish"),
        receive_count=3,
        ping_interval_seconds=15,
        max_reconnect_attempts=0,
        timeout_seconds=8,
        secrets=(),
    )

    assert connection.sent == ["subscribe", "next", "finish"]
    assert [item.ordinal for item in result.responses] == [0, 1, 2]
    assert [item.encoding for item in result.responses] == ["text", "text", "base64"]
    assert result.message == '{"state":"ready"}'
    assert result.attempt_count == 1
    assert captured["ping_interval"] == 15
    assert captured["ping_timeout"] == 15


def test_websocket_runner_reconnects_once_only_for_transport_failure() -> None:
    attempts = 0

    def connect(_uri: str, **_kwargs: Any) -> FakeConnection:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("unavailable")
        return FakeConnection("ack")

    result = WebSocketRunner(connect).execute(
        url="wss://api.example.test/socket",
        headers={},
        message="idempotent subscribe",
        additional_messages=(),
        receive_count=1,
        ping_interval_seconds=None,
        max_reconnect_attempts=1,
        timeout_seconds=8,
        secrets=(),
    )

    assert attempts == 2
    assert result.attempt_count == 2


def test_websocket_runner_does_not_reconnect_an_oversized_message() -> None:
    attempts = 0

    def connect(_uri: str, **_kwargs: Any) -> FakeConnection:
        nonlocal attempts
        attempts += 1
        return FakeConnection("x" * (2 * 1024 * 1024 + 1))

    with pytest.raises(WebSocketRunnerError) as raised:
        WebSocketRunner(connect).execute(
            url="wss://api.example.test/socket",
            headers={},
            message="hello",
            additional_messages=(),
            receive_count=1,
            ping_interval_seconds=None,
            max_reconnect_attempts=1,
            timeout_seconds=8,
            secrets=(),
        )

    assert raised.value.reason == "response_too_large"
    assert attempts == 1
