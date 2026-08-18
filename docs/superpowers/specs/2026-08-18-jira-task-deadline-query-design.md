# Jira Task and Deadline Query Design

## Goal

Allow an authorized manager to ask factual questions such as “What is the due date of WRD-4?” and “How many unfinished tasks does Employee 3 have due by tomorrow?” without routing those questions into risk scoring.

## Selected design

Add a finite, read-only `jira_task_query` LangGraph intent. A deterministic parser recognizes either an exact Jira issue key or an employee task/deadline query. The workflow calls Atlassian Rovo MCP using `getJiraIssue` or `searchJiraIssuesUsingJql`, validates typed structured fields, excludes `workforce-record:employee-profile` rows from task results, and returns a factual answer with Jira evidence references. Relative dates use the configured `Asia/Jerusalem` business timezone.

Bedrock may phrase the validated facts naturally, but it cannot create issue keys, counts, dates, or statuses. If Bedrock is unavailable or returns invalid output, the deterministic factual answer is returned. The workflow is read-only and preserves project authorization, correlation IDs, timeouts, bounded retries, and `read degraded; write closed`.

## Alternatives rejected

- Reusing employee-overload scoring cannot answer exact dates or counts and caused the observed incorrect response.
- Allowing Bedrock to construct arbitrary Jira queries would make counts and dates non-deterministic and weaken tool boundaries.

## Acceptance criteria

- `What is the due date of WRD-4?` returns WRD-4’s structured Jira due date.
- `How many unfinished tasks does Employee 3 have due by tomorrow?` returns the exact structured count and matching issue list.
- Employee-profile rows never count as tasks.
- Unsupported or ambiguous queries fail clearly rather than guessing.
- Tests cover classification, parsing, Jira MCP response validation, authorization, correlation propagation, exact answers, and fallback behavior.
