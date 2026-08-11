from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

HealthState = Literal["healthy", "degraded", "unhealthy"]


@dataclass(frozen=True)
class ServiceHealth:
    process: HealthState
    dependency_readiness: HealthState
    workflow: HealthState

    @property
    def ready(self) -> bool:
        return self.process == "healthy" and self.dependency_readiness != "unhealthy"
