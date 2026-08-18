from datetime import date

import pytest
from agent_api.graph.intents import Intent, classify_intent
from agent_api.graph.state import EntityReferences
from agent_api.task_queries import JiraTaskQueryTool, TaskQueryKind, parse_task_query
from workforce_contracts.jira import JiraIssueEvidence


def issue(key: str, due_date: date | None) -> JiraIssueEvidence:
    return JiraIssueEvidence.model_validate(
        {
            "environment": "test",
            "correlation_id": "corr-task",
            "evidence_timestamp": "2026-08-18T10:00:00Z",
            "key": key,
            "summary": "Build manager result view",
            "status": "Idea",
            "priority": "Medium",
            "assignee": None,
            "due_date": due_date,
            "original_estimate_seconds": None,
            "remaining_estimate_seconds": None,
            "workforce_employee_id": "EMP-003",
            "activity_timestamp": "2026-08-18T09:00:00Z",
            "evidence_references": [
                {
                    "issue_key": key,
                    "field_id": "duedate",
                    "observed_at": "2026-08-18T10:00:00Z",
                }
            ],
        }
    )


@pytest.mark.unit
def test_exact_issue_due_date_question_is_a_task_query() -> None:
    question = "What is the due date of WRD-4?"
    assert classify_intent(question, default_scope="employee") is Intent.JIRA_TASK_QUERY
    query = parse_task_query(
        question,
        EntityReferences(employee_id="EMP-003", project_key="WRD"),
        today=date(2026, 8, 18),
    )
    assert query.kind is TaskQueryKind.ISSUE_DUE_DATE
    assert query.issue_key == "WRD-4"


@pytest.mark.unit
def test_employee_due_by_tomorrow_question_builds_bounded_query() -> None:
    question = "How many unfinished tasks does Employee 3 have due by tomorrow?"
    assert classify_intent(question, default_scope="employee") is Intent.JIRA_TASK_QUERY
    query = parse_task_query(
        question,
        EntityReferences(employee_id="EMP-003", project_key="WRD"),
        today=date(2026, 8, 18),
    )
    assert query.kind is TaskQueryKind.EMPLOYEE_DUE_BY
    assert query.employee_id == "EMP-003"
    assert query.due_by == date(2026, 8, 19)
    assert query.jql is not None
    assert 'labels = "workforce-employee:EMP-003"' in query.jql
    assert 'labels != "workforce-record:employee-profile"' in query.jql
    assert 'duedate <= "2026-08-19"' in query.jql
    assert "statusCategory != Done" in query.jql


@pytest.mark.unit
def test_manager_wording_without_due_keyword_is_supported() -> None:
    question = "How many tasks does Employee 3 have to do till tomorrow?"
    assert classify_intent(question, default_scope="employee") is Intent.JIRA_TASK_QUERY
    query = parse_task_query(
        question,
        EntityReferences(project_key="WRD"),
        today=date(2026, 8, 18),
    )
    assert query.employee_id == "EMP-003"
    assert query.due_by == date(2026, 8, 19)


@pytest.mark.unit
def test_ambiguous_employee_query_is_rejected() -> None:
    with pytest.raises(ValueError, match="employee"):
        parse_task_query(
            "How many tasks are due tomorrow?",
            EntityReferences(project_key="WRD"),
            today=date(2026, 8, 18),
        )


@pytest.mark.asyncio
async def test_tool_answers_exact_due_date_from_jira_evidence() -> None:
    class Jira:
        async def get_issue(
            self, issue_key: str, *, correlation_id: str
        ) -> JiraIssueEvidence:
            return issue(issue_key, date(2026, 8, 17))

        async def search_issues(
            self, jql: str, *, project_key: str, correlation_id: str
        ) -> tuple[JiraIssueEvidence, ...]:
            raise AssertionError("search should not run")

    result = await JiraTaskQueryTool(Jira(), today=lambda: date(2026, 8, 18)).query(
        "What is the due date of WRD-4?",
        EntityReferences(employee_id="EMP-003", project_key="WRD"),
        "corr-task",
    )
    assert result.answer == "WRD-4 is due on 2026-08-17."
    assert result.evidence_references == ("jira:WRD-4:duedate",)


@pytest.mark.asyncio
async def test_tool_counts_employee_tasks_due_by_tomorrow() -> None:
    class Jira:
        async def get_issue(
            self, issue_key: str, *, correlation_id: str
        ) -> JiraIssueEvidence:
            raise AssertionError("single issue read should not run")

        async def search_issues(
            self, jql: str, *, project_key: str, correlation_id: str
        ) -> tuple[JiraIssueEvidence, ...]:
            return (
                issue("WRD-4", date(2026, 8, 18)),
                issue("WRD-7", date(2026, 8, 19)),
            )

    result = await JiraTaskQueryTool(Jira(), today=lambda: date(2026, 8, 18)).query(
        "How many unfinished tasks does Employee 3 have due by tomorrow?",
        EntityReferences(employee_id="EMP-003", project_key="WRD"),
        "corr-task",
    )
    assert result.answer == (
        "Employee 3 has 2 unfinished tasks due by 2026-08-19: "
        "WRD-4 (due 2026-08-18) and WRD-7 (due 2026-08-19)."
    )


@pytest.mark.asyncio
async def test_tool_defensively_excludes_employee_profile_rows() -> None:
    class Jira:
        async def get_issue(
            self, issue_key: str, *, correlation_id: str
        ) -> JiraIssueEvidence:
            raise AssertionError("single issue read should not run")

        async def search_issues(
            self, jql: str, *, project_key: str, correlation_id: str
        ) -> tuple[JiraIssueEvidence, ...]:
            task = issue("WRD-4", date(2026, 8, 19))
            profile = issue("WRD-12", None).model_copy(
                update={"workforce_employee_id": None}
            )
            return task, profile

    result = await JiraTaskQueryTool(Jira(), today=lambda: date(2026, 8, 18)).query(
        "How many unfinished tasks does Employee 3 have due by tomorrow?",
        EntityReferences(project_key="WRD"),
        "corr-task",
    )
    assert result.answer.startswith("Employee 3 has 1 unfinished task")
    assert [task.key for task in result.tasks] == ["WRD-4"]
