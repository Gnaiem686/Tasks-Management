from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class ReportRiskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    subject_id: str
    score_family: Literal["employee_overload", "task_fit", "project_delivery"]
    score: int | None = Field(ge=0, le=100)
    risk_level: str | None
    confidence: str
    scoring_model_version: str
    evidence_references: tuple[str, ...]
    recommendations: tuple[str, ...] = ()


class DailyRiskReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = "1.0"
    report_id: str
    environment: Literal["dev", "prod", "test"]
    generated_at: AwareDatetime
    scope: str
    generator_version: str
    risks: tuple[ReportRiskSummary, ...]

    @model_validator(mode="after")
    def reject_sensitive_material(self) -> DailyRiskReport:
        serialized = self.model_dump_json().lower()
        forbidden = (
            "api_key",
            "authorization:",
            "bearer ",
            "password",
            "secret_access_key",
            "raw_comment",
            "jwt",
        )
        if any(term in serialized for term in forbidden):
            raise ValueError("report contains prohibited sensitive material")
        return self

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def object_key(self) -> str:
        timestamp: datetime = self.generated_at
        return f"reports/{self.environment}/{timestamp:%Y/%m/%d}/{self.report_id}.json"
