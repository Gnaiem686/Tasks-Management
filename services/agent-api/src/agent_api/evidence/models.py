from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from workforce_risk.models import RiskResult

from agent_api.dashboard.models import DashboardSnapshot
from agent_api.risk_evidence import RiskEvidenceDossier


class EvidenceScope(StrEnum):
    PROJECT = "project"
    EMPLOYEE = "employee"
    TASK = "task"
    MIXED = "mixed"


class EvidenceCategory(StrEnum):
    JIRA_ISSUES = "jira_issues"
    WORKFORCE_PROFILES = "workforce_profiles"
    CAPACITY_AND_WORKLOAD = "capacity_and_workload"
    SKILLS_AND_SENIORITY = "skills_and_seniority"
    RISK_RESULTS = "risk_results"
    DEPENDENCIES_AND_BLOCKERS = "dependencies_and_blockers"
    DEADLINES = "deadlines"
    HISTORY = "history"
    OPERATIONS = "operations"


class EvidenceEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["project", "employee", "task", "risk", "operation"]
    identifier: str = Field(min_length=1, max_length=128)


class EvidencePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scope: EvidenceScope
    entities: tuple[EvidenceEntity, ...] = ()
    evidence_categories: tuple[EvidenceCategory, ...] = Field(min_length=1)
    exhaustive: bool = False


class MissingData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    category: EvidenceCategory
    reason: str = Field(min_length=1, max_length=500)
    entity: str = Field(min_length=1, max_length=128)
    required_for_claim: bool = False


class CapacityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    employee_id: str | None = None
    configured_capacity_hours: float
    workload_hours: float
    available_capacity_hours: float
    capacity_headroom_hours: float
    utilization_percent: float


class RankedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    employee_id: str
    display_name: str
    role: str | None = None
    seniority: str | None = None
    rank: int = Field(ge=1)
    capacity_headroom_hours: float | None = None
    matching_skills: tuple[str, ...] = ()
    missing_required_skills: tuple[str, ...] = ()
    eligible: bool
    reasons: tuple[str, ...] = ()


class CandidateRankingResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["success", "insufficient_data", "no_candidates"]
    candidates: tuple[RankedCandidate, ...] = ()
    missing_data: tuple[MissingData, ...] = ()


class AnswerTaskEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str
    summary: str
    status: str
    priority: str
    assignee: str | None = None
    due_date: date | None = None
    remaining_hours: float | None = None
    blocker: str | None = None
    dependencies: tuple[str, ...] = ()
    blocked: bool = False
    blocks_downstream: tuple[str, ...] = ()
    overdue: bool = False
    due_soon: bool = False
    missing_fields: tuple[str, ...] = ()


class AnswerEmployeeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    employee_id: str
    display_name: str
    role: str | None = None
    skills: tuple[str, ...] = ()
    capacity_hours: float | None = None
    remaining_hours: float | None = None
    available_capacity_hours: float | None = None
    active_tasks: int
    risk_level: str
    top_risk: str
    task_keys: tuple[str, ...] = ()


class AnswerEvidenceSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    question_focus: str
    tasks: tuple[AnswerTaskEvidence, ...] = ()
    required_task_keys: tuple[str, ...] = ()
    employees: tuple[AnswerEmployeeEvidence, ...] = ()
    exhaustive: bool = False
    missing_data: tuple[MissingData, ...] = ()

    @model_validator(mode="after")
    def required_tasks_are_in_evidence(self) -> AnswerEvidenceSet:
        evidence_keys = {task.key.upper() for task in self.tasks}
        unknown = {
            key.upper()
            for key in self.required_task_keys
            if key.upper() not in evidence_keys
        }
        if unknown:
            raise ValueError(
                "required task keys must exist in task evidence: "
                + ", ".join(sorted(unknown))
            )
        return self


class UniversalEvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = "1.0"
    correlation_id: str = Field(min_length=1, max_length=128)
    project_key: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,19}$")
    plan: EvidencePlan
    answer_evidence: AnswerEvidenceSet | None = None
    project_snapshot: DashboardSnapshot | None = None
    capacity_and_workload: tuple[CapacityEvidence, ...] = ()
    employee_workload_classifications: dict[str, str] = Field(default_factory=dict)
    task_delivery_risk: dict[str, str] = Field(default_factory=dict)
    skills: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    seniority: dict[str, str | None] = Field(default_factory=dict)
    risk_results: tuple[RiskResult, ...] = ()
    evidence_dossiers: tuple[RiskEvidenceDossier, ...] = ()
    ranked_candidates: tuple[RankedCandidate, ...] = ()
    candidate_ranking: CandidateRankingResult | None = None
    history: tuple[dict[str, object], ...] = ()
    comments: tuple[dict[str, object], ...] = ()
    operations: tuple[dict[str, object], ...] = ()
    missing_data: tuple[MissingData, ...] = ()
    source_metadata: tuple[dict[str, object], ...] = ()
    ambiguous_references: tuple[EvidenceEntity, ...] = ()


def calculate_capacity(
    configured_capacity_hours: float | None,
    workload_hours: float | None,
    *,
    employee_id: str | None = None,
) -> CapacityEvidence | None:
    if configured_capacity_hours is None or configured_capacity_hours <= 0:
        return None
    workload = 0.0 if workload_hours is None else workload_hours
    headroom = configured_capacity_hours - workload
    return CapacityEvidence(
        employee_id=employee_id,
        configured_capacity_hours=configured_capacity_hours,
        workload_hours=workload,
        available_capacity_hours=max(headroom, 0.0),
        capacity_headroom_hours=headroom,
        utilization_percent=workload / configured_capacity_hours * 100.0,
    )
