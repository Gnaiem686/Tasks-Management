from __future__ import annotations

from typing import Any

import pytest
from agent_api.auth.roles import ApplicationRole
from agent_api.graph.intents import Intent
from agent_api.graph.state import EntityReferences, VerifiedAgentContext
from agent_api.graph.workflow import InvestigationWorkflow
from agent_api.llm.bedrock import BedrockExplanationProvider
from agent_api.llm.schemas import ExplanationRequest
from agent_api.task_queries import GroundedAnswerContext, TaskFact
from test_project_chat import CoreTool, ProjectTool, snapshot
from workforce_risk.models import RiskResult


class PlainBedrock:
    plans = 0

    async def plan_evidence(self, **_: object) -> Any:
        self.plans += 1
        return {
            "scope": "mixed",
            "entities": [],
            "evidence_categories": [
                "jira_issues",
                "workforce_profiles",
                "capacity_and_workload",
                "skills_and_seniority",
                "history",
            ],
            "exhaustive": True,
        }

    async def explain(self, request: ExplanationRequest) -> Any:
        return await BedrockExplanationProvider(
            invoke=lambda _system, _payload: _answer(),
            allow_fallback=False,
            max_attempts=1,
        ).explain(request)


class OverloadOnlyTool:
    async def investigate(
        self, intent: Intent, references: EntityReferences, correlation_id: str
    ) -> RiskResult:
        raise ValueError("the requested deterministic domain tool is unavailable")


async def _answer() -> str:
    return "I do not have enough complete evidence to answer this confidently."


def _context() -> VerifiedAgentContext:
    return VerifiedAgentContext(
        subject_reference="viewer",
        roles=(ApplicationRole.VIEWER,),
        environment="test",
        authorized_jira_sites=("site",),
        authorized_project_keys=("WFD",),
        correlation_id="corr-project-chat",
    )


def test_chat_workflow_deadline_is_configurable_for_grounding_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHAT_WORKFLOW_DEADLINE_SECONDS", "45")

    workflow = InvestigationWorkflow(
        tool=CoreTool(), project_tool=ProjectTool(), explainer=PlainBedrock()
    )

    assert workflow._deadline_seconds == 45.0


def test_zero_chat_workflow_deadline_waits_for_bedrock_until_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHAT_WORKFLOW_DEADLINE_SECONDS", "0")

    workflow = InvestigationWorkflow(
        tool=CoreTool(), project_tool=ProjectTool(), explainer=PlainBedrock()
    )

    assert workflow._deadline_seconds is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    (
        "Which employee would be the best candidate to take work from Mohammad "
        "Gnaiem, based on both capacity and skills?",
        "Are there any employees whose current workload cannot be classified "
        "reliably? Why?",
        "Could somebody else take that task?",
        "Who would be the best candidate and why?",
    ),
)
async def test_reported_normal_questions_complete_without_service_error(
    question: str,
) -> None:
    previous = GroundedAnswerContext(
        intent="tasks",
        issues=(TaskFact(key="WFD-4", summary="Migration", status="Idea"),),
    )
    result = await InvestigationWorkflow(
        tool=CoreTool(), project_tool=ProjectTool(), explainer=PlainBedrock()
    ).run(
        verified_context=_context(),
        question=question,
        references=EntityReferences(project_key="WFD"),
        previous_answer_context=previous,
    )

    assert result.explanation is not None
    assert result.explanation.source == "bedrock"


@pytest.mark.asyncio
async def test_ambiguous_reference_is_bedrock_clarification_not_exception() -> None:
    previous = GroundedAnswerContext(
        intent="tasks",
        issues=(
            TaskFact(key="WFD-4", summary="Migration", status="Idea"),
            TaskFact(key="WFD-5", summary="Review", status="Testing"),
        ),
    )
    explainer = PlainBedrock()
    result = await InvestigationWorkflow(
        tool=CoreTool(), project_tool=ProjectTool(), explainer=explainer
    ).run(
        verified_context=_context(),
        question="Could somebody else take that task?",
        references=EntityReferences(project_key="WFD"),
        previous_answer_context=previous,
    )

    assert result.explanation is not None
    assert result.explanation.source == "bedrock"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    (
        "Which employees are at risk and why?",
        "Which tasks are most likely to miss their deadlines?",
        "Which work is blocked right now?",
        "Has this employee's situation improved?",
        (
            "Which employee would be the best candidate to take work from "
            "Mohammad Gnaiem, based on both capacity and skills?"
        ),
    ),
)
async def test_candidate_question_with_unavailable_optional_evidence_reaches_bedrock(
    question: str,
) -> None:
    result = await InvestigationWorkflow(
        tool=OverloadOnlyTool(), explainer=PlainBedrock()
    ).run(
        verified_context=_context(),
        question=question,
        references=EntityReferences(project_key="WFD"),
    )

    assert result.explanation is not None
    assert result.explanation.source == "bedrock"


@pytest.mark.asyncio
async def test_persistent_bedrock_failure_remains_service_failure() -> None:
    async def unavailable(_system: str, _payload: dict[str, object]) -> str:
        raise OSError("Bedrock unavailable")

    with pytest.raises(OSError, match="Bedrock explanation invocation failed"):
        await BedrockExplanationProvider(
            invoke=unavailable, allow_fallback=False, max_attempts=2
        ).explain(
            ExplanationRequest(
                workflow="general_evidence_question",
                question="What is happening?",
                project_snapshot=snapshot(),
                correlation_id="corr-outage",
            )
        )
