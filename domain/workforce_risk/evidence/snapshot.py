from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from workforce_risk.evidence.fingerprint import EvidenceFingerprintInput
from workforce_risk.models import RiskResult


class SnapshotRiskResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    score_family: Literal["employee_overload", "task_fit", "project_delivery"]
    result: RiskResult


class VersionedEvidenceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    evidence: EvidenceFingerprintInput
    risk_results: tuple[SnapshotRiskResult, ...]

    @property
    def fingerprint(self) -> str:
        return self.evidence.fingerprint()
