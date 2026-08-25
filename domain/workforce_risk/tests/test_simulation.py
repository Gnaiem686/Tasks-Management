from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from workforce_risk.models import ConfidenceLevel, RiskLevel, RiskResult
from workforce_risk.profiles import (
    DocumentedSkill,
    ProjectAllocation,
    Seniority,
    SkillProficiency,
    WorkforceProfile,
)
from workforce_risk.simulation.candidates import CandidateEvidence, select_candidates
from workforce_risk.simulation.service import ScoreFamilies, simulate_reassignment

NOW = datetime(2026, 8, 9, 12, tzinfo=UTC)


def risk(
    subject: str,
    score: int | None,
    family: str,
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
    version: str | None = None,
) -> RiskResult:
    return RiskResult(
        subject_id=subject,
        environment="test",
        score=score,
        level=None
        if score is None
        else (
            RiskLevel.LOW
            if score < 30
            else RiskLevel.MEDIUM
            if score < 55
            else RiskLevel.HIGH
            if score < 75
            else RiskLevel.CRITICAL
        ),
        confidence=confidence,
        scored_at=NOW,
        evidence_timestamp=NOW,
        scoring_model_version=version or f"{family}-v1",
        factors=(),
        thresholds={},
        evidence_references=(f"jira:WRD-1:{family}",) if score is not None else (),
        missing_evidence=() if score is not None else ("required",),
        excluded_evidence=(),
    )


def candidate(
    employee_id: str,
    overload: int | None,
    task_fit: int | None,
    project: int | None,
    *,
    access: bool = True,
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
) -> CandidateEvidence:
    profile = WorkforceProfile(
        employee_id=employee_id,
        environment="test",
        role="Engineer",
        seniority=Seniority.SENIOR,
        documented_skills=(
            DocumentedSkill(name="python", proficiency=SkillProficiency.ADVANCED),
        ),
        weekly_capacity_hours=40,
        project_allocations=(ProjectAllocation(project_key="WRD", fraction=1),),
        mentoring_available=True,
        jira_account_id=f"jira-{employee_id}",
        version=1,
    )
    return CandidateEvidence(
        profile=profile,
        has_jira_project_access=access,
        overload_risk=risk(employee_id, overload, "employee-overload", confidence),
        task_fit_risk=risk("WRD-1", task_fit, "task-fit", confidence),
        predicted_project_risk=risk("WRD", project, "project-delivery", confidence),
    )


def current_scores() -> ScoreFamilies:
    return ScoreFamilies(
        employee_overload=risk("EMP-002", 88, "employee-overload"),
        task_fit=risk("WRD-1", 82, "task-fit"),
        project_delivery=risk("WRD", 78, "project-delivery"),
    )


@pytest.mark.unit
def test_candidate_selection_rejects_overload_access_and_missing_evidence() -> None:
    assessments = select_candidates(
        (
            candidate("EMP-003", 30, 20, 45),
            candidate("EMP-004", 80, 20, 45),
            candidate("EMP-005", 20, 30, 40, access=False),
            candidate("EMP-006", 20, None, 40),
        )
    )
    assert assessments[0].employee_id == "EMP-003" and assessments[0].eligible
    reasons = {item.employee_id: item.reasons for item in assessments}
    assert "candidate_overloaded" in reasons["EMP-004"]
    assert "jira_access_unavailable" in reasons["EMP-005"]
    assert "incomplete_structured_evidence" in reasons["EMP-006"]


@pytest.mark.unit
def test_what_if_uses_same_versions_and_lowers_all_score_families() -> None:
    simulation = simulate_reassignment(
        task_id="WRD-1",
        current_assignee_id="EMP-002",
        candidates=(candidate("EMP-003", 30, 20, 45),),
        selected_employee_id="EMP-003",
        current_scores=current_scores(),
    )
    assert simulation.proposed.employee_overload.score == 30
    assert simulation.proposed.task_fit.score == 20
    assert simulation.proposed.project_delivery.score == 45
    assert simulation.candidate_ids == ("EMP-003",)
    assert len(simulation.evidence_fingerprint) == 64


@pytest.mark.unit
def test_low_confidence_or_invented_candidate_is_rejected() -> None:
    low = candidate("EMP-003", 20, 20, 30, confidence=ConfidenceLevel.LOW)
    assert not select_candidates((low,))[0].eligible
    with pytest.raises(ValueError, match="eligible"):
        simulate_reassignment(
            task_id="WRD-1",
            current_assignee_id="EMP-002",
            candidates=(low,),
            selected_employee_id="EMP-007",
            current_scores=current_scores(),
        )


@pytest.mark.unit
def test_mismatched_scoring_version_is_rejected() -> None:
    selected = candidate("EMP-003", 30, 20, 45)
    selected = selected.model_copy(
        update={"task_fit_risk": risk("WRD-1", 20, "task-fit", version="task-fit-v2")}
    )
    with pytest.raises(ValidationError, match="identical scoring versions"):
        simulate_reassignment(
            task_id="WRD-1",
            current_assignee_id="EMP-002",
            candidates=(selected,),
            selected_employee_id="EMP-003",
            current_scores=current_scores(),
        )
