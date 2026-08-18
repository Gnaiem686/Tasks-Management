from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from workforce_risk.models import FactorContribution, RiskResult

from agent_api.risk_evidence import RiskEvidenceDossier


class ExplanationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    workflow: str
    question: str
    risk: RiskResult
    evidence_dossier: RiskEvidenceDossier | None = None
    candidate_ids: tuple[str, ...] = ()
    untrusted_evidence: tuple[str, ...] = ()
    correlation_id: str


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action: str
    reason: str
    candidate_id: str | None = None


class ModelExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    answer: str | None = None
    summary: str
    root_causes: tuple[str, ...]
    recommendations: tuple[Recommendation, ...]
    citations: tuple[str, ...]
    score: int | None
    risk_level: str | None
    uncertainties: tuple[str, ...]


class ExplanationResponse(ModelExplanation):
    source: Literal["bedrock", "deterministic_fallback", "jira_mcp"]
    correlation_id: str


def build_model_payload(request: ExplanationRequest) -> dict[str, object]:
    """Allowlist only deterministic, work-planning evidence for Bedrock."""
    risk = request.risk
    ordered_factors = sorted(
        risk.factors,
        key=lambda factor: (-factor.contribution_points, factor.name),
    )

    def guidance(
        factor: FactorContribution,
        *,
        impact: str,
    ) -> dict[str, object]:
        return {
            "name": factor.name,
            "direction": factor.direction,
            "impact": impact,
            "evidence_references": list(factor.evidence_references),
        }

    positive_factors = [
        factor for factor in ordered_factors if factor.contribution_points > 0
    ]
    zero_factors = [
        factor for factor in ordered_factors if factor.contribution_points == 0
    ]
    lowest_impact_factors = sorted(
        risk.factors,
        key=lambda factor: (factor.contribution_points, factor.name),
    )[:4]

    dossier = request.evidence_dossier
    work_situation = None
    if dossier is not None:
        work_situation = {
            "observed_at": dossier.observed_at.isoformat().replace("+00:00", "Z"),
            "available_capacity_hours": dossier.available_capacity_hours,
            "total_remaining_hours": dossier.total_remaining_hours,
            "overdue_task_keys": list(dossier.overdue_task_keys),
            "due_soon_task_keys": list(dossier.due_soon_task_keys),
            "blocked_task_keys": list(dossier.blocked_task_keys),
            "missing_evidence": list(dossier.missing_evidence),
            "tasks": [
                {
                    "key": task.key,
                    "summary": task.summary,
                    "status": task.status,
                    "priority": task.priority,
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                    "remaining_hours": task.remaining_hours,
                    "blocker_category": task.blocker_category,
                    "dependencies": list(task.dependencies),
                    "last_activity_at": task.last_activity_at.isoformat().replace(
                        "+00:00", "Z"
                    ),
                }
                for task in dossier.tasks
            ],
        }
    return {
        "workflow": request.workflow,
        "question": request.question[:500],
        "subject_id": risk.subject_id,
        "environment": risk.environment,
        "score": risk.score,
        "risk_level": risk.level.value if risk.level else None,
        "confidence": risk.confidence.value,
        "scoring_model_version": risk.scoring_model_version,
        "factors": [
            {
                "name": factor.name,
                "contribution_points": factor.contribution_points,
                "direction": factor.direction,
                "evidence_references": list(factor.evidence_references),
            }
            for factor in risk.factors
        ],
        "strongest_contributors": [
            guidance(factor, impact="strongest_contribution")
            for factor in positive_factors[:4]
        ],
        "mitigating_factors": [
            guidance(factor, impact="zero_contribution") for factor in zero_factors[:4]
        ],
        "lowest_impact_factors": [
            guidance(
                factor,
                impact=(
                    "zero_contribution"
                    if factor.contribution_points == 0
                    else "low_relative_contribution"
                ),
            )
            for factor in lowest_impact_factors
        ],
        "evidence_references": list(risk.evidence_references),
        "missing_evidence": list(risk.missing_evidence),
        "work_situation": work_situation,
        "candidate_ids": list(request.candidate_ids),
        "correlation_id": request.correlation_id,
    }
