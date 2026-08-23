from agent_api.evidence.models import (
    EvidenceCategory,
    EvidenceEntity,
    EvidencePlan,
    EvidenceScope,
)
from agent_api.evidence.normalizer import normalize_evidence_plan
from agent_api.evidence.planner import conservative_read_plan
from agent_api.task_queries import GroundedAnswerContext, TaskFact


def test_blocked_work_normalizes_to_exhaustive_task_evidence() -> None:
    result = normalize_evidence_plan(
        question="Which work is blocked right now?",
        planned=conservative_read_plan(),
        previous_context=None,
    )

    assert result.scope is EvidenceScope.TASK
    assert result.exhaustive is True
    assert EvidenceCategory.JIRA_ISSUES in result.evidence_categories
    assert EvidenceCategory.DEPENDENCIES_AND_BLOCKERS in result.evidence_categories


def test_plural_follow_up_preserves_prior_task_entities() -> None:
    previous = GroundedAnswerContext(
        intent="deadline_risk",
        issues=(
            TaskFact(key="WFD-11", summary="Release", status="Testing"),
            TaskFact(key="WFD-13", summary="Deploy", status="Idea"),
        ),
    )

    result = normalize_evidence_plan(
        question="Name those tasks",
        planned=conservative_read_plan(),
        previous_context=previous,
    )

    assert result.scope is EvidenceScope.TASK
    assert [item.identifier for item in result.entities] == ["WFD-11", "WFD-13"]


def test_employee_capacity_question_keeps_employee_evidence() -> None:
    result = normalize_evidence_plan(
        question="Who has available capacity and the relevant skills to help?",
        planned=conservative_read_plan(),
        previous_context=None,
    )

    assert result.scope is EvidenceScope.EMPLOYEE
    assert EvidenceCategory.CAPACITY_AND_WORKLOAD in result.evidence_categories
    assert EvidenceCategory.SKILLS_AND_SENIORITY in result.evidence_categories


def test_project_wide_employee_question_drops_stale_task_entity_hints() -> None:
    previous = GroundedAnswerContext(
        intent="deadline_risk",
        issues=(TaskFact(key="WFD-4", summary="Migration", status="Idea"),),
    )
    planned = EvidencePlan(
        scope=EvidenceScope.TASK,
        entities=(
            EvidenceEntity(kind="task", identifier="WFD-4"),
            EvidenceEntity(kind="employee", identifier="EMP-002"),
        ),
        evidence_categories=(EvidenceCategory.JIRA_ISSUES,),
        exhaustive=True,
    )

    result = normalize_evidence_plan(
        question="Which employees are at risk and why?",
        planned=planned,
        previous_context=previous,
    )

    assert result.scope is EvidenceScope.EMPLOYEE
    assert result.entities == ()


def test_unknown_question_retains_broad_read_only_plan() -> None:
    planned = conservative_read_plan()

    result = normalize_evidence_plan(
        question="What should I know about this project?",
        planned=planned,
        previous_context=None,
    )

    assert result.scope is EvidenceScope.MIXED
    assert set(result.evidence_categories) == set(EvidenceCategory)


def test_progress_comparison_requires_history_evidence() -> None:
    result = normalize_evidence_plan(
        question="Has Employee 3 improved since yesterday?",
        planned=EvidencePlan(
            scope=EvidenceScope.EMPLOYEE,
            evidence_categories=(EvidenceCategory.WORKFORCE_PROFILES,),
        ),
        previous_context=None,
    )

    assert EvidenceCategory.HISTORY in result.evidence_categories
