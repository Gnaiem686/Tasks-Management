from __future__ import annotations

import asyncio
from typing import Protocol, cast

from langgraph.graph import END, START, StateGraph
from workforce_risk.models import RiskResult

from agent_api.graph.intents import Intent
from agent_api.graph.state import (
    EntityReferences,
    GraphState,
    InvestigationResponse,
    VerifiedAgentContext,
)
from agent_api.graph.supervisor import (
    capability_response,
    classify_supported_intent,
    receive_verified_context,
    route_after_classification,
)
from agent_api.llm.protocol import ExplanationProvider
from agent_api.llm.schemas import ExplanationRequest, ExplanationResponse
from agent_api.task_queries import TaskQueryResult


class InvestigationTool(Protocol):
    async def investigate(
        self,
        intent: Intent,
        references: EntityReferences,
        correlation_id: str,
    ) -> RiskResult: ...


class TaskQueryTool(Protocol):
    async def query(
        self,
        question: str,
        references: EntityReferences,
        correlation_id: str,
    ) -> TaskQueryResult: ...


class InvestigationWorkflow:
    def __init__(
        self,
        *,
        tool: InvestigationTool,
        task_query_tool: TaskQueryTool | None = None,
        explainer: ExplanationProvider,
        max_steps: int = 6,
        max_tool_calls: int = 2,
        deadline_seconds: float = 15.0,
    ) -> None:
        self._tool = tool
        self._task_query_tool = task_query_tool
        self._explainer = explainer
        self._max_steps = max_steps
        self._max_tool_calls = max_tool_calls
        self._deadline_seconds = deadline_seconds
        builder = StateGraph(GraphState)
        builder.add_node("receive_verified_context", receive_verified_context)
        builder.add_node("classify", classify_supported_intent)
        builder.add_node("gather", self._gather)
        builder.add_node("explain", self._explain)
        builder.add_node("capability", capability_response)
        builder.add_edge(START, "receive_verified_context")
        builder.add_edge("receive_verified_context", "classify")
        builder.add_conditional_edges(
            "classify",
            route_after_classification,
            {"gather": "gather", "capability": "capability"},
        )
        builder.add_edge("gather", "explain")
        builder.add_edge("explain", END)
        builder.add_edge("capability", END)
        self._graph = builder.compile()

    async def _gather(self, state: GraphState) -> dict[str, object]:
        if state["tool_calls_used"] >= self._max_tool_calls:
            raise RuntimeError("investigation tool-call limit reached")
        if state["intent"] is Intent.JIRA_TASK_QUERY:
            if self._task_query_tool is None:
                raise ValueError("Jira task query tool is unavailable")
            result = await self._task_query_tool.query(
                state["question"],
                state["references"],
                state["verified_context"].correlation_id,
            )
            return {
                "task_query_result": TaskQueryResult.model_validate(result),
                "steps_used": state["steps_used"] + 1,
                "tool_calls_used": state["tool_calls_used"] + 1,
            }
        risk = await self._tool.investigate(
            state["intent"],
            state["references"],
            state["verified_context"].correlation_id,
        )
        return {
            "risk": RiskResult.model_validate(risk),
            "steps_used": state["steps_used"] + 1,
            "tool_calls_used": state["tool_calls_used"] + 1,
        }

    async def _explain(self, state: GraphState) -> dict[str, object]:
        if state["intent"] is Intent.JIRA_TASK_QUERY:
            result = state["task_query_result"]
            explanation = ExplanationResponse(
                answer=result.answer,
                summary=result.answer,
                root_causes=(),
                recommendations=(),
                citations=result.evidence_references,
                score=None,
                risk_level=None,
                uncertainties=(),
                source="jira_mcp",
                correlation_id=result.correlation_id,
            )
            return {
                "explanation": explanation,
                "steps_used": state["steps_used"] + 1,
            }
        explanation = await self._explainer.explain(
            ExplanationRequest(
                workflow=state["intent"].value,
                question=state["question"],
                risk=state["risk"],
                correlation_id=state["verified_context"].correlation_id,
            )
        )
        return {
            "explanation": explanation,
            "steps_used": state["steps_used"] + 1,
        }

    async def run(
        self,
        *,
        verified_context: VerifiedAgentContext,
        question: str,
        references: EntityReferences,
    ) -> InvestigationResponse:
        if len(question) > 1_000:
            raise ValueError("question exceeds size limit")
        initial: GraphState = {
            "verified_context": verified_context,
            "question": question,
            "references": references,
            "steps_used": 0,
            "tool_calls_used": 0,
        }
        raw = await asyncio.wait_for(
            self._graph.ainvoke(initial, {"recursion_limit": self._max_steps}),
            timeout=self._deadline_seconds,
        )
        final = cast(GraphState, raw)
        return InvestigationResponse(
            correlation_id=verified_context.correlation_id,
            intent=final["intent"],
            risk=final.get("risk"),
            explanation=final.get("explanation"),
            capability_guidance=final.get("capability_guidance"),
            missing_sources=final.get("missing_sources", ()),
            steps_used=final["steps_used"],
            tool_calls_used=final["tool_calls_used"],
        )
