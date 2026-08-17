from __future__ import annotations

from datetime import UTC, datetime

import pytest
from agent_api.auth.roles import ApplicationRole
from agent_api.graph.intents import Intent, classify_intent
from agent_api.graph.state import EntityReferences, VerifiedAgentContext
from agent_api.graph.workflow import InvestigationWorkflow
from agent_api.llm.schemas import ExplanationResponse, Recommendation
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
    async def explain(self, request: object) -> ExplanationResponse:
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
