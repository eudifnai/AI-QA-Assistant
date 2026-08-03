from backend.app.domain.health import HealthSnapshot, HealthStatus


class HealthService:
    def __init__(self, version: str) -> None:
        self._version = version

    def get_health(self) -> HealthSnapshot:
        return HealthSnapshot(status=HealthStatus.OK, version=self._version)
