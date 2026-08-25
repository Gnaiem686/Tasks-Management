from __future__ import annotations

import pytest
from agent_api.auth.roles import ApplicationRole
from agent_api.dashboard.models import DashboardSnapshot
from agent_api.evidence.models import EvidencePlan
from agent_api.evidence.planner import conservative_read_plan
from agent_api.graph.state import EntityReferences, VerifiedAgentContext
from agent_api.graph.workflow import InvestigationWorkflow
from agent_api.llm.schemas import ExplanationRequest, ExplanationResponse
from agent_api.task_queries import GroundedAnswerContext, TaskFact
from test_answer_evidence_focus import wfd_snapshot
from test_project_chat import CoreTool, Explainer, ProjectTool

UNSEEN_QUESTIONS = (
    "Who has enough room and matching expertise to absorb Mohammad Gnaiem's work?",
    "Across the team, whose workload cannot be judged confidently and what is absent?",
    "Walk me through the pressure on this delivery in ordinary language.",
    "Where is planned work greater than people's weekly room?",
    "Which assignments depend on unfinished upstream work?",
    "Show every deadline that deserves management attention.",
    "Whose documented background is weak for their hardest assignment?",
    "What changed since the earlier risk observation?",
    "Where are estimates absent, and what conclusions does that prevent?",
    "Which review bottleneck has the broadest downstream effect?",
    "What should the delivery manager investigate first this morning?",
    "Is workload concentrated on one person even if the project score looks safe?",
    "Could moving the urgent Java work create overload somewhere else?",
    "Which people have positive headroom after their remaining assignments?",
    "Explain the difference between employee pressure and task delivery danger here.",
    "What evidence would you need before recommending a new owner?",
    "Are any critical assignments approaching their dates without matching skills?",
    "Give me the complete set of blocked or dependent work.",
    "Which current conclusions rely on incomplete planning data?",
    "Summarize the team situation and distinguish facts from recommendations.",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("question", UNSEEN_QUESTIONS)
async def test_unseen_project_question_needs_no_phrase_handler(question: str) -> None:
    explainer = Explainer()
    result = await InvestigationWorkflow(
        tool=CoreTool(), project_tool=ProjectTool(), explainer=explainer
    ).run(
        verified_context=VerifiedAgentContext(
            subject_reference="viewer",
            roles=(ApplicationRole.VIEWER,),
            environment="test",
            authorized_jira_sites=("site",),
            authorized_project_keys=("WFD",),
            correlation_id="corr-project-chat",
        ),
        question=question,
        references=EntityReferences(project_key="WFD"),
    )
    assert result.explanation is not None
    assert result.explanation.source == "bedrock"
    assert explainer.plans == 1


class WfdProjectTool:
    async def build(self, _project_key: str, _correlation_id: str) -> DashboardSnapshot:
        return wfd_snapshot()


class FocusedBedrockStub:
    async def plan_evidence(self, **_: object) -> EvidencePlan:
        return conservative_read_plan()

    async def explain(self, request: ExplanationRequest) -> ExplanationResponse:
        assert request.universal_evidence is not None
        focused = request.universal_evidence.answer_evidence
        assert focused is not None
        entities = [task.key for task in focused.tasks] + [
            employee.display_name for employee in focused.employees
        ]
        answer = "The validated evidence covers " + ", ".join(entities) + "."
        return ExplanationResponse(
            answer=answer,
            summary=answer,
            root_causes=(),
            recommendations=(),
            citations=(),
            score=None,
            risk_level=None,
            uncertainties=(),
            source="bedrock",
            correlation_id=request.correlation_id,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "expected_tasks", "expected_employees"),
    [
        (
            "Which work is blocked right now?",
            ("WFD-4", "WFD-5", "WFD-11", "WFD-13"),
            ("EMP-002", "EMP-003", "EMP-004"),
        ),
        (
            "Who owns WFD-11 and what is blocking it?",
            ("WFD-11",),
            ("EMP-003",),
        ),
        (
            "Who has available capacity and the relevant skills to help?",
            (),
            ("EMP-002", "EMP-003", "EMP-004"),
        ),
    ],
)
async def test_question_matrix_retains_exact_focused_context(
    question: str,
    expected_tasks: tuple[str, ...],
    expected_employees: tuple[str, ...],
) -> None:
    result = await InvestigationWorkflow(
        tool=CoreTool(), project_tool=WfdProjectTool(), explainer=FocusedBedrockStub()
    ).run(
        verified_context=VerifiedAgentContext(
            subject_reference="viewer",
            roles=(ApplicationRole.VIEWER,),
            environment="test",
            authorized_jira_sites=("site",),
            authorized_project_keys=("WFD",),
            correlation_id="corr-matrix",
        ),
        question=question,
        references=EntityReferences(project_key="WFD"),
    )

    assert result.explanation is not None
    assert result.explanation.source == "bedrock"
    assert result.answer_context is not None
    if expected_tasks:
        assert (
            tuple(task.key for task in result.answer_context.issues) == expected_tasks
        )
    assert result.answer_context.employee_ids == expected_employees
    answer = result.explanation.answer or ""
    assert all(key in answer for key in expected_tasks)


@pytest.mark.asyncio
async def test_plural_task_follow_up_keeps_the_previous_focused_set() -> None:
    previous = GroundedAnswerContext(
        intent="deadline_risk",
        issues=(
            TaskFact(key="WFD-11", summary="Release", status="Testing"),
            TaskFact(key="WFD-13", summary="Deploy", status="Idea"),
        ),
        exhaustive=True,
    )
    result = await InvestigationWorkflow(
        tool=CoreTool(), project_tool=WfdProjectTool(), explainer=FocusedBedrockStub()
    ).run(
        verified_context=VerifiedAgentContext(
            subject_reference="viewer",
            roles=(ApplicationRole.VIEWER,),
            environment="test",
            authorized_jira_sites=("site",),
            authorized_project_keys=("WFD",),
            correlation_id="corr-follow-up-matrix",
        ),
        question="Name those tasks",
        references=EntityReferences(project_key="WFD"),
        previous_answer_context=previous,
    )

    assert result.answer_context is not None
    assert tuple(task.key for task in result.answer_context.issues) == (
        "WFD-11",
        "WFD-13",
    )
