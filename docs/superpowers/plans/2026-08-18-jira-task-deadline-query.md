# Jira Task and Deadline Query Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add accurate natural-language task due-date and employee deadline-count answers using structured Jira MCP evidence.

**Architecture:** Extend the finite LangGraph intent set with a read-only Jira task query. Parse a bounded query deterministically, retrieve typed Jira evidence through the existing MCP client, and return a factual response that the UI already renders.

**Tech Stack:** Python, FastAPI, LangGraph, Pydantic, Atlassian Rovo MCP Streamable HTTP, pytest, vanilla JavaScript UI.

## Global Constraints

- Jira MCP is the integration path; do not add REST fallback.
- Use structured Jira fields only for dates, counts, status, and employee mapping.
- Exclude `workforce-record:employee-profile` records from task counts.
- Preserve project authorization, correlation IDs, bounded retries, and `read degraded; write closed`.
- No Jira mutation is permitted.

---

### Task 1: Typed Jira task-query model and parser

**Files:**
- Create: `services/agent-api/src/agent_api/task_queries.py`
- Modify: `services/agent-api/src/agent_api/graph/intents.py`
- Test: `services/agent-api/tests/test_task_queries.py`

**Interfaces:**
- Produces: `TaskQuery`, `TaskQueryResult`, and `parse_task_query(question, references, today)`.

- [ ] Write failing tests for exact issue due-date queries, Employee 3 due-by-tomorrow queries, profile-row exclusion, and ambiguous input.
- [ ] Run `uv run pytest services/agent-api/tests/test_task_queries.py -q` and confirm failures identify the missing feature.
- [ ] Implement the minimal typed parser and `JIRA_TASK_QUERY` intent classification.
- [ ] Re-run the focused tests and confirm they pass.

### Task 2: Jira MCP structured query boundary

**Files:**
- Modify: `packages/jira-mcp-client/src/jira_mcp_client/client.py`
- Modify: `packages/jira-mcp-client/src/jira_mcp_client/normalize.py`
- Modify: `packages/contracts/src/workforce_contracts/jira.py`
- Test: `packages/jira-mcp-client/tests/test_client.py`

**Interfaces:**
- Produces: `JiraEvidenceClient.search_issues(jql, correlation_id)` returning validated task evidence.

- [ ] Write failing tests for search result schema, environment/correlation validation, malformed payload rejection, and bounded read behavior.
- [ ] Run the focused client tests and observe the intended failures.
- [ ] Implement typed search normalization and the MCP `searchJiraIssuesUsingJql` call.
- [ ] Re-run focused tests and confirm they pass.

### Task 3: LangGraph workflow and HTTP/UI response

**Files:**
- Modify: `services/agent-api/src/agent_api/graph/state.py`
- Modify: `services/agent-api/src/agent_api/graph/workflow.py`
- Modify: `services/agent-api/src/agent_api/routes/investigations.py`
- Modify: `services/agent-api/src/agent_api/web/static/chat.js` only if the typed answer requires rendering support.
- Test: `services/agent-api/tests/test_graph_workflows.py`
- Test: `services/agent-api/tests/test_investigations.py`

**Interfaces:**
- Consumes: typed task query and Jira evidence client.
- Produces: an `InvestigationResponse` with a factual answer, evidence citations, source, and correlation ID.

- [ ] Write failing graph and route tests for the two approved example questions and authorization boundaries.
- [ ] Run focused tests and verify the current misrouting/rejection failures.
- [ ] Route the new intent to the Jira query tool and construct the deterministic factual response; optionally allow Bedrock wording without changing facts.
- [ ] Re-run focused tests and the Agent API suite.

### Task 4: Regression and deployment verification

**Files:**
- Modify only tests or deployment metadata required by the existing release process.

**Interfaces:**
- Produces: verified dev behavior for exact due-date and deadline-count questions.

- [ ] Run `uv run pytest services/agent-api/tests packages/jira-mcp-client/tests -q`.
- [ ] Run formatting and typing checks used by CI.
- [ ] Commit the feature, push its branch, open a PR to `dev`, and verify required checks.
- [ ] After merge and dev deployment, ask both approved questions in the Manager UI and confirm Jira-backed answers and citations.
