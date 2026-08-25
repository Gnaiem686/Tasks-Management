from __future__ import annotations

import pytest
from agent_api.graph.agents.reassignment_planning import ReassignmentPlanningAgent
from agent_api.graph.agents.workforce_analysis import WorkforceAnalysisAgent
from agent_api.graph.handoffs import SpecialistRouter, SpecialistUnavailable
from agent_api.graph.intents import Intent
from agent_api.graph.state import EntityReferences
from test_agent_handoffs import DomainTool, context


@pytest.mark.unit
@pytest.mark.asyncio
async def test_read_specialist_unavailable_uses_core_supervisor_fallback() -> None:
    router = SpecialistRouter(
        core_tool=DomainTool(),
        specialists=(WorkforceAnalysisAgent(available=False),),
        context=context(),
    )
    result = await router.investigate(
        Intent.EXPLAIN_EMPLOYEE_OVERLOAD,
        EntityReferences(employee_id="EMP-002", project_key="WRD"),
        "corr-fallback",
    )
    assert result.score == 55
    assert router.trace[-1].status == "fallback"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_write_oriented_preparation_closes_when_specialist_unavailable() -> None:
    router = SpecialistRouter(
        core_tool=DomainTool(),
        specialists=(ReassignmentPlanningAgent(available=False),),
        context=context(),
    )
    with pytest.raises(SpecialistUnavailable):
        await router.investigate(
            Intent.WHAT_IF_SIMULATION,
            EntityReferences(task_id="WRD-1", project_key="WRD"),
            "corr-closed",
        )
