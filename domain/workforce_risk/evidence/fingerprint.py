from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

MATERIAL_FIELDS = (
    "schema_version",
    "subject_id",
    "task_state",
    "current_assignee",
    "employee_workloads",
    "due_date",
    "dependencies",
    "scoring_versions",
)


class EvidenceFingerprintInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"]
    environment: Literal["dev", "prod", "test"]
    subject_id: str = Field(min_length=1, max_length=128)
    task_state: str = Field(min_length=1, max_length=64)
    current_assignee: str | None = Field(default=None, max_length=256)
    employee_workloads: dict[str, float]
    due_date: date | None = None
    dependencies: tuple[str, ...] = ()
    scoring_versions: tuple[str, ...]
    evidence_timestamp: AwareDatetime
    irrelevant_metadata: dict[str, Any] = Field(default_factory=dict)

    def canonical_material(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", include=set(MATERIAL_FIELDS))
        payload["environment"] = self.environment
        payload["employee_workloads"] = dict(sorted(self.employee_workloads.items()))
        payload["dependencies"] = sorted(self.dependencies)
        payload["scoring_versions"] = sorted(self.scoring_versions)
        return payload

    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.canonical_material(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


def material_changes(
    previous: EvidenceFingerprintInput, current: EvidenceFingerprintInput
) -> tuple[str, ...]:
    if previous.environment != current.environment:
        raise ValueError("evidence environment mismatch")
    before = previous.canonical_material()
    after = current.canonical_material()
    return tuple(name for name in before if before[name] != after[name])
