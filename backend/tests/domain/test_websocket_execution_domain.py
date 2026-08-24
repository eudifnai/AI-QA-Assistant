from datetime import UTC, datetime

import pytest

from backend.app.domain.websocket_execution import (
    WebSocketExecution,
    WebSocketMessage,
    WebSocketMessageAssertion,
    build_websocket_url,
    evaluate_websocket_assertions,
)


def test_websocket_url_uses_matching_secure_scheme_and_frozen_base_path() -> None:
    assert (
        build_websocket_url("https://api.example.test/v1", "/events?room=42")
        == "wss://api.example.test/v1/events?room=42"
    )
    assert build_websocket_url("http://127.0.0.1:9000", "/socket") == ("ws://127.0.0.1:9000/socket")


@pytest.mark.parametrize("path", ["socket", "//other.example/socket", "/bad#fragment"])
def test_websocket_url_rejects_paths_that_can_replace_or_fragment_target(path: str) -> None:
    with pytest.raises(ValueError):
        build_websocket_url("https://api.example.test", path)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://user:password@api.example.test",
        "https://api.example.test?target=other",
        "https://api.example.test#fragment",
        "https://api.example.test:bad",
    ],
)
def test_websocket_url_defensively_rejects_unsafe_frozen_base(base_url: str) -> None:
    with pytest.raises(ValueError):
        build_websocket_url(base_url, "/socket")


def test_terminal_websocket_execution_cannot_be_cancelled() -> None:
    run = WebSocketExecution(
        id="run-1",
        workspace_id="workspace-1",
        environment_id="environment-1",
        environment_name="开发环境",
        base_url="https://api.example.test",
        path_template="/socket",
        headers_template={},
        variables={},
        secret_names=(),
        message_template="hello",
        timeout_seconds=10,
        status="passed",
        progress=100,
        pid=None,
        response_message="world",
        response_encoding="text",
        response_size_bytes=5,
        duration_ms=12,
        error_code=None,
        error_message=None,
        created_at=datetime(2026, 8, 16, tzinfo=UTC),
        started_at=None,
        finished_at=datetime(2026, 8, 16, tzinfo=UTC),
        events=(),
    )

    assert run.can_cancel is False


def test_message_sequence_assertions_support_encoding_text_and_typed_json() -> None:
    responses = (
        WebSocketMessage(0, '{"state":"ready","count":1}', "text", 27),
        WebSocketMessage(1, "done", "text", 4),
        WebSocketMessage(2, "/wA=", "base64", 2),
    )
    assertions = (
        WebSocketMessageAssertion(0, "json_path_equals", "$.count", "1").validate(),
        WebSocketMessageAssertion(1, "text_equals", None, "done").validate(),
        WebSocketMessageAssertion(1, "text_contains", None, "on").validate(),
        WebSocketMessageAssertion(2, "encoding", None, "base64").validate(),
    )

    results = evaluate_websocket_assertions(assertions, responses)

    assert [item.passed for item in results] == [True, True, True, True]


def test_sequence_assertion_reports_missing_message_and_strict_type_mismatch() -> None:
    responses = (WebSocketMessage(0, '{"count":1}', "text", 11),)
    assertions = (
        WebSocketMessageAssertion(1, "text_equals", None, "later").validate(),
        WebSocketMessageAssertion(0, "json_path_equals", "$.count", '"1"').validate(),
    )

    results = evaluate_websocket_assertions(assertions, responses)

    assert results[0].actual is None
    assert results[0].passed is False
    assert results[1].actual == "1"
    assert results[1].passed is False


@pytest.mark.parametrize(
    "assertion",
    [
        WebSocketMessageAssertion(-1, "text_equals", None, "x"),
        WebSocketMessageAssertion(0, "encoding", None, "binary"),
        WebSocketMessageAssertion(0, "json_path_equals", "count", "1"),
        WebSocketMessageAssertion(0, "json_path_equals", "$.count", "{}"),
        WebSocketMessageAssertion(0, "text_contains", "$.x", "x"),
    ],
)
def test_message_sequence_assertion_rejects_invalid_contract(
    assertion: WebSocketMessageAssertion,
) -> None:
    with pytest.raises(ValueError):
        assertion.validate()
