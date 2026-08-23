from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from agent_api.auth.roles import ApplicationRole
from agent_api.dashboard.models import (
    DashboardSnapshot,
    ProjectSummary,
    WorkloadDistribution,
)
from agent_api.evidence.models import EvidenceCategory, EvidencePlan, EvidenceScope
from agent_api.graph.intents import Intent
from agent_api.graph.state import EntityReferences, VerifiedAgentContext
from agent_api.graph.workflow import InvestigationWorkflow
from agent_api.llm.bedrock import BedrockExplanationProvider
from agent_api.llm.fallback import DeterministicFallbackProvider
from agent_api.llm.schemas import ExplanationRequest, ExplanationResponse
from agent_api.task_queries import GroundedAnswerContext, TaskFact


def snapshot() -> DashboardSnapshot:
    return DashboardSnapshot(
        correlation_id="corr-project-chat",
        evidence_timestamp=datetime(2026, 8, 20, tzinfo=UTC),
        project=ProjectSummary(
            key="WFD",
            name="Workforce Real Data",
            total_tasks=15,
            completed_tasks=1,
            active_tasks=14,
            overdue_tasks=2,
            due_soon_tasks=5,
            blocked_tasks=3,
            missing_estimate_tasks=1,
            completion_percent=7,
        ),
        employees=(),
        tasks=(),
        alerts=(),
        workload=WorkloadDistribution(overloaded=1, balanced=3, insufficient_data=0),
    )


class ProjectTool:
    calls = 0

    async def build(self, project_key: str, correlation_id: str) -> DashboardSnapshot:
        self.calls += 1
        assert project_key == "WFD"
        assert correlation_id == "corr-project-chat"
        return snapshot()


class CoreTool:
    async def investigate(
        self, intent: Any, references: Any, correlation_id: str
    ) -> Any:
        raise AssertionError("project chat must not fabricate an employee risk")


class UnsupportedTaskQueryTool:
    calls = 0

    async def query(
        self,
        question: str,
        references: EntityReferences,
        correlation_id: str,
        *,
        previous_context: GroundedAnswerContext | None = None,
    ) -> Any:
        del previous_context
        self.calls += 1
        raise ValueError("employee is required for a deadline task query")


class Explainer:
    request: ExplanationRequest | None = None
    plans = 0

    async def plan_evidence(self, **_: object) -> EvidencePlan:
        self.plans += 1
        return EvidencePlan(
            scope=EvidenceScope.MIXED,
            evidence_categories=(
                EvidenceCategory.JIRA_ISSUES,
                EvidenceCategory.WORKFORCE_PROFILES,
                EvidenceCategory.CAPACITY_AND_WORKLOAD,
                EvidenceCategory.SKILLS_AND_SENIORITY,
                EvidenceCategory.RISK_RESULTS,
            ),
            exhaustive=True,
        )

    async def explain(self, request: ExplanationRequest) -> ExplanationResponse:
        self.request = request
        return ExplanationResponse(
            answer="WFD has 14 active tasks, including two overdue tasks.",
            summary="Project delivery summary",
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
async def test_project_question_sends_dashboard_snapshot_to_bedrock() -> None:
    explainer = Explainer()
    workflow = InvestigationWorkflow(
        tool=CoreTool(), project_tool=ProjectTool(), explainer=explainer
    )

    result = await workflow.run(
        verified_context=VerifiedAgentContext(
            subject_reference="anonymous-demo-viewer",
            roles=(ApplicationRole.VIEWER,),
            environment="test",
            authorized_jira_sites=("site",),
            authorized_project_keys=("WFD",),
            correlation_id="corr-project-chat",
        ),
        question="Summarize all work in this project",
        references=EntityReferences(project_key="WFD"),
    )

    assert result.explanation is not None
    assert result.explanation.source == "bedrock"
    assert result.risk is None
    assert explainer.request is not None
    assert explainer.request.project_snapshot is not None
    assert explainer.request.project_snapshot.project.total_tasks == 15
    assert explainer.request.universal_evidence is not None
    assert explainer.plans == 1
    assert result.answer_context is not None
    assert result.answer_context.exhaustive is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        "Which employee would be the best candidate to take work from Mohammad "
        "Gnaiem, based on both capacity and skills?",
        "Are there any employees whose current workload cannot be classified "
        "reliably? Why?",
    ],
)
async def test_general_questions_bypass_fixed_specialist_failures(
    question: str,
) -> None:
    explainer = Explainer()
    workflow = InvestigationWorkflow(
        tool=CoreTool(), project_tool=ProjectTool(), explainer=explainer
    )

    result = await workflow.run(
        verified_context=VerifiedAgentContext(
            subject_reference="anonymous-demo-viewer",
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
    assert explainer.request is not None
    assert explainer.request.universal_evidence is not None


@pytest.mark.asyncio
async def test_follow_up_passes_previous_blocked_work_context_to_bedrock() -> None:
    explainer = Explainer()
    previous = GroundedAnswerContext(
        intent="blocked_tasks",
        previous_question="Which work is blocked right now?",
        issues=(
            TaskFact(key="WFD-4", summary="Migration", status="Idea"),
            TaskFact(key="WFD-5", summary="Security review", status="Testing"),
        ),
    )
    workflow = InvestigationWorkflow(
        tool=CoreTool(), project_tool=ProjectTool(), explainer=explainer
    )

    result = await workflow.run(
        verified_context=VerifiedAgentContext(
            subject_reference="anonymous-demo-viewer",
            roles=(ApplicationRole.VIEWER,),
            environment="test",
            authorized_jira_sites=("site",),
            authorized_project_keys=("WFD",),
            correlation_id="corr-project-chat",
        ),
        question="How urgent is this risk?",
        references=EntityReferences(project_key="WFD"),
        previous_answer_context=previous,
    )

    assert result.explanation is not None
    assert explainer.request is not None
    assert explainer.request.previous_answer_context == previous


@pytest.mark.asyncio
async def test_ambiguous_singular_follow_up_reaches_bedrock_as_clarification() -> None:
    explainer = Explainer()
    previous = GroundedAnswerContext(
        intent="list_tasks",
        issues=(
            TaskFact(key="WFD-4", summary="Migration", status="Idea"),
            TaskFact(key="WFD-5", summary="Review", status="Testing"),
        ),
    )

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
        question="Who owns that task?",
        references=EntityReferences(project_key="WFD"),
        previous_answer_context=previous,
    )

    assert result.explanation is not None
    assert explainer.request is not None
    assert explainer.request.universal_evidence is not None
    assert [
        entity.identifier
        for entity in explainer.request.universal_evidence.ambiguous_references
    ] == ["WFD-4", "WFD-5"]


@pytest.mark.asyncio
async def test_broad_workforce_question_sends_project_snapshot_to_bedrock() -> None:
    explainer = Explainer()
    project_tool = ProjectTool()
    task_query_tool = UnsupportedTaskQueryTool()
    workflow = InvestigationWorkflow(
        tool=CoreTool(),
        task_query_tool=task_query_tool,
        project_tool=project_tool,
        explainer=explainer,
    )

    result = await workflow.run(
        verified_context=VerifiedAgentContext(
            subject_reference="anonymous-demo-viewer",
            roles=(ApplicationRole.VIEWER,),
            environment="test",
            authorized_jira_sites=("site",),
            authorized_project_keys=("WFD",),
            correlation_id="corr-project-chat",
        ),
        question="Which employees are at risk and why?",
        references=EntityReferences(project_key="WFD"),
    )

    assert result.intent is Intent.EXPLAIN_PROJECT_RISK
    assert result.explanation is not None
    assert result.explanation.source == "bedrock"
    assert task_query_tool.calls == 0
    assert project_tool.calls == 1
    assert explainer.request is not None
    assert explainer.request.task_query_result is None
    assert explainer.request.project_snapshot is not None


@pytest.mark.asyncio
async def test_bedrock_only_mode_never_returns_deterministic_prose() -> None:
    async def unavailable(system_prompt: str, payload: dict[str, object]) -> str:
        raise OSError("unavailable")

    provider = BedrockExplanationProvider(
        invoke=unavailable,
        allow_fallback=False,
        max_attempts=1,
    )

    with pytest.raises(OSError, match="invocation failed"):
        await provider.explain(
            ExplanationRequest(
                workflow="explain_project_risk",
                question="Summarize WFD",
                project_snapshot=snapshot(),
                correlation_id="corr-project-chat",
            )
        )


@pytest.mark.asyncio
async def test_project_chat_discards_unsupported_model_score_and_candidate() -> None:
    async def invoke(system_prompt: str, payload: dict[str, object]) -> str:
        return json.dumps(
            {
                "answer": (
                    "The project has urgent blocked work in WRD-8 and missing "
                    "estimates across several active tasks. Review WRD-8 first "
                    "because its blocker and approaching deadline create the "
                    "clearest delivery concern. Confirm the missing estimates "
                    "before making a broader workload decision."
                ),
                "summary": "Project risk summary",
                "root_causes": ["Blocked work"],
                "recommendations": [
                    {
                        "action": "review",
                        "reason": "Inspect WRD-8",
                        "candidate_id": "invented-user",
                    }
                ],
                "citations": [
                    "jira:WRD-8:summary",
                    "jira:WRD-8:updated",
                    "jira:WRD-8:labels",
                    "jira:OTHER-1:summary",
                ],
                "score": 80,
                "risk_level": "high",
                "uncertainties": ["Missing estimates"],
            }
        )

    project_data = snapshot().model_dump()
    project_data["tasks"] = (
        {
            "key": "WRD-8",
            "summary": "Database migration",
            "status": "Blocked",
            "priority": "Highest",
            "assignee_id": None,
            "assignee_name": None,
            "due_date": None,
            "original_hours": None,
            "remaining_hours": None,
            "required_skills": (),
            "blocker": "Technical blocker",
            "dependencies": (),
            "jira_url": "https://example.atlassian.net/browse/WRD-8",
        },
    )
    project = DashboardSnapshot.model_validate(project_data)
    provider = BedrockExplanationProvider(
        invoke=invoke, allow_fallback=False, max_attempts=1
    )

    result = await provider.explain(
        ExplanationRequest(
            workflow="explain_project_risk",
            question="Summarize project risk",
            project_snapshot=project,
            correlation_id="corr-project-chat",
        )
    )

    assert result.source == "bedrock"
    assert result.score is None
    assert result.risk_level is None
    assert result.recommendations[0].candidate_id is None
    assert "jira:OTHER-1:summary" not in result.citations


@pytest.mark.asyncio
async def test_project_chat_rejects_unknown_jira_issue_claim() -> None:
    async def invoke(system_prompt: str, payload: dict[str, object]) -> str:
        if "conservative" in system_prompt.casefold():
            return "I do not have enough reliable information to answer confidently."
        return json.dumps(
            {
                "answer": "WRD-8 is blocked; inspect it first.",
                "summary": "Current project evidence",
                "root_causes": ["Blocked work"],
                "recommendations": [],
                "citations": [],
                "score": None,
                "risk_level": None,
                "uncertainties": [],
            }
        )

    provider = BedrockExplanationProvider(
        invoke=invoke, allow_fallback=False, max_attempts=1
    )
    result = await provider.explain(
        ExplanationRequest(
            workflow="explain_project_risk",
            question="What is blocked?",
            project_snapshot=snapshot(),
            correlation_id="corr-project-chat",
        )
    )

    assert result.source == "bedrock"
    assert "enough reliable information" in (result.answer or "")


@pytest.mark.asyncio
async def test_deadline_question_retries_generic_answer_without_task_keys() -> None:
    attempts = 0

    async def invoke(system_prompt: str, payload: dict[str, object]) -> str:
        nonlocal attempts
        attempts += 1
        answer = (
            "Tasks with dependencies and blockers are most likely to miss deadlines."
            if attempts == 1
            else (
                "WRD-8 is most likely to miss its deadline; it is blocked and due soon."
            )
        )
        return json.dumps(
            {
                "answer": answer,
                "summary": "Deadline risk",
                "root_causes": ["Blocked work"],
                "recommendations": [],
                "citations": ["jira:WRD-8:summary"],
                "score": None,
                "risk_level": None,
                "uncertainties": [],
            }
        )

    provider = BedrockExplanationProvider(
        invoke=invoke, allow_fallback=False, max_attempts=2
    )
    project_data = snapshot().model_dump()
    project_data["tasks"] = (
        {
            "key": "WRD-8",
            "summary": "Database migration",
            "status": "Blocked",
            "priority": "Highest",
            "assignee_id": None,
            "assignee_name": None,
            "due_date": None,
            "original_hours": None,
            "remaining_hours": None,
            "required_skills": (),
            "blocker": "Technical blocker",
            "dependencies": (),
            "jira_url": "https://example.atlassian.net/browse/WRD-8",
        },
    )
    result = await provider.explain(
        ExplanationRequest(
            workflow="explain_project_risk",
            question="Which tasks are most likely to miss their deadlines?",
            project_snapshot=DashboardSnapshot.model_validate(project_data),
            correlation_id="corr-project-chat",
        )
    )

    assert attempts == 2
    assert result.answer is not None
    assert "WRD-8" in result.answer


@pytest.mark.asyncio
async def test_project_chat_rejects_at_risk_claim_for_insufficient_employee() -> None:
    attempts = 0

    async def invoke(system_prompt: str, payload: dict[str, object]) -> str:
        nonlocal attempts
        attempts += 1
        answer = (
            "Mohammad is at risk because one task has a missing estimate."
            if attempts == 1
            else (
                "Mohammad has insufficient data for an employee risk level. "
                "The missing estimate is a planning-data warning, not proof "
                "of overload."
            )
        )
        return json.dumps(
            {
                "answer": answer,
                "summary": "Workforce status",
                "root_causes": [],
                "recommendations": [],
                "citations": [],
                "score": None,
                "risk_level": None,
                "uncertainties": ["Missing estimate"],
            }
        )

    project_data = snapshot().model_dump()
    project_data["employees"] = (
        {
            "employee_id": "EMP-001",
            "display_name": "Mohammad",
            "role": "Engineer",
            "skills": (),
            "capacity_hours": None,
            "remaining_hours": None,
            "active_tasks": 1,
            "score": None,
            "level": "insufficient-data",
            "top_risk": "One task is missing a remaining estimate.",
        },
    )
    provider = BedrockExplanationProvider(
        invoke=invoke, allow_fallback=False, max_attempts=2
    )

    result = await provider.explain(
        ExplanationRequest(
            workflow="explain_project_risk",
            question="Which employees are at risk and why?",
            project_snapshot=DashboardSnapshot.model_validate(project_data),
            correlation_id="corr-project-chat",
        )
    )

    assert attempts == 2
    assert result.answer is not None
    assert "insufficient data" in result.answer.casefold()


@pytest.mark.asyncio
async def test_deterministic_fallback_refuses_project_chat() -> None:
    with pytest.raises(ValueError, match="requires a risk result"):
        await DeterministicFallbackProvider().explain(
            ExplanationRequest(
                workflow="explain_project_risk",
                question="Summarize WFD",
                project_snapshot=snapshot(),
                correlation_id="corr-project-chat",
            )
        )
