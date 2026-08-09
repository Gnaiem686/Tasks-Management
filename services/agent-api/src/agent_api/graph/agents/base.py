from __future__ import annotations

from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from workforce_risk.models import RiskResult

from agent_api.graph.handoffs import (
    AgentHandoff,
    DomainTool,
    SpecialistUnavailable,
)
from agent_api.graph.intents import Intent


class SpecialistState(TypedDict):
    handoff: AgentHandoff
    tool: DomainTool
    result: NotRequired[RiskResult]


class BoundedSpecialistAgent:
    name: str
    intents: frozenset[Intent]
    allowed_tools: frozenset[str]

    def __init__(self, *, available: bool = True) -> None:
        self._available = available
        builder = StateGraph(SpecialistState)
        builder.add_node("validate_handoff", self._validate_handoff)
        builder.add_node("call_domain_tool", self._call_domain_tool)
        builder.add_edge(START, "validate_handoff")
        builder.add_edge("validate_handoff", "call_domain_tool")
        builder.add_edge("call_domain_tool", END)
        self._graph = builder.compile()

    def supports(self, intent: Intent) -> bool:
        return intent in self.intents

    async def _validate_handoff(self, state: SpecialistState) -> dict[str, object]:
        handoff = state["handoff"]
        if not self._available:
            raise SpecialistUnavailable(f"{self.name} is unavailable")
        if handoff.specialist != self.name or handoff.intent not in self.intents:
            raise ValueError("specialist handoff mismatch")
        if (
            handoff.references.project_key
            not in handoff.context.authorized_project_keys
        ):
            raise PermissionError("specialist project scope mismatch")
        return {}

    async def _call_domain_tool(self, state: SpecialistState) -> dict[str, object]:
        handoff = state["handoff"]
        result = await state["tool"].investigate(
            handoff.intent, handoff.references, handoff.correlation_id
        )
        return {"result": RiskResult.model_validate(result)}

    async def run(self, handoff: AgentHandoff, tool: DomainTool) -> RiskResult:
        initial: SpecialistState = {"handoff": handoff, "tool": tool}
        result = await self._graph.ainvoke(initial, {"recursion_limit": 4})
        return RiskResult.model_validate(result["result"])
