from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from agent_api.auth.roles import ApplicationRole
from agent_api.graph.intents import Intent, classify_intent
from agent_api.graph.state import EntityReferences, VerifiedAgentContext
from agent_api.graph.workflow import InvestigationWorkflow
from agent_api.historical_evidence import HistoricalRiskContext
from agent_api.llm.schemas import (
    ExplanationRequest,
    ExplanationResponse,
    Recommendation,
)
from agent_api.risk_evidence import RiskEvidenceDossier
from agent_api.task_queries import TaskFact, TaskQueryResult
from workforce_risk.models import RiskResult


class Tool:
    calls = 0

    async def investigate(
        self, intent: Intent, references: EntityReferences, correlation_id: str
    ) -> RiskResult:
        self.calls += 1
        return RiskResult.model_validate(
            {
                "subject_id": references.employee_id
                or references.project_id
                or "WRD-1",
                "environment": "test",
                "score": 77,
                "level": "critical",
                "confidence": "high",
                "scored_at": datetime.now(UTC),
                "evidence_timestamp": datetime.now(UTC),
                "scoring_model_version": "employee-overload-v1",
                "factors": [],
                "thresholds": {},
                "evidence_references": ["jira:WRD-1:status"],
                "missing_evidence": [],
                "excluded_evidence": [],
            }
        )


class Explainer:
    async def explain(self, request: ExplanationRequest) -> ExplanationResponse:
        return ExplanationResponse(
            summary="Deterministic risk is high.",
            root_causes=(),
            recommendations=(
                Recommendation(action="review", reason="Review evidence"),
            ),
            citations=("jira:WRD-1:status",),
            score=77,
            risk_level="critical",
            uncertainties=(),
            source="deterministic_fallback",
            correlation_id="corr-graph",
        )


class DossierTool:
    async def get_current_dossier(
        self, employee_id: str, project_key: str, correlation_id: str
    ) -> RiskEvidenceDossier:
        return RiskEvidenceDossier(
            employee_id=employee_id,
            project_key=project_key,
            observed_at=datetime(2026, 8, 18, 10, tzinfo=UTC),
            available_capacity_hours=40,
            total_remaining_hours=72,
            tasks=(),
            overdue_task_keys=("WRD-4",),
            due_soon_task_keys=("WRD-6",),
            blocked_task_keys=("WRD-6",),
            missing_evidence=(),
            evidence_references=("jira:WRD-4:duedate",),
        )


class CapturingExplainer(Explainer):
    request: ExplanationRequest | None = None

    async def explain(self, request: ExplanationRequest) -> ExplanationResponse:
        self.request = request
        if request.task_query_result is not None:
            return ExplanationResponse(
                answer="captured",
                summary="captured",
                root_causes=(),
                recommendations=(),
                citations=request.task_query_result.evidence_references,
                score=None,
                risk_level=None,
                uncertainties=(),
                source="bedrock",
                correlation_id=request.correlation_id,
            )
        return await super().explain(request)


class HistoricalTool:
    async def get_at(
        self,
        question: str,
        employee_id: str,
        project_key: str,
        correlation_id: str,
    ) -> HistoricalRiskContext:
        assert "August 18" in question
        return HistoricalRiskContext(
            risk=await Tool().investigate(
                Intent.EXPLAIN_EMPLOYEE_OVERLOAD,
                EntityReferences(employee_id=employee_id, project_key=project_key),
                correlation_id,
            ),
            dossier=await DossierTool().get_current_dossier(
                employee_id, project_key, correlation_id
            ),
        )


class TaskQueryTool:
    calls = 0

    async def query(
        self,
        question: str,
        references: EntityReferences,
        correlation_id: str,
    ) -> TaskQueryResult:
        self.calls += 1
        return TaskQueryResult(
            answer="WRD-4 is due on 2026-08-17.",
            tasks=(
                TaskFact(
                    key="WRD-4",
                    summary="Build manager result view",
                    status="Idea",
                    due_date=date(2026, 8, 17),
                ),
            ),
            evidence_references=("jira:WRD-4:duedate",),
            correlation_id=correlation_id,
        )


def context() -> VerifiedAgentContext:
    return VerifiedAgentContext(
        subject_reference="manager-1",
        roles=(ApplicationRole.MANAGER,),
        environment="test",
        authorized_jira_sites=("site-1",),
        authorized_project_keys=("WRD",),
        correlation_id="corr-graph",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Why is this employee overloaded?", Intent.EXPLAIN_EMPLOYEE_OVERLOAD),
        ("Why is this project at risk?", Intent.EXPLAIN_PROJECT_RISK),
        ("Is this task a good skill fit?", Intent.EVALUATE_TASK_FIT),
        (
            "How did this risk develop and how can we prevent it?",
            Intent.EXPLAIN_HISTORY,
        ),
        ("Which employees could take this task?", Intent.REASSIGNMENT_CANDIDATES),
        ("What if we move this task?", Intent.WHAT_IF_SIMULATION),
        ("Why is the service unhealthy?", Intent.OPERATIONS_DIAGNOSIS),
        ("What is the due date of WRD-4?", Intent.JIRA_TASK_QUERY),
        (
            "How many unfinished tasks does Employee 3 have due by tomorrow?",
            Intent.JIRA_TASK_QUERY,
        ),
    ],
)
def test_supported_intents_are_finite(question: str, expected: Intent) -> None:
    assert classify_intent(question) is expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "question",
    [
        "What is causing this employee's risk?",
        "Which factors contribute most to the score?",
        "Does this employee have overdue or blocked work?",
        "How urgent is this risk?",
        "What should the manager do first?",
        "Should some tasks be reassigned?",
        "How could we prevent this overload?",
        "What evidence supports this conclusion?",
        "Explain this result in simple words.",
        "What information might be missing?",
        "Has the employee's situation improved?",
    ],
)
def test_employee_context_accepts_natural_risk_questions(question: str) -> None:
    assert classify_intent(question, default_scope="employee") is not Intent.UNSUPPORTED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_workflow_returns_typed_cited_result() -> None:
    tool = Tool()
    workflow = InvestigationWorkflow(tool=tool, explainer=Explainer())
    result = await workflow.run(
        verified_context=context(),
        question="Why is this employee overloaded?",
        references=EntityReferences(employee_id="EMP-002", project_key="WRD"),
    )
    assert result.intent is Intent.EXPLAIN_EMPLOYEE_OVERLOAD
    assert result.risk is not None
    assert result.explanation is not None
    assert result.risk.score == 77
    assert result.explanation.citations == ("jira:WRD-1:status",)
    assert result.steps_used <= 4
    assert result.tool_calls_used == tool.calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_employee_risk_explanation_receives_current_jira_dossier() -> None:
    explainer = CapturingExplainer()
    workflow = InvestigationWorkflow(
        tool=Tool(), dossier_tool=DossierTool(), explainer=explainer
    )

    await workflow.run(
        verified_context=context(),
        question="How urgent is this risk?",
        references=EntityReferences(employee_id="EMP-003", project_key="WRD"),
    )

    assert explainer.request is not None
    assert explainer.request.evidence_dossier is not None
    assert explainer.request.evidence_dossier.total_remaining_hours == 72
    assert explainer.request.correlation_id == "corr-graph"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_historical_question_uses_immutable_snapshot_context() -> None:
    explainer = CapturingExplainer()
    workflow = InvestigationWorkflow(
        tool=Tool(), historical_tool=HistoricalTool(), explainer=explainer
    )

    result = await workflow.run(
        verified_context=context(),
        question="Why did Employee 3 have high risk on August 18?",
        references=EntityReferences(employee_id="EMP-003", project_key="WRD"),
    )

    assert result.intent is Intent.EXPLAIN_HISTORY
    assert explainer.request is not None
    assert explainer.request.evidence_dossier is not None
    assert explainer.request.evidence_dossier.observed_at.isoformat().startswith(
        "2026-08-18"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_task_due_date_uses_jira_query_not_risk_scoring() -> None:
    risk_tool = Tool()
    query_tool = TaskQueryTool()
    explainer = CapturingExplainer()
    workflow = InvestigationWorkflow(
        tool=risk_tool,
        task_query_tool=query_tool,
        explainer=explainer,
    )
    result = await workflow.run(
        verified_context=context(),
        question="What is the due date of WRD-4?",
        references=EntityReferences(employee_id="EMP-003", project_key="WRD"),
    )
    assert result.intent is Intent.JIRA_TASK_QUERY
    assert result.risk is None
    assert result.explanation is not None
    assert result.explanation.answer == "captured"
    assert result.explanation.source == "bedrock"
    assert result.explanation.citations == ("jira:WRD-4:duedate",)
    assert explainer.request is not None
    assert explainer.request.task_query_result is not None
    assert explainer.request.task_query_result.tasks[0].key == "WRD-4"
    assert risk_tool.calls == 0
    assert query_tool.calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unsupported_or_conversational_approval_never_calls_tool() -> None:
    for question in ("Write a poem", "I approve proposal P-12, execute it now"):
        tool = Tool()
        result = await InvestigationWorkflow(tool=tool, explainer=Explainer()).run(
            verified_context=context(),
            question=question,
            references=EntityReferences(project_key="WRD"),
        )
        assert result.intent is Intent.UNSUPPORTED
        assert result.capability_guidance
        assert tool.calls == 0
