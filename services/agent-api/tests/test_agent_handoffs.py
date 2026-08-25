from __future__ import annotations

from datetime import UTC, datetime

import pytest
from agent_api.auth.roles import ApplicationRole
from agent_api.graph.agents.operations_diagnostic import OperationsDiagnosticAgent
from agent_api.graph.agents.project_delivery import ProjectDeliveryAgent
from agent_api.graph.agents.reassignment_planning import ReassignmentPlanningAgent
from agent_api.graph.agents.workforce_analysis import WorkforceAnalysisAgent
from agent_api.graph.handoffs import AgentHandoff, SpecialistRouter
from agent_api.graph.intents import Intent
from agent_api.graph.state import EntityReferences, VerifiedAgentContext
from workforce_risk.models import RiskResult


class DomainTool:
    async def investigate(
        self, intent: Intent, references: EntityReferences, correlation_id: str
    ) -> RiskResult:
        return RiskResult.model_validate(
            {
                "subject_id": references.employee_id or "WRD",
                "environment": "test",
                "score": 55,
                "level": "high",
                "confidence": "medium",
                "scored_at": datetime.now(UTC),
                "evidence_timestamp": datetime.now(UTC),
                "scoring_model_version": "v1",
                "factors": [],
                "thresholds": {},
                "evidence_references": ["jira:WRD-1"],
                "missing_evidence": [],
                "excluded_evidence": [],
            }
        )


def context() -> VerifiedAgentContext:
    return VerifiedAgentContext(
        subject_reference="manager-1",
        roles=(ApplicationRole.MANAGER,),
        environment="test",
        authorized_jira_sites=("site-1",),
        authorized_project_keys=("WRD",),
        correlation_id="corr-handoff",
    )


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("intent", "specialist"),
    [
        (Intent.EXPLAIN_EMPLOYEE_OVERLOAD, "workforce_analysis"),
        (Intent.EVALUATE_TASK_FIT, "workforce_analysis"),
        (Intent.EXPLAIN_PROJECT_RISK, "project_delivery"),
        (Intent.EXPLAIN_HISTORY, "project_delivery"),
        (Intent.REASSIGNMENT_CANDIDATES, "reassignment_planning"),
        (Intent.WHAT_IF_SIMULATION, "reassignment_planning"),
        (Intent.OPERATIONS_DIAGNOSIS, "operations_diagnostic"),
    ],
)
async def test_router_uses_typed_specialist_handoff(
    intent: Intent, specialist: str
) -> None:
    router = SpecialistRouter(
        core_tool=DomainTool(),
        specialists=(
            WorkforceAnalysisAgent(),
            ProjectDeliveryAgent(),
            ReassignmentPlanningAgent(),
            OperationsDiagnosticAgent(),
        ),
        context=context(),
    )
    result = await router.investigate(
        intent,
        EntityReferences(employee_id="EMP-002", project_key="WRD"),
        "corr-handoff",
    )
    assert result.score == 55
    assert router.trace[-1].specialist == specialist
    assert router.trace[-1].status == "completed"


@pytest.mark.unit
def test_handoff_contains_references_not_credentials_or_raw_comments() -> None:
    handoff = AgentHandoff(
        specialist="workforce_analysis",
        intent=Intent.EXPLAIN_EMPLOYEE_OVERLOAD,
        context=context(),
        references=EntityReferences(project_key="WRD"),
        evidence_references=("jira:WRD-1:comment:42",),
        evidence_timestamp=datetime.now(UTC),
        correlation_id="corr-handoff",
    )
    serialized = handoff.model_dump_json()
    assert "api_key" not in serialized
    assert "authorization" not in serialized
    assert "comment_body" not in serialized
