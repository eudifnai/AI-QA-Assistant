from dataclasses import dataclass
from enum import StrEnum


class HealthStatus(StrEnum):
    OK = "ok"


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    status: HealthStatus
    version: str
