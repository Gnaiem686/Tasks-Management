from datetime import date

import pytest
from agent_api.graph.intents import Intent, classify_intent
from agent_api.graph.state import EntityReferences
from agent_api.task_queries import (
    GroundedAnswerContext,
    JiraTaskQueryTool,
    TaskFact,
    TaskQueryKind,
    parse_task_query,
)
from workforce_contracts.jira import JiraAccountRef, JiraIssueEvidence, JiraIssueLink


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


@pytest.mark.asyncio
async def test_done_tasks_are_formatted_directly_from_jira() -> None:
    class Jira:
        async def get_issue(
            self, issue_key: str, *, correlation_id: str
        ) -> JiraIssueEvidence:
            raise AssertionError("single issue read should not run")

        async def search_issues(
            self, jql: str, *, project_key: str, correlation_id: str
        ) -> tuple[JiraIssueEvidence, ...]:
            assert "statusCategory = Done" in jql
            return (
                issue("WFD-7", date(2026, 8, 28)).model_copy(
                    update={
                        "summary": "Admin dashboard filters and export",
                        "status": "Done",
                        "assignee": JiraAccountRef(
                            account_id="account-mohammad", display_name="Mohammad"
                        ),
                    }
                ),
            )

    result = await JiraTaskQueryTool(Jira(), today=lambda: date(2026, 8, 20)).query(
        "Which tasks are done?",
        EntityReferences(project_key="WFD"),
        "corr-done",
    )

    assert result.answer == (
        "WFD-7 — Admin dashboard filters and export — Done — assigned to Mohammad."
    )
    assert result.tasks[0].assignee == "Mohammad"
    assert result.context is not None
    assert result.context.intent == "list_done_tasks"
    assert result.context.issues[0].key == "WFD-7"


@pytest.mark.asyncio
async def test_blocked_work_excludes_unrelated_active_tasks() -> None:
    class Jira:
        async def get_issue(
            self, issue_key: str, *, correlation_id: str
        ) -> JiraIssueEvidence:
            raise AssertionError("single issue read should not run")

        async def search_issues(
            self, jql: str, *, project_key: str, correlation_id: str
        ) -> tuple[JiraIssueEvidence, ...]:
            assert " OR " not in jql
            blocked = issue("WFD-4", date(2026, 8, 23)).model_copy(
                update={
                    "links": (
                        JiraIssueLink(relationship="is blocked by", issue_key="WFD-2"),
                    )
                }
            )
            unrelated = issue("WFD-6", date(2026, 8, 27))
            return blocked, unrelated

    result = await JiraTaskQueryTool(Jira(), today=lambda: date(2026, 8, 20)).query(
        "Which work is blocked right now?",
        EntityReferences(project_key="WFD"),
        "corr-blocked",
    )

    assert [task.key for task in result.tasks] == ["WFD-4"]
    assert "WFD-4" in result.answer
    assert "WFD-6" not in result.answer


@pytest.mark.asyncio
async def test_single_prior_task_resolves_that_task_without_searching() -> None:
    prior = GroundedAnswerContext(
        intent="list_done_tasks",
        issues=(
            TaskFact(
                key="WFD-7",
                summary="Admin dashboard filters and export",
                status="Done",
                assignee="Mohammad",
            ),
        ),
    )

    class Jira:
        async def get_issue(
            self, issue_key: str, *, correlation_id: str
        ) -> JiraIssueEvidence:
            assert issue_key == "WFD-7"
            return issue("WFD-7", date(2026, 8, 28)).model_copy(
                update={
                    "summary": "Admin dashboard filters and export",
                    "status": "Done",
                    "assignee": JiraAccountRef(
                        account_id="account-mohammad", display_name="Mohammad"
                    ),
                }
            )

        async def search_issues(
            self, jql: str, *, project_key: str, correlation_id: str
        ) -> tuple[JiraIssueEvidence, ...]:
            raise AssertionError("referent resolution must not search")

    result = await JiraTaskQueryTool(Jira(), today=lambda: date(2026, 8, 20)).query(
        "Which employee have done that task?",
        EntityReferences(project_key="WFD"),
        "corr-follow-up",
        previous_context=prior,
    )

    assert result.answer == (
        "Mohammad is assigned to WFD-7, Admin dashboard filters and export, "
        "which is currently Done."
    )
    assert result.tasks[0].key == "WFD-7"


@pytest.mark.asyncio
async def test_multiple_prior_tasks_require_disambiguation() -> None:
    prior = GroundedAnswerContext(
        intent="list_done_tasks",
        issues=(
            TaskFact(key="WFD-7", summary="First", status="Done"),
            TaskFact(key="WFD-8", summary="Second", status="Done"),
        ),
    )

    class Jira:
        async def get_issue(
            self, issue_key: str, *, correlation_id: str
        ) -> JiraIssueEvidence:
            raise AssertionError("ambiguous referent must not call Jira")

        async def search_issues(
            self, jql: str, *, project_key: str, correlation_id: str
        ) -> tuple[JiraIssueEvidence, ...]:
            raise AssertionError("ambiguous referent must not search")

    result = await JiraTaskQueryTool(Jira(), today=lambda: date(2026, 8, 20)).query(
        "Who did that task?",
        EntityReferences(project_key="WFD"),
        "corr-ambiguous",
        previous_context=prior,
    )

    assert result.answer == "Which task do you mean: WFD-7 or WFD-8?"
    assert result.tasks == ()
