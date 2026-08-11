from __future__ import annotations

from agent_api.graph.intents import Intent, classify_intent
from agent_api.graph.state import GraphState


async def receive_verified_context(state: GraphState) -> dict[str, object]:
    context = state["verified_context"]
    references = state["references"]
    if references.project_key not in context.authorized_project_keys:
        raise PermissionError("project is outside verified authorization context")
    return {"steps_used": state["steps_used"] + 1}


async def classify_supported_intent(state: GraphState) -> dict[str, object]:
    return {
        "intent": classify_intent(state["question"]),
        "steps_used": state["steps_used"] + 1,
    }


async def route_after_classification(state: GraphState) -> str:
    return "capability" if state["intent"] is Intent.UNSUPPORTED else "gather"


async def capability_response(state: GraphState) -> dict[str, object]:
    return {
        "capability_guidance": (
            "I can explain employee, task-fit, and project risk; describe risk "
            "history; identify deterministic candidates; run a what-if simulation; "
            "or provide read-only operational diagnosis. Approval must use the "
            "dedicated structured approval control."
        ),
        "steps_used": state["steps_used"] + 1,
    }
