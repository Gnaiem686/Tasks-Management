from __future__ import annotations

import re
from collections.abc import Iterable

from agent_api.dashboard.models import EmployeeSummary
from agent_api.evidence.models import (
    AnswerEmployeeEvidence,
    AnswerEvidenceSet,
    UniversalEvidenceBundle,
)
from agent_api.task_queries import TaskFact


class GroundingValidationError(ValueError):
    """A generated Jira claim does not match its structured evidence."""


def validate_focused_claims(
    answer: str,
    evidence: AnswerEvidenceSet,
    *,
    allowed_issue_keys: Iterable[str] = (),
) -> None:
    tasks = {task.key.upper(): task for task in evidence.tasks}
    validated_project_keys = {key.upper() for key in allowed_issue_keys}
    employee_ids = {employee.employee_id.upper() for employee in evidence.employees}
    dependency_keys = {
        key
        for task in evidence.tasks
        for dependency in task.dependencies
        for key in re.findall(r"\b[A-Z][A-Z0-9]{1,19}-\d+\b", dependency.upper())
    }
    mentioned = set(re.findall(r"\b[A-Z][A-Z0-9]{1,19}-\d+\b", answer.upper()))
    unknown = (
        mentioned
        - tasks.keys()
        - dependency_keys
        - validated_project_keys
        - employee_ids
    )
    if unknown:
        raise GroundingValidationError(
            "answer mentioned unknown Jira issue(s): " + ", ".join(sorted(unknown))
        )
    for key in dependency_keys - tasks.keys() - validated_project_keys:
        if re.search(
            rf"^\s*(?:\d+[.)]\s*)?[*_]*{re.escape(key)}[*_]*\s*(?::|—|-)",
            answer,
            re.I | re.M,
        ):
            raise GroundingValidationError(
                f"answer promoted dependency-only Jira issue {key} to focused task"
            )

    for blocked, blocker in re.findall(
        r"\b([A-Z][A-Z0-9]{1,19}-\d+)\b\s+(?:is\s+)?blocked by\s+"
        r"\b([A-Z][A-Z0-9]{1,19}-\d+)\b",
        answer,
        re.I,
    ):
        task = tasks.get(blocked.upper())
        if task is None and blocked.upper() in validated_project_keys:
            continue
        if task is None or blocker.upper() not in " ".join(task.dependencies).upper():
            raise GroundingValidationError("answer invented a Jira dependency")

    mentioned_ids = set(re.findall(r"\bEMP-\d+\b", answer.upper()))
    unknown_employees = mentioned_ids - employee_ids
    if unknown_employees:
        raise GroundingValidationError(
            "answer mentioned unknown employee(s): "
            + ", ".join(sorted(unknown_employees))
        )
    remaining_answer = answer
    for employee in sorted(
        evidence.employees,
        key=lambda item: len(item.display_name),
        reverse=True,
    ):
        name_pattern = re.compile(
            rf"(?<!\w){re.escape(employee.display_name)}(?!\w)", re.I
        )
        matches = tuple(name_pattern.finditer(remaining_answer))
        if not matches:
            continue
        expected = "high" if employee.risk_level == "critical" else employee.risk_level
        for match in matches:
            sentence = re.split(
                r"[.!?\n]",
                remaining_answer[match.start() : match.end() + 80],
                maxsplit=1,
            )[0]
            claimed = re.search(
                r"\b(low|medium|high|critical|insufficient-data)\s+risk\b",
                sentence,
                re.I,
            )
            if claimed is not None and claimed.group(1).casefold() != expected:
                raise GroundingValidationError(
                    "answer changed employee risk classification"
                )
        characters = list(remaining_answer)
        for match in matches:
            characters[match.start() : match.end()] = " " * (
                match.end() - match.start()
            )
        remaining_answer = "".join(characters)


def validate_focused_completeness(answer: str, evidence: AnswerEvidenceSet) -> None:
    if not evidence.exhaustive:
        return
    folded = evidence.question_focus.casefold()
    employee_question = any(
        phrase in folded
        for phrase in ("employee", "people", "capacity", "workload", "skill", "who has")
    ) and not any(
        phrase in folded
        for phrase in ("which task", "tasks ", "work is blocked", "deadline")
    )
    if evidence.employees and (employee_question or not evidence.tasks):
        subset_only = any(
            phrase in folded
            for phrase in (
                "cannot be classified",
                "can't be classified",
                "classified reliably",
                "unclassified",
                "insufficient data",
                "insufficient-data",
            )
        )
        required_employees = (
            tuple(
                employee
                for employee in evidence.employees
                if employee.risk_level == "insufficient-data"
            )
            if subset_only
            else evidence.employees
        )
        mentioned = _mentioned_employee_ids(answer, evidence.employees)
        missing = {
            employee.display_name
            for employee in required_employees
            if employee.employee_id not in mentioned
        }
        if missing:
            raise GroundingValidationError(
                "answer omitted employee(s): " + ", ".join(sorted(missing))
            )
        return
    if evidence.tasks:
        required_tasks = (
            {key.upper() for key in evidence.required_task_keys}
            if evidence.required_task_keys
            else {task.key.upper() for task in evidence.tasks}
        )
        mentioned = set(re.findall(r"\b[A-Z][A-Z0-9]{1,19}-\d+\b", answer.upper()))
        missing = required_tasks - mentioned
        if missing:
            raise GroundingValidationError(
                "answer omitted matching Jira issue(s): " + ", ".join(sorted(missing))
            )


def validate_insufficiency_claim(answer: str, evidence: AnswerEvidenceSet) -> None:
    folded = answer.casefold()
    generic = any(
        phrase in folded
        for phrase in (
            "not enough information",
            "do not have enough information",
            "not enough reliable information",
            "insufficient information",
            "not possible to confidently",
            "cannot confidently",
            "provide more details",
            "clarify the entity",
            "clarify the question",
        )
    )
    if not generic or not (evidence.tasks or evidence.employees):
        return
    concrete_missing = any(
        item.entity.split(":", 1)[-1].casefold() in folded
        and any(
            term in folded
            for term in (
                "estimate",
                "capacity",
                "skills",
                "due date",
                "priority",
                "assignee",
            )
        )
        for item in evidence.missing_data
    )
    if not concrete_missing:
        raise GroundingValidationError(
            "answer claimed insufficiency despite usable focused evidence"
        )


def validate_universal_claims(
    answer: str,
    bundle: UniversalEvidenceBundle,
) -> None:
    snapshot = bundle.project_snapshot
    if snapshot is None:
        return
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer):
        mentioned = _mentioned_employee_ids(sentence, snapshot.employees)
        if len(mentioned) != 1:
            continue
        employee = next(
            item for item in snapshot.employees if item.employee_id in mentioned
        )
        capacity = next(
            (
                item
                for item in bundle.capacity_and_workload
                if item.employee_id == employee.employee_id
            ),
            None,
        )
        available_claim = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:h|hours?)\s+(?:of\s+)?available",
            sentence,
            re.I,
        )
        if (
            available_claim
            and capacity is not None
            and float(available_claim.group(1)) != capacity.available_capacity_hours
        ):
            raise GroundingValidationError("answer misstated available capacity")
        claimed = re.search(
            r"\b(low|medium|high|critical|insufficient-data)\s+risk\b",
            sentence,
            re.I,
        )
        expected = "high" if employee.level == "critical" else employee.level
        if claimed is not None and claimed.group(1).casefold() != expected:
            raise GroundingValidationError(
                "answer changed employee risk classification"
            )
        overage_claim = re.search(
            r"capacity\s+by\s+(\d+(?:\.\d+)?)\s*(?:h|hours?)\b",
            sentence,
            re.I,
        )
        if (
            overage_claim
            and employee.remaining_hours is not None
            and employee.capacity_hours is not None
        ):
            expected_overage = max(
                employee.remaining_hours - employee.capacity_hours, 0.0
            )
            if float(overage_claim.group(1)) != expected_overage:
                raise GroundingValidationError("answer misstated capacity overage")
    facts = {task.key.upper(): task for task in snapshot.tasks}
    for blocked, blocker in re.findall(
        r"\b([A-Z][A-Z0-9]{1,19}-\d+)\b\s+(?:is\s+)?blocked by\s+"
        r"\b([A-Z][A-Z0-9]{1,19}-\d+)\b",
        answer,
        re.I,
    ):
        task = facts.get(blocked.upper())
        if task is None or blocker.upper() not in " ".join(task.dependencies).upper():
            raise GroundingValidationError("answer invented a Jira dependency")


def validate_universal_completeness(
    answer: str,
    bundle: UniversalEvidenceBundle,
) -> None:
    if bundle.answer_evidence is not None:
        validate_focused_completeness(answer, bundle.answer_evidence)
        return
    if not bundle.plan.exhaustive or bundle.project_snapshot is None:
        return
    from agent_api.evidence.models import EvidenceCategory, EvidenceScope

    categories = set(bundle.plan.evidence_categories)
    employee_categories = {
        EvidenceCategory.WORKFORCE_PROFILES,
        EvidenceCategory.CAPACITY_AND_WORKLOAD,
        EvidenceCategory.SKILLS_AND_SENIORITY,
        EvidenceCategory.RISK_RESULTS,
    }
    # An exhaustive workforce answer must cover the employees, not enumerate
    # every Jira task that contributed to each aggregate risk. Explicit task-list
    # plans retain the issue-by-issue completeness check below.
    if bundle.plan.scope is not EvidenceScope.TASK and categories & employee_categories:
        mentioned = _mentioned_employee_ids(answer, bundle.project_snapshot.employees)
        missing = {
            employee.display_name
            for employee in bundle.project_snapshot.employees
            if employee.employee_id not in mentioned
        }
        if missing:
            raise GroundingValidationError(
                "answer omitted employee(s): " + ", ".join(sorted(missing))
            )
        return
    expected: set[str] = set()

    if EvidenceCategory.DEPENDENCIES_AND_BLOCKERS in categories:
        expected.update(
            task.key.upper()
            for task in bundle.project_snapshot.tasks
            if task.blocker or task.dependencies
        )
    if not expected:
        return
    mentioned = set(re.findall(r"\b[A-Z][A-Z0-9]{1,19}-\d+\b", answer.upper()))
    missing = expected - mentioned
    if missing:
        raise GroundingValidationError(
            "answer omitted matching Jira issue(s): " + ", ".join(sorted(missing))
        )


def _mentioned_employee_ids(
    answer: str, employees: Iterable[EmployeeSummary | AnswerEmployeeEvidence]
) -> set[str]:
    remaining = answer.casefold()
    mentioned: set[str] = set()
    ordered = sorted(
        employees,
        key=lambda employee: len(employee.display_name),
        reverse=True,
    )
    for employee in ordered:
        name = employee.display_name
        pattern = rf"(?<!\w){re.escape(name.casefold())}(?!\w)"
        matches = tuple(re.finditer(pattern, remaining))
        if not matches:
            continue
        mentioned.add(employee.employee_id)
        chars = list(remaining)
        for match in matches:
            chars[match.start() : match.end()] = " " * (match.end() - match.start())
        remaining = "".join(chars)
    return mentioned


def validate_jira_claims(
    answer: str,
    evidence: Iterable[TaskFact],
    *,
    referenced_issue_keys: Iterable[str] = (),
    referenced_employee_ids: Iterable[str] = (),
) -> None:
    facts = {fact.key.upper(): fact for fact in evidence}
    mentioned = set(re.findall(r"\b[A-Z][A-Z0-9]{1,19}-\d+\b", answer.upper()))
    allowed = (
        facts.keys()
        | {key.upper() for key in referenced_issue_keys}
        | {employee_id.upper() for employee_id in referenced_employee_ids}
    )
    unknown = mentioned - allowed
    if unknown:
        raise GroundingValidationError(
            "answer mentioned unknown Jira issue(s): " + ", ".join(sorted(unknown))
        )

    for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer):
        sentence_keys = set(
            re.findall(r"\b[A-Z][A-Z0-9]{1,19}-\d+\b", sentence.upper())
        )
        for key in sentence_keys:
            if key not in facts:
                continue
            fact = facts[key]
            folded = sentence.casefold()
            for other in facts.values():
                if (
                    other.summary.casefold() in folded
                    and other.key != fact.key
                    and other.key.upper() not in sentence_keys
                ):
                    raise GroundingValidationError(
                        "answer mismatched Jira issue key and summary"
                    )
            assigned_after = re.search(
                rf"\b{re.escape(key)}\b\s+is assigned to\s+([^,.]+)",
                sentence,
                flags=re.IGNORECASE,
            )
            if assigned_after and (
                fact.assignee is None
                or assigned_after.group(1).strip().casefold()
                != fact.assignee.casefold()
            ):
                raise GroundingValidationError(
                    "answer mismatched Jira issue key and assignee"
                )
            status = re.search(
                r"(?:currently|status is)\s+([A-Za-z][A-Za-z ]+?)(?:[,.]|$)",
                sentence,
                flags=re.IGNORECASE,
            )
            if (
                len(sentence_keys) == 1
                and status
                and status.group(1).strip().casefold() != fact.status.casefold()
            ):
                raise GroundingValidationError(
                    "answer mismatched Jira issue key and status"
                )
