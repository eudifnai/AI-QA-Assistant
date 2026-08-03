from backend.app.application.health import HealthService
from backend.app.domain.health import HealthStatus


def test_health_service_returns_configured_version() -> None:
    service = HealthService(version="1.2.3")

    snapshot = service.get_health()

    assert snapshot.status is HealthStatus.OK
    assert snapshot.version == "1.2.3"
