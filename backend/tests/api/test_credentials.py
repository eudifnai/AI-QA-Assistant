from typing import NoReturn

from fastapi.testclient import TestClient

from backend.app.application.credentials import ModelCredentialUseCases
from backend.app.core.errors import AppError
from backend.app.main import create_app


class StubCredentialService(ModelCredentialUseCases):
    def __init__(self) -> None:
        self.secret: str | None = None
        self.deleted = False

    def status(self) -> bool:
        return self.secret is not None

    def set(self, secret: str) -> bool:
        self.secret = secret
        return True

    def delete(self) -> bool:
        self.deleted = True
        self.secret = None
        return False


class FailingCredentialService(StubCredentialService):
    def set(self, secret: str) -> NoReturn:
        raise AppError(
            code="CREDENTIAL_STORE_UNAVAILABLE",
            message="操作系统凭据库当前不可用。",
            status_code=503,
        )


class CrashingCredentialService(StubCredentialService):
    def status(self) -> NoReturn:
        raise RuntimeError("sensitive credential detail")


def test_credential_status_never_returns_secret() -> None:
    service = StubCredentialService()
    service.secret = "test-credential-value"
    app = create_app(credential_service=service)

    with TestClient(app) as client:
        response = client.get("/api/settings/model-credential")

    assert response.status_code == 200
    assert response.json() == {"configured": True}
    assert "test-credential-value" not in response.text


def test_set_and_delete_credential_delegate_without_echoing_secret() -> None:
    service = StubCredentialService()
    app = create_app(credential_service=service)

    with TestClient(app) as client:
        saved = client.put(
            "/api/settings/model-credential",
            json={"api_key": "test-credential-value"},
        )
        deleted = client.delete("/api/settings/model-credential")

    assert saved.status_code == 200
    assert saved.json() == {"configured": True}
    assert "test-credential-value" not in saved.text
    assert service.secret is None
    assert service.deleted is True
    assert deleted.json() == {"configured": False}


def test_set_credential_rejects_invalid_payload() -> None:
    app = create_app(credential_service=StubCredentialService())

    with TestClient(app) as client:
        response = client.put("/api/settings/model-credential", json={"api_key": "xY7!"})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert "xY7!" not in response.text


def test_set_credential_maps_store_failure() -> None:
    app = create_app(credential_service=FailingCredentialService())

    with TestClient(app) as client:
        response = client.put(
            "/api/settings/model-credential",
            json={"api_key": "test-credential-value"},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "CREDENTIAL_STORE_UNAVAILABLE"


def test_credential_unexpected_failure_is_redacted() -> None:
    app = create_app(credential_service=CrashingCredentialService())

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/settings/model-credential")

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "sensitive credential detail" not in response.text
