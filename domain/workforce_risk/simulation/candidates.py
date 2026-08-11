from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from workforce_risk.models import ConfidenceLevel, RiskResult
from workforce_risk.profiles import WorkforceProfile

ACCEPTABLE_CONFIDENCE = {ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH}


class CandidateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    profile: WorkforceProfile
    has_jira_project_access: bool
    overload_risk: RiskResult
    task_fit_risk: RiskResult
    predicted_project_risk: RiskResult


class CandidateAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    employee_id: str
    eligible: bool
    reasons: tuple[str, ...]
    ranking_score: float | None


def assess_candidate(candidate: CandidateEvidence) -> CandidateAssessment:
    reasons: list[str] = []
    if (
        candidate.profile.jira_account_id is None
        or not candidate.has_jira_project_access
    ):
        reasons.append("jira_access_unavailable")
    risks = (
        candidate.overload_risk,
        candidate.task_fit_risk,
        candidate.predicted_project_risk,
    )
    if any(result.confidence not in ACCEPTABLE_CONFIDENCE for result in risks):
        reasons.append("confidence_below_minimum")
    if any(result.score is None for result in risks):
        reasons.append("incomplete_structured_evidence")
    if (
        candidate.overload_risk.score is not None
        and candidate.overload_risk.score >= 75
    ):
        reasons.append("candidate_overloaded")
    if reasons:
        return CandidateAssessment(
            employee_id=candidate.profile.employee_id,
            eligible=False,
            reasons=tuple(reasons),
            ranking_score=None,
        )
    overload = candidate.overload_risk.score
    task_fit = candidate.task_fit_risk.score
    project = candidate.predicted_project_risk.score
    assert overload is not None and task_fit is not None and project is not None
    ranking = round(task_fit * 0.5 + overload * 0.3 + project * 0.2, 2)
    return CandidateAssessment(
        employee_id=candidate.profile.employee_id,
        eligible=True,
        reasons=(),
        ranking_score=ranking,
    )


def select_candidates(
    candidates: tuple[CandidateEvidence, ...],
) -> tuple[CandidateAssessment, ...]:
    assessments = tuple(assess_candidate(candidate) for candidate in candidates)
    return tuple(
        sorted(
            assessments,
            key=lambda item: (
                not item.eligible,
                item.ranking_score if item.ranking_score is not None else float("inf"),
                item.employee_id,
            ),
        )
    )
