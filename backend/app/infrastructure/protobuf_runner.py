from __future__ import annotations

import time
from email.message import Message
from http.client import HTTPResponse
from typing import IO
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, OpenerDirector, ProxyHandler, Request, build_opener

from backend.app.domain.http_execution import redact_secrets
from backend.app.domain.protobuf_execution import ProtoTransportResult
from backend.app.infrastructure.http_runner import SENSITIVE_RESPONSE_HEADERS

MAX_PROTO_RESPONSE_BYTES = 2 * 1024 * 1024


class ProtoRunnerError(Exception):
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


class StdlibProtobufRunner:
    def __init__(self, opener: OpenerDirector | None = None) -> None:
        self._opener = opener or build_opener(ProxyHandler({}), _NoRedirectHandler())

    def execute(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: bytes,
        timeout_seconds: int,
        secrets: tuple[str, ...],
    ) -> ProtoTransportResult:
        request_headers = {
            name: value
            for name, value in headers.items()
            if name.casefold() not in {"content-type", "content-length", "accept"}
        }
        request_headers["Content-Type"] = "application/x-protobuf"
        request_headers["Accept"] = "application/x-protobuf"
        request = Request(url, data=payload, headers=request_headers, method="POST")
        started = time.monotonic()
        try:
            with self._opener.open(request, timeout=timeout_seconds) as response:
                status_code = response.status
                response_headers = dict(response.headers.items())
                response_payload = self._read_limited(response)
        except HTTPError as response:
            status_code = response.code
            response_headers = dict(response.headers.items())
            response_payload = self._read_limited(response)
        except TimeoutError as exception:
            raise ProtoRunnerError("timeout") from exception
        except (URLError, OSError, ValueError) as exception:
            raise ProtoRunnerError("unavailable") from exception
        duration_ms = max(0, round((time.monotonic() - started) * 1000))
        return ProtoTransportResult(
            status_code,
            self._redact_headers(response_headers, secrets),
            response_payload,
            duration_ms,
        )

    @staticmethod
    def _read_limited(response: HTTPResponse | HTTPError) -> bytes:
        payload = response.read(MAX_PROTO_RESPONSE_BYTES + 1)
        if len(payload) > MAX_PROTO_RESPONSE_BYTES:
            raise ProtoRunnerError("response_too_large")
        return payload

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
