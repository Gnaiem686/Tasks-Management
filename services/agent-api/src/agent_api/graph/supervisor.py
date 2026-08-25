from __future__ import annotations

import logging

from agent_api.failure_diagnostics import log_assistant_event
from agent_api.graph.intents import Intent, classify_intent
from agent_api.graph.state import GraphState

logger = logging.getLogger(__name__)


async def receive_verified_context(state: GraphState) -> dict[str, object]:
    log_assistant_event(
        logger,
        "langgraph_node_entered",
        state["verified_context"].correlation_id,
        node="receive_verified_context",
    )
    context = state["verified_context"]
    references = state["references"]
    if references.project_key not in context.authorized_project_keys:
        raise PermissionError("project is outside verified authorization context")
    return {"steps_used": state["steps_used"] + 1}


async def classify_supported_intent(state: GraphState) -> dict[str, object]:
    references = state["references"]
    if references.employee_id is not None:
        default_scope = "employee"
    elif references.task_id is not None:
        default_scope = "task"
    else:
        default_scope = "project"
    intent = classify_intent(state["question"], default_scope=default_scope)
    log_assistant_event(
        logger,
        "intent_detected",
        state["verified_context"].correlation_id,
        intent=intent.value,
        node="classify",
    )
    return {
        "intent": intent,
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
