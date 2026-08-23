from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ProjectSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str
    name: str
    total_tasks: int
    completed_tasks: int
    active_tasks: int
    overdue_tasks: int
    due_soon_tasks: int
    blocked_tasks: int
    missing_estimate_tasks: int
    completion_percent: int


class EmployeeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    employee_id: str
    display_name: str
    role: str | None
    skills: tuple[str, ...]
    capacity_hours: float | None
    remaining_hours: float | None
    active_tasks: int
    score: int | None
    level: Literal["low", "medium", "high", "critical", "insufficient-data"]
    top_risk: str


class TaskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str
    summary: str
    status: str
    priority: str | None
    assignee_id: str | None
    assignee_name: str | None
    due_date: date | None
    original_hours: float | None
    remaining_hours: float | None
    raw_remaining_hours: float | None = None
    time_spent_hours: float | None = None
    jira_updated_at: datetime | None = None
    data_quality_findings: tuple[str, ...] = ()
    required_skills: tuple[str, ...]
    blocker: str | None
    dependencies: tuple[str, ...]
    jira_url: str


class AlertSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    subject_id: str
    severity: Literal["medium", "high", "critical"]
    score: int = Field(ge=0, le=100)
    reason: str


class WorkloadDistribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    overloaded: int
    balanced: int
    insufficient_data: int


class DashboardSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = "1.0"
    correlation_id: str
    evidence_timestamp: AwareDatetime
    project: ProjectSummary
    employees: tuple[EmployeeSummary, ...]
    tasks: tuple[TaskSummary, ...]
    alerts: tuple[AlertSummary, ...]
    workload: WorkloadDistribution
    degraded: bool = False
    missing_sources: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
