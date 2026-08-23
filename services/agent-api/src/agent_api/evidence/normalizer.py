from __future__ import annotations

import re

from agent_api.evidence.models import (
    EvidenceCategory,
    EvidenceEntity,
    EvidencePlan,
    EvidenceScope,
)
from agent_api.task_queries import GroundedAnswerContext


def normalize_evidence_plan(
    *,
    question: str,
    planned: EvidencePlan,
    previous_context: GroundedAnswerContext | None,
) -> EvidencePlan:
    """Make a model-selected read plan compatible with the manager's question."""

    folded = question.casefold()
    task_language = any(
        phrase in folded
        for phrase in (
            "task",
            "work item",
            "issue",
            "deadline",
            "due",
            "blocked",
            "blocker",
            "dependency",
            "estimate",
        )
    )
    employee_language = any(
        phrase in folded
        for phrase in (
            "employee",
            "people",
            "person",
            "capacity",
            "workload",
            "skill",
            "assignee",
            "who has",
            "who is at risk",
        )
    )
    refers_to_prior_tasks = (
        previous_context is not None
        and bool(previous_context.issues)
        and any(
            phrase in folded
            for phrase in ("that task", "those tasks", "these tasks", "them")
        )
    )

    scope = planned.scope
    if refers_to_prior_tasks or (task_language and not employee_language):
        scope = EvidenceScope.TASK
    elif employee_language and not task_language:
        scope = EvidenceScope.EMPLOYEE
    elif employee_language and task_language:
        scope = EvidenceScope.MIXED

    categories = list(planned.evidence_categories)

    def require(category: EvidenceCategory) -> None:
        if category not in categories:
            categories.append(category)

    if task_language or refers_to_prior_tasks:
        require(EvidenceCategory.JIRA_ISSUES)
    if any(word in folded for word in ("blocked", "blocker", "dependency")):
        require(EvidenceCategory.DEPENDENCIES_AND_BLOCKERS)
    if any(word in folded for word in ("deadline", "due", "overdue")):
        require(EvidenceCategory.DEADLINES)
    if employee_language:
        require(EvidenceCategory.WORKFORCE_PROFILES)
    if any(word in folded for word in ("capacity", "workload", "available", "risk")):
        require(EvidenceCategory.CAPACITY_AND_WORKLOAD)
    if any(word in folded for word in ("skill", "fit", "qualified")):
        require(EvidenceCategory.SKILLS_AND_SENIORITY)
    if any(
        phrase in folded
        for phrase in (
            "history",
            "historical",
            "improved",
            "changed",
            "progressed",
            "progress over",
            "since yesterday",
            "this week",
            "last week",
            "previously",
            "before",
            "trend",
        )
    ):
        require(EvidenceCategory.HISTORY)

    exhaustive = planned.exhaustive or any(
        phrase in folded
        for phrase in ("which ", "list ", "all ", "name those", "name the ")
    )
    project_wide_employee_question = (
        exhaustive
        and employee_language
        and not task_language
        and any(
            phrase in folded
            for phrase in (
                "which employees",
                "all employees",
                "employees are",
                "which people",
                "who is at risk",
            )
        )
    )
    entities = [] if project_wide_employee_question else list(planned.entities)
    existing: set[tuple[str, str]] = {(item.kind, item.identifier) for item in entities}
    for issue_key in re.findall(r"\b[A-Z][A-Z0-9]{1,19}-\d+\b", question.upper()):
        key = ("task", issue_key)
        if key not in existing:
            entities.append(EvidenceEntity(kind="task", identifier=issue_key))
            existing.add(key)
    if refers_to_prior_tasks and previous_context is not None:
        for issue in previous_context.issues:
            key = ("task", issue.key)
            if key not in existing:
                entities.append(EvidenceEntity(kind="task", identifier=issue.key))
                existing.add(key)
    if any(entity.kind == "task" for entity in entities):
        scope = EvidenceScope.TASK

    return planned.model_copy(
        update={
            "scope": scope,
            "entities": tuple(entities),
            "evidence_categories": tuple(categories),
            "exhaustive": exhaustive,
        }
    )
