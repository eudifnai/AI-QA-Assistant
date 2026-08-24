from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

HttpExecutionStatus = Literal[
    "pending", "queued", "running", "passed", "failed", "error", "cancelled", "timeout"
]
HttpMethod = Literal["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
HttpAssertionKind = Literal["status_code", "header_equals", "body_contains", "json_path_equals"]
HttpEventLevel = Literal["info", "warning", "error"]
TERMINAL_HTTP_EXECUTION_STATUSES: frozenset[HttpExecutionStatus] = frozenset(
    {"passed", "failed", "error", "cancelled", "timeout"}
)
HTTP_METHODS: frozenset[str] = frozenset(
    {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"}
)
VARIABLE_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
TEMPLATE_REFERENCE_PATTERN = re.compile(r"{{(secret\.)?([A-Z][A-Z0-9_]{0,63})}}")
JSON_PATH_PATTERN = re.compile(r"^\$(?:\.(?:[A-Za-z_][A-Za-z0-9_-]*|\d+))+$")


class HttpTemplateError(ValueError):
    pass


def validate_variable_name(name: str) -> str:
    if VARIABLE_NAME_PATTERN.fullmatch(name) is None:
        raise ValueError("invalid variable name")
    return name


def validate_and_normalize_base_url(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("unsafe HTTP base URL")
    try:
        _ = parsed.port
    except ValueError as exception:
        raise ValueError("invalid HTTP base URL port") from exception
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def resolve_template(
    template: str,
    *,
    variables: Mapping[str, str],
    secrets: Mapping[str, str],
) -> str:
    cursor = 0
    resolved: list[str] = []
    for match in TEMPLATE_REFERENCE_PATTERN.finditer(template):
        prefix = template[cursor : match.start()]
        if "{{" in prefix or "}}" in prefix:
            raise HttpTemplateError("malformed template reference")
        resolved.append(prefix)
        secret_prefix, name = match.groups()
        source = secrets if secret_prefix else variables
        if name not in source:
            raise HttpTemplateError("template reference is not configured")
        resolved.append(source[name])
        cursor = match.end()
    suffix = template[cursor:]
    if "{{" in suffix or "}}" in suffix:
        raise HttpTemplateError("malformed template reference")
    resolved.append(suffix)
    return "".join(resolved)


def redact_secrets(value: str, secrets: list[str] | tuple[str, ...]) -> str:
    redacted = value
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        redacted = redacted.replace(secret, "***")
    return redacted


@dataclass(frozen=True, slots=True)
class HttpAssertion:
    kind: HttpAssertionKind
    target: str | None
    expected: str

    def validate(self) -> HttpAssertion:
        if not self.expected or len(self.expected) > 4000:
            raise ValueError("invalid assertion expected value")
        if self.kind == "status_code":
            if self.target is not None or not self.expected.isdigit():
                raise ValueError("invalid status assertion")
            expected_status = int(self.expected)
            if not 100 <= expected_status <= 599:
                raise ValueError("invalid expected status")
        elif self.kind == "header_equals":
            if self.target is None or not self.target or len(self.target) > 128:
                raise ValueError("invalid header assertion")
        elif self.kind == "body_contains":
            if self.target is not None:
                raise ValueError("invalid body assertion")
        elif self.kind == "json_path_equals":
            if self.target is None or JSON_PATH_PATTERN.fullmatch(self.target) is None:
                raise ValueError("invalid JSON path assertion")
            expected = json.loads(self.expected)
            if isinstance(expected, (dict, list)):
                raise ValueError("JSON assertion expected value must be scalar")
        else:
            raise ValueError("unsupported assertion kind")
        return self


@dataclass(frozen=True, slots=True)
class HttpAssertionResult:
    kind: HttpAssertionKind
    target: str | None
    expected: str
    actual: str | None
    passed: bool
    message: str


@dataclass(frozen=True, slots=True)
class HttpExecutionEvent:
    id: str
    ordinal: int
    level: HttpEventLevel
    code: str
    message: str
    attempt: int | None
    created_at: datetime


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


def evaluate_http_assertions(
    assertions: tuple[HttpAssertion, ...],
    *,
    status_code: int,
    headers: Mapping[str, str],
    body: str,
    body_encoding: Literal["text", "base64"],
) -> tuple[HttpAssertionResult, ...]:
    normalized_headers = {name.casefold(): value for name, value in headers.items()}
    parsed_body: object | None = None
    parsed_body_ready = False
    results: list[HttpAssertionResult] = []
    for assertion in assertions:
        assertion.validate()
        actual: str | None = None
        passed = False
        message = "断言未通过。"
        if assertion.kind == "status_code":
            actual = str(status_code)
            passed = actual == assertion.expected
            message = "HTTP 状态码符合预期。" if passed else "HTTP 状态码与预期不一致。"
        elif assertion.kind == "header_equals":
            actual = normalized_headers.get((assertion.target or "").casefold())
            passed = actual == assertion.expected
            message = "响应头符合预期。" if passed else "响应头缺失或与预期不一致。"
        elif assertion.kind == "body_contains":
            if body_encoding == "text":
                passed = assertion.expected in body
                message = "响应正文包含预期文本。" if passed else "响应正文未包含预期文本。"
            else:
                message = "二进制响应不支持正文包含断言。"
        elif assertion.kind == "json_path_equals":
            if body_encoding != "text":
                message = "二进制响应不支持 JSON 路径断言。"
            else:
                if not parsed_body_ready:
                    try:
                        parsed_body = json.loads(body)
                    except json.JSONDecodeError:
                        parsed_body = None
                    parsed_body_ready = True
                found, value = _json_path_value(parsed_body, assertion.target or "")
                if found:
                    actual = _display(value)
                    expected_value = json.loads(assertion.expected)
                    passed = value == expected_value and type(value) is type(expected_value)
                message = "JSON 路径值符合预期。" if passed else "JSON 路径缺失或值不一致。"
        results.append(
            HttpAssertionResult(
                assertion.kind,
                assertion.target,
                assertion.expected,
                actual,
                passed,
                message,
            )
        )
    return tuple(results)


@dataclass(frozen=True, slots=True)
class HttpEnvironment:
    id: str
    workspace_id: str
    name: str
    base_url: str
    variables: dict[str, str]
    secret_names: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class HttpEnvironmentInput:
    name: str
    base_url: str
    variables: dict[str, str]


@dataclass(frozen=True, slots=True)
class HttpExecutionStartInput:
    environment_id: str
    method: HttpMethod
    path: str
    headers: dict[str, str]
    body: str | None
    timeout_seconds: int
    max_attempts: int = 1
    assertions: tuple[HttpAssertion, ...] = ()


@dataclass(frozen=True, slots=True)
class HttpExecution:
    id: str
    workspace_id: str
    environment_id: str | None
    environment_name: str
    method: HttpMethod
    base_url: str
    path_template: str
    headers_template: dict[str, str]
    body_template: str | None
    timeout_seconds: int
    status: HttpExecutionStatus
    progress: int
    pid: int | None
    response_status_code: int | None
    response_headers: dict[str, str]
    response_body: str | None
    response_body_encoding: Literal["text", "base64"] | None
    response_size_bytes: int | None
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    max_attempts: int = 1
    assertions: tuple[HttpAssertion, ...] = ()
    assertion_results: tuple[HttpAssertionResult, ...] = ()
    events: tuple[HttpExecutionEvent, ...] = ()

    @property
    def can_cancel(self) -> bool:
        return self.status not in TERMINAL_HTTP_EXECUTION_STATUSES


@dataclass(frozen=True, slots=True)
class HttpExecutionTaskRequest:
    run_id: str


@dataclass(frozen=True, slots=True)
class HttpExecutionInput:
    run_id: str
    base_url: str
    variables: dict[str, str]
    secret_names: tuple[str, ...]
    method: HttpMethod
    path_template: str
    headers_template: dict[str, str]
    body_template: str | None
    timeout_seconds: int
    max_attempts: int = 1
    assertions: tuple[HttpAssertion, ...] = ()


@dataclass(frozen=True, slots=True)
class HttpExecutionResult:
    status_code: int
    headers: dict[str, str]
    body: str
    body_encoding: Literal["text", "base64"]
    size_bytes: int
    duration_ms: int
