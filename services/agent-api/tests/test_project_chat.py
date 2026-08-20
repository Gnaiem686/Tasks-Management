from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import agent_api.graph.supervisor as supervisor
import pytest
from agent_api.auth.roles import ApplicationRole
from agent_api.dashboard.models import (
    DashboardSnapshot,
    ProjectSummary,
    WorkloadDistribution,
)
from agent_api.graph.intents import Intent
from agent_api.graph.state import EntityReferences, VerifiedAgentContext
from agent_api.graph.workflow import InvestigationWorkflow
from agent_api.llm.bedrock import BedrockExplanationProvider
from agent_api.llm.fallback import DeterministicFallbackProvider
from agent_api.llm.schemas import ExplanationRequest, ExplanationResponse


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
        self, question: str, references: EntityReferences, correlation_id: str
    ) -> Any:
        self.calls += 1
        raise ValueError("employee is required for a deadline task query")


class Explainer:
    request: ExplanationRequest | None = None

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


@pytest.mark.asyncio
async def test_broad_workforce_question_falls_back_to_project_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        supervisor,
        "classify_intent",
        lambda question, *, default_scope=None: Intent.JIRA_TASK_QUERY,
    )
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
    assert task_query_tool.calls == 1
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
async def test_project_chat_accepts_concise_bedrock_prose() -> None:
    async def invoke(system_prompt: str, payload: dict[str, object]) -> str:
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
    assert result.answer == "WRD-8 is blocked; inspect it first."


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
