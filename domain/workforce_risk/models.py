from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT_DATA = "insufficient-data"


class EmployeeOverloadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    employee_id: str
    environment: Literal["dev", "prod", "test"]
    remaining_estimated_hours: float | None = Field(default=None, ge=0)
    available_capacity_hours: float | None = Field(default=None, gt=0)
    overdue_tasks: int | None = Field(default=None, ge=0)
    blocked_or_blocking_tasks: int | None = Field(default=None, ge=0)
    urgent_high_priority_tasks: int | None = Field(default=None, ge=0)
    due_soon_tasks: int | None = Field(default=None, ge=0)
    active_tasks: int | None = Field(default=None, ge=0)
    concurrent_projects: int | None = Field(default=None, ge=0)
    stale_tasks: int | None = Field(default=None, ge=0)
    evidence_timestamp: AwareDatetime
    evidence_references: dict[str, tuple[str, ...]] = Field(default_factory=dict)


class TaskFitInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    task_id: str
    environment: Literal["dev", "prod", "test"]
    required_skill_gap: float | None = Field(default=None, ge=0, le=1)
    difficulty_seniority_mismatch: float | None = Field(default=None, ge=0, le=1)
    deadline_pressure: float | None = Field(default=None, ge=0, le=1)
    dependency_impact: float | None = Field(default=None, ge=0, le=1)
    task_criticality: float | None = Field(default=None, ge=0, le=1)
    similar_task_evidence: float | None = Field(default=None, ge=0, le=1)
    mentoring_review_support: float | None = Field(default=None, ge=0, le=1)
    evidence_timestamp: AwareDatetime
    evidence_references: dict[str, tuple[str, ...]] = Field(default_factory=dict)


class ProjectDeliveryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    project_id: str
    environment: Literal["dev", "prod", "test"]
    schedule_gap: float | None = Field(default=None, ge=0, le=1)
    remaining_capacity_pressure: float | None = Field(default=None, ge=0, le=1)
    blocked_overdue_work: float | None = Field(default=None, ge=0, le=1)
    workload_concentration: float | None = Field(default=None, ge=0, le=1)
    unplanned_work: float | None = Field(default=None, ge=0, le=1)
    critical_weak_fit: float | None = Field(default=None, ge=0, le=1)
    evidence_timestamp: AwareDatetime
    evidence_references: dict[str, tuple[str, ...]] = Field(default_factory=dict)


class FactorContribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    raw_value: float
    normalized_value: float = Field(ge=0, le=1)
    weight: float = Field(ge=0, le=1)
    direction: Literal["increases_risk", "inverse_risk", "protective"]
    contribution_points: float
    evidence_references: tuple[str, ...]


class RiskResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    subject_id: str
    environment: Literal["dev", "prod", "test"]
    score: int | None = Field(default=None, ge=0, le=100)
    level: RiskLevel | None
    confidence: ConfidenceLevel
    scored_at: datetime
    evidence_timestamp: datetime
    scoring_model_version: str
    factors: tuple[FactorContribution, ...]
    thresholds: dict[str, int]
    evidence_references: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    excluded_evidence: tuple[str, ...]
