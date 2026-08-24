from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.application.health import HealthService
from backend.app.core.config import Settings
from backend.app.main import create_app


def test_health_returns_status_and_version() -> None:
    app = create_app(health_service=HealthService(version="9.8.7"))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "9.8.7"}
    assert len(response.headers["x-trace-id"]) == 32


def test_health_requires_configured_session_token() -> None:
    settings = Settings(session_token=SecretStr("desktop-session-token"))
    app = create_app(health_service=HealthService(version="9.8.7"), settings=settings)

    with TestClient(app) as client:
        response = client.get("/health")

    payload = response.json()
    assert response.status_code == 401
    assert payload["code"] == "SESSION_TOKEN_INVALID"
    assert payload["message"] == "本地会话凭据无效。"
    assert "desktop-session-token" not in response.text
    assert payload["trace_id"] == response.headers["x-trace-id"]


def test_health_accepts_configured_session_token() -> None:
    settings = Settings(session_token=SecretStr("desktop-session-token"))
    app = create_app(health_service=HealthService(version="9.8.7"), settings=settings)

    with TestClient(app) as client:
        response = client.get(
            "/health",
            headers={"Authorization": "Bearer desktop-session-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "9.8.7"}


def test_health_rejects_wrong_session_token_without_leaking_it() -> None:
    settings = Settings(session_token=SecretStr("desktop-session-token"))
    app = create_app(health_service=HealthService(version="9.8.7"), settings=settings)

    with TestClient(app) as client:
        response = client.get(
            "/health",
            headers={"Authorization": "Bearer wrong-session-token"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "SESSION_TOKEN_INVALID"
    assert "wrong-session-token" not in response.text
    assert "desktop-session-token" not in response.text
