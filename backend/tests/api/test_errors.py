from typing import NoReturn

from fastapi import FastAPI, Query
from fastapi.testclient import TestClient

from backend.app.core.errors import AppError, configure_error_handling


def create_error_test_app() -> FastAPI:
    app = FastAPI()
    configure_error_handling(app)

    @app.get("/validate")
    async def validate(value: int = Query(gt=0)) -> dict[str, int]:
        return {"value": value}

    @app.get("/business", response_model=None)
    async def business_error() -> NoReturn:
        raise AppError(
            code="WORKSPACE_NOT_READY",
            message="工作空间尚未准备完成。",
            status_code=409,
            detail="test detail",
        )

    @app.get("/unexpected", response_model=None)
    async def unexpected_error() -> NoReturn:
        raise RuntimeError("secret internal detail")

    return app


def test_validation_error_uses_stable_error_contract() -> None:
    with TestClient(create_error_test_app()) as client:
        response = client.get("/validate", params={"value": "sensitive-input"})

    payload = response.json()
    assert response.status_code == 422
    assert payload["code"] == "VALIDATION_ERROR"
    assert payload["message"] == "请求参数不正确。"
    assert payload["detail"]
    assert "sensitive-input" not in response.text
    assert payload["trace_id"] == response.headers["x-trace-id"]


def test_business_error_preserves_safe_detail() -> None:
    with TestClient(create_error_test_app()) as client:
        response = client.get("/business")

    assert response.status_code == 409
    assert response.json() == {
        "code": "WORKSPACE_NOT_READY",
        "message": "工作空间尚未准备完成。",
        "detail": "test detail",
        "trace_id": response.headers["x-trace-id"],
    }


def test_unexpected_error_is_logged_and_redacted() -> None:
    with TestClient(create_error_test_app(), raise_server_exceptions=False) as client:
        response = client.get("/unexpected")

    payload = response.json()
    assert response.status_code == 500
    assert payload["code"] == "INTERNAL_ERROR"
    assert payload["message"] == "服务发生未预期错误。"
    assert "secret internal detail" not in response.text
    assert payload["trace_id"] == response.headers["x-trace-id"]
