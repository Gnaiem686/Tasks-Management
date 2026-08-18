from __future__ import annotations

import re
from enum import StrEnum


class Intent(StrEnum):
    EXPLAIN_PROJECT_RISK = "explain_project_risk"
    EXPLAIN_EMPLOYEE_OVERLOAD = "explain_employee_overload"
    EVALUATE_TASK_FIT = "evaluate_task_fit"
    EXPLAIN_HISTORY = "explain_history"
    REASSIGNMENT_CANDIDATES = "reassignment_candidates"
    WHAT_IF_SIMULATION = "what_if_simulation"
    OPERATIONS_DIAGNOSIS = "operations_diagnosis"
    JIRA_TASK_QUERY = "jira_task_query"
    UNSUPPORTED = "unsupported"


READ_ONLY_TOOL_ALLOWLISTS: dict[Intent, frozenset[str]] = {
    Intent.EXPLAIN_PROJECT_RISK: frozenset({"get_project_risk"}),
    Intent.EXPLAIN_EMPLOYEE_OVERLOAD: frozenset({"get_employee_overload_risk"}),
    Intent.EVALUATE_TASK_FIT: frozenset({"get_task_fit_risk"}),
    Intent.EXPLAIN_HISTORY: frozenset({"get_risk_history"}),
    Intent.REASSIGNMENT_CANDIDATES: frozenset({"get_reassignment_candidates"}),
    Intent.WHAT_IF_SIMULATION: frozenset({"simulate_reassignment"}),
    Intent.OPERATIONS_DIAGNOSIS: frozenset({"diagnose_operations_read_only"}),
    Intent.JIRA_TASK_QUERY: frozenset({"getJiraIssue", "searchJiraIssuesUsingJql"}),
}


def classify_intent(question: str, *, default_scope: str | None = None) -> Intent:
    text = " ".join(question.lower().split())
    if any(word in text for word in ("approve", "execute", "change assignee")):
        return Intent.UNSUPPORTED
    has_issue_due_date = "due date" in text and re.search(
        r"\b[A-Z][A-Z0-9]{1,19}-\d+\b", question.upper()
    )
    if has_issue_due_date or (
        "task" in text
        and ("due" in text or "tomorrow" in text)
        and any(term in text for term in ("how many", "list", "what", "which"))
    ):
        return Intent.JIRA_TASK_QUERY
    if "what if" in text or "simulate" in text:
        return Intent.WHAT_IF_SIMULATION
    if any(word in text for word in ("candidate", "which employee", "could take")):
        return Intent.REASSIGNMENT_CANDIDATES
    if "task" in text and any(word in text for word in ("fit", "skill", "appropriate")):
        return Intent.EVALUATE_TASK_FIT
    if any(word in text for word in ("service", "pod", "deployment")) and any(
        word in text for word in ("unhealthy", "latency", "failed", "failure")
    ):
        return Intent.OPERATIONS_DIAGNOSIS
    if (
        any(word in text for word in ("develop", "prevent", "recurrence", "history"))
        and default_scope is None
    ):
        return Intent.EXPLAIN_HISTORY
    if "project" in text and any(word in text for word in ("risk", "late", "delay")):
        return Intent.EXPLAIN_PROJECT_RISK
    if "employee" in text and any(
        word in text for word in ("overload", "progress", "finish", "workload")
    ):
        return Intent.EXPLAIN_EMPLOYEE_OVERLOAD
    work_terms = (
        "employee",
        "risk",
        "score",
        "factor",
        "overdue",
        "blocked",
        "work",
        "task",
        "manager",
        "evidence",
        "result",
        "missing",
        "situation",
        "improved",
        "improvement",
        "urgent",
        "overload",
        "prevent",
    )
    if default_scope == "employee" and any(term in text for term in work_terms):
        return Intent.EXPLAIN_EMPLOYEE_OVERLOAD
    if default_scope in {"project", "workflow"} and any(
        term in text for term in work_terms
    ):
        return Intent.EXPLAIN_PROJECT_RISK
    return Intent.UNSUPPORTED
