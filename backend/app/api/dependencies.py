from collections.abc import Awaitable, Callable
from hmac import compare_digest
from typing import Annotated

from fastapi import Header
from pydantic import SecretStr

from backend.app.core.errors import AppError

SessionAuthDependency = Callable[..., Awaitable[None]]


def create_session_auth_dependency(
    expected_token: SecretStr | None,
) -> SessionAuthDependency:
    async def require_session_token(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        if expected_token is None:
            return

        scheme, separator, credentials = (authorization or "").partition(" ")
        supplied_token = credentials if separator and scheme.casefold() == "bearer" else ""
        if not compare_digest(expected_token.get_secret_value(), supplied_token):
            raise AppError(
                code="SESSION_TOKEN_INVALID",
                message="本地会话凭据无效。",
                status_code=401,
            )

    return require_session_token
