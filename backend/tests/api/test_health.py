from fastapi.testclient import TestClient

from backend.app.application.health import HealthService
from backend.app.main import create_app


def test_health_returns_status_and_version() -> None:
    app = create_app(health_service=HealthService(version="9.8.7"))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "9.8.7"}
    assert len(response.headers["x-trace-id"]) == 32
