from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

ProtoExecutionStatus = Literal[
    "pending", "queued", "running", "passed", "failed", "error", "cancelled", "timeout"
]
ProtoEventLevel = Literal["info", "warning", "error"]
TERMINAL_PROTO_EXECUTION_STATUSES: frozenset[ProtoExecutionStatus] = frozenset(
    {"passed", "failed", "error", "cancelled", "timeout"}
)
PROTO_FIELD_PATH_PATTERN = re.compile(r"^\$(?:\.(?:[A-Za-z_][A-Za-z0-9_]*|\d+))+$")


def build_protobuf_url(base_url: str, path: str) -> str:
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
        raise ValueError("unsafe Protobuf URL")
    try:
        _ = base.port
    except ValueError as exception:
        raise ValueError("invalid Protobuf target port") from exception
    combined_path = f"{base.path.rstrip('/')}{request.path}"
    return urlunsplit((base.scheme, base.netloc, combined_path, request.query, ""))


def _display(value: object) -> str:
    rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return rendered if len(rendered) <= 500 else f"{rendered[:497]}..."


def _field_value(document: object, path: str) -> tuple[bool, object]:
    current = document
    for segment in path.split(".")[1:]:
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit() and int(segment) < len(current):
            current = current[int(segment)]
        else:
            return False, None
    return True, current


@dataclass(frozen=True, slots=True)
class ProtoFieldAssertion:
    path: str
    expected_json: str

    def validate(self) -> ProtoFieldAssertion:
        if PROTO_FIELD_PATH_PATTERN.fullmatch(self.path) is None:
            raise ValueError("invalid Protobuf field path")
        if not self.expected_json or len(self.expected_json) > 4000:
            raise ValueError("invalid Protobuf assertion value")
        try:
            expected = json.loads(self.expected_json)
        except json.JSONDecodeError as exception:
            raise ValueError("invalid Protobuf assertion JSON") from exception
        if isinstance(expected, (dict, list)):
            raise ValueError("Protobuf assertion expected value must be scalar")
        return self


@dataclass(frozen=True, slots=True)
class ProtoFieldAssertionResult:
    path: str
    expected_json: str
    actual: str | None
    passed: bool
    message: str


def evaluate_proto_assertions(
    assertions: tuple[ProtoFieldAssertion, ...], payload: Mapping[str, Any]
) -> tuple[ProtoFieldAssertionResult, ...]:
    results: list[ProtoFieldAssertionResult] = []
    for assertion in assertions:
        assertion.validate()
        found, actual_value = _field_value(payload, assertion.path)
        expected_value = json.loads(assertion.expected_json)
        passed = (
            found and type(actual_value) is type(expected_value) and actual_value == expected_value
        )
        results.append(
            ProtoFieldAssertionResult(
                assertion.path,
                assertion.expected_json,
                _display(actual_value) if found else None,
                passed,
                "字段值符合预期。" if passed else "字段缺失或值与预期不一致。",
            )
        )
    return tuple(results)


@dataclass(frozen=True, slots=True)
class ProtoExecutionStartInput:
    environment_id: str
    asset_id: str
    expected_sha256: str
    service_name: str
    method_name: str
    path: str
    headers: dict[str, str]
    request_payload: dict[str, Any]
    timeout_seconds: int
    assertions: tuple[ProtoFieldAssertion, ...] = ()


@dataclass(frozen=True, slots=True)
class ProtoExecutionEvent:
    id: str
    ordinal: int
    level: ProtoEventLevel
    code: str
    message: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProtoExecution:
    id: str
    workspace_id: str
    environment_id: str | None
    environment_name: str
    asset_id: str | None
    asset_name: str
    asset_sha256: str
    service_name: str
    method_name: str
    base_url: str
    path_template: str
    headers_template: dict[str, str]
    request_message_type: str
    response_message_type: str
    request_payload: dict[str, Any]
    timeout_seconds: int
    assertions: tuple[ProtoFieldAssertion, ...]
    assertion_results: tuple[ProtoFieldAssertionResult, ...]
    status: ProtoExecutionStatus
    progress: int
    pid: int | None
    response_status_code: int | None
    response_headers: dict[str, str]
    response_payload: dict[str, Any] | None
    response_size_bytes: int | None
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    events: tuple[ProtoExecutionEvent, ...]

    @property
    def can_cancel(self) -> bool:
        return self.status not in TERMINAL_PROTO_EXECUTION_STATUSES


@dataclass(frozen=True, slots=True)
class ProtoExecutionInput:
    run_id: str
    environment_id: str
    base_url: str
    variables: dict[str, str]
    secret_names: tuple[str, ...]
    descriptor_set: bytes
    path_template: str
    headers_template: dict[str, str]
    request_message_type: str
    response_message_type: str
    request_payload: dict[str, Any]
    timeout_seconds: int
    assertions: tuple[ProtoFieldAssertion, ...]


@dataclass(frozen=True, slots=True)
class ProtoTransportResult:
    status_code: int
    headers: dict[str, str]
    payload: bytes
    duration_ms: int


@dataclass(frozen=True, slots=True)
class ProtoExecutionResult:
    status_code: int
    headers: dict[str, str]
    payload: dict[str, Any]
    size_bytes: int
    duration_ms: int
    assertion_results: tuple[ProtoFieldAssertionResult, ...]


@dataclass(frozen=True, slots=True)
class ProtoExecutionTaskRequest:
    run_id: str
