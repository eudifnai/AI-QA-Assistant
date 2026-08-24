from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

WebSocketExecutionStatus = Literal[
    "pending", "queued", "running", "passed", "failed", "error", "cancelled", "timeout"
]
WebSocketEventLevel = Literal["info", "warning", "error"]
WebSocketAssertionKind = Literal["encoding", "text_equals", "text_contains", "json_path_equals"]
WEBSOCKET_JSON_PATH_PATTERN = re.compile(r"^\$(?:\.(?:[A-Za-z_][A-Za-z0-9_-]*|\d+))+$")
TERMINAL_WEBSOCKET_EXECUTION_STATUSES: frozenset[WebSocketExecutionStatus] = frozenset(
    {"passed", "failed", "error", "cancelled", "timeout"}
)


def build_websocket_url(base_url: str, path: str) -> str:
    base = urlsplit(base_url)
    request = urlsplit(path)
    if (
        base.scheme not in {"http", "https"}
        or not base.hostname
        or base.username is not None
        or base.password is not None
        or base.query
        or base.fragment
        or request.scheme
        or request.netloc
        or not request.path.startswith("/")
        or request.path.startswith("//")
        or request.fragment
        or "\r" in path
        or "\n" in path
    ):
        raise ValueError("unsafe WebSocket URL")
    try:
        _ = base.port
    except ValueError as exception:
        raise ValueError("invalid WebSocket target port") from exception
    scheme = "wss" if base.scheme == "https" else "ws"
    combined_path = f"{base.path.rstrip('/')}{request.path}"
    return urlunsplit((scheme, base.netloc, combined_path, request.query, ""))


@dataclass(frozen=True, slots=True)
class WebSocketExecutionStartInput:
    environment_id: str
    path: str
    headers: dict[str, str]
    message: str
    timeout_seconds: int
    additional_messages: tuple[str, ...] = ()
    receive_count: int = 1
    ping_interval_seconds: int | None = None
    max_reconnect_attempts: int = 0
    assertions: tuple[WebSocketMessageAssertion, ...] = ()


@dataclass(frozen=True, slots=True)
class WebSocketMessage:
    ordinal: int
    message: str
    encoding: Literal["text", "base64"]
    size_bytes: int


@dataclass(frozen=True, slots=True)
class WebSocketMessageAssertion:
    message_index: int
    kind: WebSocketAssertionKind
    path: str | None
    expected: str

    def validate(self) -> WebSocketMessageAssertion:
        if not 0 <= self.message_index < 20 or not self.expected or len(self.expected) > 4000:
            raise ValueError("invalid WebSocket assertion")
        if self.kind == "encoding":
            if self.path is not None or self.expected not in {"text", "base64"}:
                raise ValueError("invalid WebSocket encoding assertion")
        elif self.kind in {"text_equals", "text_contains"}:
            if self.path is not None:
                raise ValueError("invalid WebSocket text assertion")
        elif self.kind == "json_path_equals":
            if self.path is None or WEBSOCKET_JSON_PATH_PATTERN.fullmatch(self.path) is None:
                raise ValueError("invalid WebSocket JSON path assertion")
            try:
                expected = json.loads(self.expected)
            except json.JSONDecodeError as exception:
                raise ValueError("invalid WebSocket JSON assertion") from exception
            if isinstance(expected, (dict, list)):
                raise ValueError("WebSocket JSON assertion expected value must be scalar")
        else:
            raise ValueError("unsupported WebSocket assertion")
        return self


@dataclass(frozen=True, slots=True)
class WebSocketMessageAssertionResult:
    message_index: int
    kind: WebSocketAssertionKind
    path: str | None
    expected: str
    actual: str | None
    passed: bool
    message: str


def _display(value: object) -> str:
    rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return rendered if len(rendered) <= 500 else f"{rendered[:497]}..."


def _json_path_value(document: object, path: str) -> tuple[bool, object]:
    current = document
    for segment in path.split(".")[1:]:
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit() and int(segment) < len(current):
            current = current[int(segment)]
        else:
            return False, None
    return True, current


def evaluate_websocket_assertions(
    assertions: tuple[WebSocketMessageAssertion, ...],
    responses: tuple[WebSocketMessage, ...],
) -> tuple[WebSocketMessageAssertionResult, ...]:
    results: list[WebSocketMessageAssertionResult] = []
    for assertion in assertions:
        assertion.validate()
        response = (
            responses[assertion.message_index] if assertion.message_index < len(responses) else None
        )
        actual: str | None = None
        passed = False
        if response is not None and assertion.kind == "encoding":
            actual = response.encoding
            passed = actual == assertion.expected
        elif response is not None and assertion.kind in {"text_equals", "text_contains"}:
            if response.encoding == "text":
                actual = response.message
                passed = (
                    actual == assertion.expected
                    if assertion.kind == "text_equals"
                    else assertion.expected in actual
                )
        elif response is not None and assertion.kind == "json_path_equals":
            if response.encoding == "text":
                try:
                    document: Any = json.loads(response.message)
                except json.JSONDecodeError:
                    document = None
                found, value = _json_path_value(document, assertion.path or "")
                if found:
                    actual = _display(value)
                    expected_value = json.loads(assertion.expected)
                    passed = value == expected_value and type(value) is type(expected_value)
        results.append(
            WebSocketMessageAssertionResult(
                assertion.message_index,
                assertion.kind,
                assertion.path,
                assertion.expected,
                actual,
                passed,
                "消息断言通过。" if passed else "消息缺失、编码不匹配或内容与预期不一致。",
            )
        )
    return tuple(results)


@dataclass(frozen=True, slots=True)
class WebSocketExecutionEvent:
    id: str
    ordinal: int
    level: WebSocketEventLevel
    code: str
    message: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class WebSocketExecution:
    id: str
    workspace_id: str
    environment_id: str | None
    environment_name: str
    base_url: str
    path_template: str
    headers_template: dict[str, str]
    variables: dict[str, str]
    secret_names: tuple[str, ...]
    message_template: str
    timeout_seconds: int
    status: WebSocketExecutionStatus
    progress: int
    pid: int | None
    response_message: str | None
    response_encoding: Literal["text", "base64"] | None
    response_size_bytes: int | None
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    events: tuple[WebSocketExecutionEvent, ...]
    additional_message_templates: tuple[str, ...] = ()
    receive_count: int = 1
    ping_interval_seconds: int | None = None
    max_reconnect_attempts: int = 0
    responses: tuple[WebSocketMessage, ...] = ()
    assertions: tuple[WebSocketMessageAssertion, ...] = ()
    assertion_results: tuple[WebSocketMessageAssertionResult, ...] = ()
    attempt_count: int = 1

    @property
    def can_cancel(self) -> bool:
        return self.status not in TERMINAL_WEBSOCKET_EXECUTION_STATUSES


@dataclass(frozen=True, slots=True)
class WebSocketExecutionInput:
    base_url: str
    path_template: str
    headers_template: dict[str, str]
    variables: dict[str, str]
    secret_names: tuple[str, ...]
    message_template: str
    timeout_seconds: int
    additional_message_templates: tuple[str, ...] = ()
    receive_count: int = 1
    ping_interval_seconds: int | None = None
    max_reconnect_attempts: int = 0
    assertions: tuple[WebSocketMessageAssertion, ...] = ()


@dataclass(frozen=True, slots=True)
class WebSocketExecutionResult:
    message: str
    encoding: Literal["text", "base64"]
    size_bytes: int
    duration_ms: int
    responses: tuple[WebSocketMessage, ...] = ()
    assertion_results: tuple[WebSocketMessageAssertionResult, ...] = ()
    attempt_count: int = 1


@dataclass(frozen=True, slots=True)
class WebSocketExecutionTaskRequest:
    run_id: str
