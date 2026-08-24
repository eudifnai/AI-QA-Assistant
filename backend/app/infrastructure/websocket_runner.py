from __future__ import annotations

import base64
import time
from collections.abc import Callable
from typing import Any, Literal, Protocol, cast

from websockets.exceptions import PayloadTooBig, WebSocketException
from websockets.sync.client import connect

from backend.app.domain.http_execution import redact_secrets
from backend.app.domain.websocket_execution import WebSocketExecutionResult, WebSocketMessage

MAX_WEBSOCKET_MESSAGE_BYTES = 2 * 1024 * 1024


class WebSocketRunnerError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class WebSocketConnection(Protocol):
    def __enter__(self) -> WebSocketConnection: ...

    def __exit__(self, *args: object) -> None: ...

    def send(self, message: str) -> None: ...

    def recv(self, timeout: float | None = None) -> str | bytes: ...


ConnectFactory = Callable[..., WebSocketConnection]


class WebSocketRunner:
    def __init__(self, connect_factory: ConnectFactory | None = None) -> None:
        self._connect = connect_factory or cast(ConnectFactory, connect)

    def execute(
        self,
        *,
        url: str,
        headers: dict[str, str],
        message: str,
        additional_messages: tuple[str, ...] = (),
        receive_count: int = 1,
        ping_interval_seconds: int | None = None,
        max_reconnect_attempts: int = 0,
        timeout_seconds: int,
        secrets: tuple[str, ...],
    ) -> WebSocketExecutionResult:
        started = time.monotonic()
        responses: tuple[WebSocketMessage, ...] = ()
        attempt_count = 0
        for attempt in range(max_reconnect_attempts + 1):
            attempt_count = attempt + 1
            try:
                options: dict[str, Any] = {
                    "additional_headers": headers,
                    "open_timeout": timeout_seconds,
                    "close_timeout": min(timeout_seconds, 5),
                    "proxy": None,
                    "max_size": MAX_WEBSOCKET_MESSAGE_BYTES,
                    "ping_interval": ping_interval_seconds,
                    "ping_timeout": ping_interval_seconds,
                }
                collected: list[WebSocketMessage] = []
                total_bytes = 0
                with self._connect(url, **options) as connection:
                    for outgoing in (message, *additional_messages):
                        connection.send(outgoing)
                    for ordinal in range(receive_count):
                        response = connection.recv(timeout=timeout_seconds)
                        encoded = self._encode_response(response, secrets, ordinal)
                        total_bytes += encoded.size_bytes
                        if total_bytes > MAX_WEBSOCKET_MESSAGE_BYTES:
                            raise WebSocketRunnerError("response_too_large")
                        collected.append(encoded)
                responses = tuple(collected)
                break
            except PayloadTooBig as exception:
                raise WebSocketRunnerError("response_too_large") from exception
            except WebSocketRunnerError:
                raise
            except TimeoutError as exception:
                if attempt < max_reconnect_attempts:
                    continue
                raise WebSocketRunnerError("timeout") from exception
            except (WebSocketException, OSError, ValueError) as exception:
                if attempt < max_reconnect_attempts:
                    continue
                raise WebSocketRunnerError("unavailable") from exception
        duration_ms = max(0, round((time.monotonic() - started) * 1000))
        first = responses[0]
        return WebSocketExecutionResult(
            message=first.message,
            encoding=first.encoding,
            size_bytes=sum(item.size_bytes for item in responses),
            duration_ms=duration_ms,
            responses=responses,
            attempt_count=attempt_count,
        )

    @staticmethod
    def _encode_response(
        response: str | bytes, secrets: tuple[str, ...], ordinal: int
    ) -> WebSocketMessage:
        if isinstance(response, str):
            payload = response.encode("utf-8")
            if len(payload) > MAX_WEBSOCKET_MESSAGE_BYTES:
                raise WebSocketRunnerError("response_too_large")
            value = redact_secrets(response, secrets)
            encoding: Literal["text", "base64"] = "text"
        else:
            if len(response) > MAX_WEBSOCKET_MESSAGE_BYTES:
                raise WebSocketRunnerError("response_too_large")
            redacted = response
            for secret in sorted((item for item in secrets if item), key=len, reverse=True):
                redacted = redacted.replace(secret.encode("utf-8"), b"***")
            payload = response
            value = base64.b64encode(redacted).decode("ascii")
            encoding = "base64"
        return WebSocketMessage(ordinal, value, encoding, len(payload))
