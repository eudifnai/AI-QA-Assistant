from __future__ import annotations

import base64
import time
from email.message import Message
from http.client import HTTPResponse
from typing import IO, Literal
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, OpenerDirector, ProxyHandler, Request, build_opener

from backend.app.domain.http_execution import HttpExecutionResult, redact_secrets

MAX_HTTP_RESPONSE_BYTES = 2 * 1024 * 1024
SENSITIVE_RESPONSE_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "proxy-authenticate",
        "proxy-authorization",
        "set-cookie",
        "www-authenticate",
    }
)


class HttpRunnerError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> None:
        return None


class StdlibHttpRunner:
    def __init__(self, opener: OpenerDirector | None = None) -> None:
        self._opener = opener or build_opener(ProxyHandler({}), _NoRedirectHandler())

    def execute(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: str | None,
        timeout_seconds: int,
        secrets: tuple[str, ...],
    ) -> HttpExecutionResult:
        request = Request(
            url,
            data=None if body is None else body.encode("utf-8"),
            headers=headers,
            method=method,
        )
        started = time.monotonic()
        try:
            with self._opener.open(request, timeout=timeout_seconds) as response:
                status_code = response.status
                response_headers = dict(response.headers.items())
                payload = self._read_limited(response)
        except HTTPError as response:
            status_code = response.code
            response_headers = dict(response.headers.items())
            payload = self._read_limited(response)
        except TimeoutError as exception:
            raise HttpRunnerError("timeout") from exception
        except (URLError, OSError, ValueError) as exception:
            raise HttpRunnerError("unavailable") from exception
        duration_ms = max(0, round((time.monotonic() - started) * 1000))
        redacted_payload = payload
        for secret in sorted((value for value in secrets if value), key=len, reverse=True):
            redacted_payload = redacted_payload.replace(secret.encode("utf-8"), b"***")
        body_value, encoding = self._encode_body(redacted_payload)
        return HttpExecutionResult(
            status_code=status_code,
            headers=self._redact_headers(response_headers, secrets),
            body=body_value,
            body_encoding=encoding,
            size_bytes=len(payload),
            duration_ms=duration_ms,
        )

    @staticmethod
    def _read_limited(response: HTTPResponse | HTTPError) -> bytes:
        payload = response.read(MAX_HTTP_RESPONSE_BYTES + 1)
        if len(payload) > MAX_HTTP_RESPONSE_BYTES:
            raise HttpRunnerError("response_too_large")
        return payload

    @staticmethod
    def _encode_body(payload: bytes) -> tuple[str, Literal["text", "base64"]]:
        try:
            return payload.decode("utf-8"), "text"
        except UnicodeDecodeError:
            return base64.b64encode(payload).decode("ascii"), "base64"

    @staticmethod
    def _redact_headers(headers: dict[str, str], secrets: tuple[str, ...]) -> dict[str, str]:
        return {
            name: (
                "***"
                if name.casefold() in SENSITIVE_RESPONSE_HEADERS
                else redact_secrets(value, secrets)
            )
            for name, value in headers.items()
        }
