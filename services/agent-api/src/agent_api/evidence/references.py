from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from agent_api.evidence.models import EvidenceEntity
from agent_api.task_queries import GroundedAnswerContext


class ResolvedConversationContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    entities: tuple[EvidenceEntity, ...] = ()
    needs_clarification: bool = False


_SINGULAR = re.compile(
    r"\b(?:that|this|it)\s+(?:task|issue|risk|employee)?\b|\bit\b", re.I
)
_PLURAL = re.compile(r"\b(?:those|these|them)\s*(?:tasks|issues|employees)?\b", re.I)
_PLURAL_EMPLOYEE = re.compile(r"\b(?:those|these)\s+employees\b", re.I)
_SINGULAR_EMPLOYEE = re.compile(r"\b(?:that|this)\s+employee\b", re.I)


def resolve_conversation_references(
    question: str,
    previous_context: GroundedAnswerContext | None,
) -> ResolvedConversationContext:
    if previous_context is None:
        return ResolvedConversationContext()
    issues = tuple(
        EvidenceEntity(kind="task", identifier=item.key)
        for item in previous_context.issues
    )
    employees = tuple(
        EvidenceEntity(kind="employee", identifier=employee_id)
        for employee_id in previous_context.employee_ids
    )
    if _PLURAL_EMPLOYEE.search(question):
        return ResolvedConversationContext(entities=employees)
    if _SINGULAR_EMPLOYEE.search(question):
        return ResolvedConversationContext(
            entities=employees,
            needs_clarification=len(employees) != 1,
        )
    if _PLURAL.search(question):
        entities = issues or employees
        return ResolvedConversationContext(entities=entities)
    if _SINGULAR.search(question):
        return ResolvedConversationContext(
            entities=issues,
            needs_clarification=len(issues) != 1,
        )
    return ResolvedConversationContext()
