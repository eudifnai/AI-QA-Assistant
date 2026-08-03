import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.responses import Response

logger = logging.getLogger(__name__)


class ErrorResponse(BaseModel):
    code: str
    message: str
    detail: Any | None = None
    trace_id: str


class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        detail: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


def _trace_id(request: Request) -> str:
    trace_id = getattr(request.state, "trace_id", None)
    return trace_id if isinstance(trace_id, str) else uuid4().hex


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    detail: Any | None = None,
) -> JSONResponse:
    trace_id = _trace_id(request)
    payload = ErrorResponse(
        code=code,
        message=message,
        detail=detail,
        trace_id=trace_id,
    )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(payload.model_dump()),
        headers={"X-Trace-ID": trace_id},
    )


def _safe_validation_detail(exception: RequestValidationError) -> list[dict[str, Any]]:
    return [
        {
            "type": error.get("type"),
            "loc": list(error.get("loc", ())),
            "msg": error.get("msg"),
        }
        for error in exception.errors()
    ]


def configure_error_handling(app: FastAPI) -> None:
    @app.middleware("http")
    async def add_trace_id(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.state.trace_id = uuid4().hex
        response = await call_next(request)
        response.headers["X-Trace-ID"] = request.state.trace_id
        return response

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exception: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="请求参数不正确。",
            detail=_safe_validation_detail(exception),
        )

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exception: AppError) -> JSONResponse:
        return _error_response(
            request,
            status_code=exception.status_code,
            code=exception.code,
            message=exception.message,
            detail=exception.detail,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exception: Exception) -> JSONResponse:
        logger.error(
            "Unhandled API exception",
            extra={"trace_id": _trace_id(request)},
            exc_info=(type(exception), exception, exception.__traceback__),
        )
        return _error_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="服务发生未预期错误。",
        )
