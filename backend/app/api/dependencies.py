import base64
import binascii
from collections.abc import Awaitable, Callable
from hmac import compare_digest

from fastapi import WebSocketException, status
from pydantic import SecretStr
from starlette.requests import HTTPConnection

from backend.app.core.errors import AppError

SessionAuthDependency = Callable[..., Awaitable[None]]


def _decode_websocket_token(value: str) -> str:
    if not value.startswith("auth.") or len(value) > 2048:
        return ""
    encoded = value.removeprefix("auth.")
    padding = "=" * (-len(encoded) % 4)
    try:
        decoded = base64.b64decode(f"{encoded}{padding}", altchars=b"-_", validate=True).decode(
            "utf-8"
        )
    except (binascii.Error, UnicodeDecodeError):
        return ""
    return decoded


def create_session_auth_dependency(
    expected_token: SecretStr | None,
) -> SessionAuthDependency:
    async def require_session_token(connection: HTTPConnection) -> None:
        if expected_token is None:
            return

        authorization = connection.headers.get("authorization", "")
        scheme, separator, credentials = authorization.partition(" ")
        supplied_token = credentials if separator and scheme.casefold() == "bearer" else ""
        if connection.scope["type"] == "websocket":
            protocols = [
                item.strip()
                for item in connection.headers.get("sec-websocket-protocol", "").split(",")
                if item.strip()
            ]
            supplied_token = _decode_websocket_token(protocols[1]) if len(protocols) == 2 else ""
        if not compare_digest(expected_token.get_secret_value(), supplied_token):
            if connection.scope["type"] == "websocket":
                raise WebSocketException(
                    code=status.WS_1008_POLICY_VIOLATION,
                    reason="本地会话凭据无效。",
                )
            raise AppError(
                code="SESSION_TOKEN_INVALID",
                message="本地会话凭据无效。",
                status_code=401,
            )

    return require_session_token
