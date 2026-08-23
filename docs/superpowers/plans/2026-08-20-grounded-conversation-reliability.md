# Grounded Conversation Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Jira factual answers deterministic, preserve typed task referents across chat turns, reject ungrounded claims, and expose classified server-side failure diagnostics.

**Architecture:** Add typed conversation evidence to the investigation contract and deterministic Jira-query handlers ahead of Bedrock. Add centralized failure classification and correlation-aware structured lifecycle logging at API, graph, Jira, and Bedrock boundaries.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, LangGraph, Atlassian MCP Streamable HTTP, Amazon Bedrock, browser JavaScript, pytest.

## Global Constraints

- Jira is the factual source of truth for task fields.
- Bedrock must not independently select or change Jira facts.
- Simple factual queries bypass Bedrock.
- Retries are bounded to three total attempts and only transient failures.
- Credentials, tokens, prompts, and raw sensitive evidence must not be logged.
- Changes remain local; do not deploy to AWS.

---

### Task 1: Typed factual query and conversation context

**Files:**
- Modify: `services/agent-api/src/agent_api/task_queries.py`
- Modify: `services/agent-api/src/agent_api/graph/state.py`
- Modify: `services/agent-api/src/agent_api/routes/investigations.py`
- Test: `services/agent-api/tests/test_task_queries.py`

**Interfaces:**
- Produces: typed issue facts, deterministic answer text, and bounded previous-answer context.
- Consumes: validated Jira MCP issue/search responses and project-scoped references.

- [ ] Add failing tests for done tasks, status, assignee, missing estimates, blocked, overdue, due-soon, single "that task" resolution, and ambiguous referents.
- [ ] Run the focused tests and confirm failures describe missing behavior.
- [ ] Add the minimal typed models, classifiers, JQL builders, deterministic formatters, and referent resolver.
- [ ] Run the focused tests and confirm they pass.

### Task 2: Grounding validation

**Files:**
- Modify: `services/agent-api/src/agent_api/llm/bedrock.py`
- Create: `services/agent-api/src/agent_api/grounding.py`
- Test: `services/agent-api/tests/test_grounding.py`

**Interfaces:**
- Produces: `validate_jira_claims(answer, evidence)` which rejects mismatched issue key, summary, assignee, or status.
- Consumes: the exact typed evidence used for the answer.

- [ ] Add failing tests for WFD-1/WFD-7 substitution and each mismatched Jira field.
- [ ] Confirm the tests fail before implementation.
- [ ] Implement validation and connect it to Bedrock response acceptance.
- [ ] Confirm focused tests pass.

### Task 3: Classified diagnostics and bounded retries

**Files:**
- Create: `services/agent-api/src/agent_api/failure_diagnostics.py`
- Modify: `services/agent-api/src/agent_api/routes/investigations.py`
- Modify: `services/agent-api/src/agent_api/graph/workflow.py`
- Modify: `packages/jira-mcp-client/src/jira_mcp_client/client.py`
- Modify: `services/agent-api/src/agent_api/llm/factory.py`
- Test: `services/agent-api/tests/test_failure_diagnostics.py`
- Test: `services/agent-api/tests/test_risk_endpoint.py`

**Interfaces:**
- Produces: stable failure codes and structured lifecycle log events sharing one correlation ID.
- Consumes: typed exceptions from Jira transport, Bedrock, parsing, grounding, and graph execution.

- [ ] Add failing classification, retry, and correlation-log tests.
- [ ] Confirm they fail for absent diagnostics.
- [ ] Implement safe classification and event logging without evidence or secrets.
- [ ] Ensure retry ownership remains at the existing Jira and Bedrock boundaries and excludes non-transient failures.
- [ ] Run focused tests and confirm they pass.

### Task 4: Browser context continuity and local verification

**Files:**
- Modify: `services/agent-api/src/agent_api/web/static/chat.js`
- Test: `services/agent-api/tests/ui/test_contextual_chat.py`

**Interfaces:**
- Produces: per-project bounded structured context sent with the next investigation request.
- Consumes: investigation response context returned by Task 1.

- [ ] Add failing UI tests proving WFD-7 context is submitted on "that task" and cleared per project/session.
- [ ] Implement the minimal session context persistence.
- [ ] Run UI and full focused suites, lint modified files, and verify the local WFD flow.
- [ ] Restart the local API and open `http://127.0.0.1:8000`.
