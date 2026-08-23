from __future__ import annotations

import pytest
from agent_api.dashboard.models import TaskSummary
from agent_api.evidence.collectors import UniversalEvidenceCollector
from agent_api.evidence.models import (
    AnswerEmployeeEvidence,
    AnswerEvidenceSet,
    AnswerTaskEvidence,
    EvidenceCategory,
    EvidencePlan,
    EvidenceScope,
    MissingData,
)
from agent_api.grounding import (
    GroundingValidationError,
    validate_focused_claims,
    validate_focused_completeness,
    validate_insufficiency_claim,
    validate_universal_claims,
    validate_universal_completeness,
)
from test_evidence_collectors import ProjectTool


def blocked_answer_evidence() -> AnswerEvidenceSet:
    return AnswerEvidenceSet(
        question_focus="Which work is blocked right now?",
        tasks=tuple(
            AnswerTaskEvidence(
                key=key,
                summary=f"Task {key}",
                status="In Progress",
                priority="High",
                due_date=None,
                remaining_hours=4,
                dependencies=(f"is blocked by: {blocker}",),
                blocked=True,
            )
            for key, blocker in (
                ("WFD-4", "WFD-2"),
                ("WFD-5", "WFD-3"),
                ("WFD-11", "WFD-9"),
                ("WFD-13", "WFD-12"),
            )
        ),
        exhaustive=True,
    )


def test_vague_insufficiency_is_rejected_when_focused_tasks_exist() -> None:
    with pytest.raises(GroundingValidationError, match="usable focused evidence"):
        validate_insufficiency_claim(
            "I do not have enough information to identify blocked tasks.",
            blocked_answer_evidence(),
        )


def test_precise_missing_estimate_request_is_allowed() -> None:
    evidence = AnswerEvidenceSet(
        question_focus="What is missing?",
        tasks=(
            AnswerTaskEvidence(
                key="WFD-14",
                summary="Release plan",
                status="Idea",
                priority="Medium",
                missing_fields=("remaining_hours",),
            ),
        ),
        missing_data=(
            MissingData(
                category=EvidenceCategory.JIRA_ISSUES,
                reason="remaining estimate is unavailable",
                entity="task:WFD-14",
                required_for_claim=True,
            ),
        ),
    )

    validate_insufficiency_claim(
        "WFD-14 has no remaining estimate; add it before workload analysis.",
        evidence,
    )


def test_focused_completeness_requires_every_blocked_task() -> None:
    with pytest.raises(GroundingValidationError, match="WFD-13"):
        validate_focused_completeness(
            "WFD-4, WFD-5, and WFD-11 are blocked.", blocked_answer_evidence()
        )


def test_overdue_completeness_requires_only_overdue_tasks() -> None:
    evidence = AnswerEvidenceSet(
        question_focus="Which tasks are overdue?",
        tasks=(
            AnswerTaskEvidence(
                key="WFD-1",
                summary="Refresh token support",
                status="In Progress",
                priority="High",
                overdue=True,
            ),
            AnswerTaskEvidence(
                key="WFD-3",
                summary="Rotate signing keys",
                status="Idea",
                priority="High",
                overdue=True,
            ),
            AnswerTaskEvidence(
                key="WFD-4",
                summary="Database migration",
                status="Idea",
                priority="High",
                overdue=False,
            ),
        ),
        required_task_keys=("WFD-1", "WFD-3"),
        exhaustive=True,
    )

    validate_focused_completeness("WFD-1 and WFD-3 are overdue.", evidence)
    with pytest.raises(GroundingValidationError, match="WFD-3"):
        validate_focused_completeness("WFD-1 is overdue.", evidence)


def test_focused_completeness_does_not_require_supporting_tasks() -> None:
    evidence = AnswerEvidenceSet(
        question_focus="Which tasks need attention?",
        tasks=(
            AnswerTaskEvidence(
                key="WFD-1",
                summary="Direct result",
                status="In Progress",
                priority="High",
            ),
            AnswerTaskEvidence(
                key="WFD-2",
                summary="Supporting dependency",
                status="In Progress",
                priority="High",
            ),
        ),
        required_task_keys=("WFD-1",),
        exhaustive=True,
    )

    validate_focused_completeness("WFD-1 needs attention.", evidence)


def test_focused_completeness_requires_every_required_task() -> None:
    evidence = blocked_answer_evidence().model_copy(
        update={"required_task_keys": ("WFD-4", "WFD-5")}
    )

    with pytest.raises(GroundingValidationError, match="WFD-5"):
        validate_focused_completeness("WFD-4 is blocked.", evidence)


def test_focused_claims_reject_unknown_issue() -> None:
    with pytest.raises(GroundingValidationError, match="unknown Jira issue"):
        validate_focused_claims(
            "WFD-999 is blocked by WFD-2.", blocked_answer_evidence()
        )


def test_focused_claims_allow_issues_from_validated_project_snapshot() -> None:
    evidence = AnswerEvidenceSet(
        question_focus="Which employees are at risk and why?",
        employees=(),
        exhaustive=True,
    )

    validate_focused_claims(
        "WFD-11 is blocked by WFD-9.",
        evidence,
        allowed_issue_keys={"WFD-9", "WFD-11"},
    )


def test_focused_claims_distinguish_overlapping_employee_names() -> None:
    evidence = AnswerEvidenceSet(
        question_focus="Which employees are at risk and why?",
        employees=(
            AnswerEmployeeEvidence(
                employee_id="EMP-001",
                display_name="Mohammad Gnaiem",
                active_tasks=5,
                risk_level="high",
                top_risk="Over capacity",
            ),
            AnswerEmployeeEvidence(
                employee_id="EMP-002",
                display_name="Mohammad",
                active_tasks=2,
                risk_level="low",
                top_risk="Within capacity",
            ),
        ),
        exhaustive=True,
    )

    validate_focused_claims(
        "Mohammad Gnaiem is at high risk. Mohammad is at low risk.", evidence
    )


def test_focused_claims_treat_known_employee_id_as_employee_not_jira_issue() -> None:
    evidence = AnswerEvidenceSet(
        question_focus="Which workload cannot be classified reliably?",
        employees=(
            AnswerEmployeeEvidence(
                employee_id="EMP-004",
                display_name="gnaiem",
                active_tasks=4,
                risk_level="insufficient-data",
                top_risk="Missing remaining estimate",
            ),
        ),
        exhaustive=True,
    )

    validate_focused_claims(
        "EMP-004 cannot be classified because a remaining estimate is missing.",
        evidence,
    )


def test_focused_completeness_requires_only_unclassified_employee_subset() -> None:
    evidence = AnswerEvidenceSet(
        question_focus=(
            "Are there any employees whose current workload cannot be classified "
            "reliably? Why?"
        ),
        employees=(
            AnswerEmployeeEvidence(
                employee_id="EMP-001",
                display_name="Mohammad Gnaiem",
                active_tasks=5,
                risk_level="high",
                top_risk="Over capacity",
            ),
            AnswerEmployeeEvidence(
                employee_id="EMP-004",
                display_name="gnaiem",
                active_tasks=4,
                risk_level="insufficient-data",
                top_risk="Missing remaining estimate",
            ),
        ),
        exhaustive=True,
    )

    validate_focused_completeness(
        "gnaiem cannot be classified because one task has no remaining estimate.",
        evidence,
    )


def test_focused_claims_reject_dependency_promoted_to_ranked_task() -> None:
    with pytest.raises(GroundingValidationError, match="dependency-only"):
        validate_focused_claims(
            "1. **WFD-9: Dashboard charts** — due 2026-08-24.",
            blocked_answer_evidence(),
        )


@pytest.mark.asyncio
async def test_grounding_rejects_configured_capacity_as_available_capacity() -> None:
    bundle = await UniversalEvidenceCollector(ProjectTool()).collect(
        EvidencePlan(
            scope=EvidenceScope.PROJECT,
            evidence_categories=(EvidenceCategory.CAPACITY_AND_WORKLOAD,),
        ),
        project_key="WFD",
        correlation_id="corr-1",
    )

    with pytest.raises(GroundingValidationError, match="available capacity"):
        validate_universal_claims("A has 24 hours available.", bundle)


@pytest.mark.asyncio
async def test_employee_risk_list_does_not_require_dependency_task_list() -> None:
    bundle = await UniversalEvidenceCollector(ProjectTool()).collect(
        EvidencePlan(
            scope=EvidenceScope.EMPLOYEE,
            evidence_categories=(
                EvidenceCategory.CAPACITY_AND_WORKLOAD,
                EvidenceCategory.DEPENDENCIES_AND_BLOCKERS,
            ),
            exhaustive=True,
        ),
        project_key="WFD",
        correlation_id="corr-employee-risk",
    )
    assert bundle.project_snapshot is not None
    snapshot = bundle.project_snapshot.model_copy(
        update={
            "tasks": (
                TaskSummary(
                    key="WFD-11",
                    summary="Prepare release",
                    status="Testing",
                    priority="High",
                    assignee_id="EMP-1",
                    assignee_name="A",
                    due_date=None,
                    original_hours=4,
                    remaining_hours=3,
                    required_skills=(),
                    blocker=None,
                    dependencies=("is blocked by: WFD-9",),
                    jira_url="https://example.atlassian.net/browse/WFD-11",
                ),
            )
        }
    )
    bundle = bundle.model_copy(update={"project_snapshot": snapshot})

    validate_universal_completeness(
        "A is at high risk because 36 hours of work exceeds 24 hours of capacity.",
        bundle,
    )


@pytest.mark.asyncio
async def test_exhaustive_employee_answer_must_name_every_employee() -> None:
    bundle = await UniversalEvidenceCollector(ProjectTool()).collect(
        EvidencePlan(
            scope=EvidenceScope.MIXED,
            evidence_categories=(EvidenceCategory.CAPACITY_AND_WORKLOAD,),
            exhaustive=True,
        ),
        project_key="WFD",
        correlation_id="corr-all-employees",
    )

    with pytest.raises(GroundingValidationError, match="employee"):
        validate_universal_completeness("Some employees are at risk.", bundle)


@pytest.mark.asyncio
async def test_grounding_rejects_incorrect_capacity_overage() -> None:
    bundle = await UniversalEvidenceCollector(ProjectTool()).collect(
        EvidencePlan(
            scope=EvidenceScope.EMPLOYEE,
            evidence_categories=(EvidenceCategory.CAPACITY_AND_WORKLOAD,),
        ),
        project_key="WFD",
        correlation_id="corr-overage",
    )

    with pytest.raises(GroundingValidationError, match="capacity overage"):
        validate_universal_claims(
            "A is at high risk because the workload exceeds capacity by 36 hours.",
            bundle,
        )


@pytest.mark.asyncio
async def test_grounding_distinguishes_overlapping_employee_names() -> None:
    bundle = await UniversalEvidenceCollector(ProjectTool()).collect(
        EvidencePlan(
            scope=EvidenceScope.EMPLOYEE,
            evidence_categories=(EvidenceCategory.CAPACITY_AND_WORKLOAD,),
        ),
        project_key="WFD",
        correlation_id="corr-overlapping-names",
    )
    assert bundle.project_snapshot is not None
    first = bundle.project_snapshot.employees[0].model_copy(
        update={"display_name": "Mohammad Gnaiem", "level": "high"}
    )
    second = first.model_copy(
        update={
            "employee_id": "EMP-2",
            "display_name": "Mohammad",
            "capacity_hours": 28,
            "remaining_hours": 12,
            "score": 17,
            "level": "low",
        }
    )
    snapshot = bundle.project_snapshot.model_copy(update={"employees": (first, second)})
    bundle = bundle.model_copy(update={"project_snapshot": snapshot})

    validate_universal_claims(
        "Mohammad Gnaiem is at high risk. Mohammad is at low risk.", bundle
    )
