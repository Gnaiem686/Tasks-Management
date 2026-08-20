# Compact Manager Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved one-screen manager dashboard and reliable natural-language Bedrock chat.

**Architecture:** Keep the existing FastAPI template and vanilla JavaScript client. Add a project-evidence fallback at the LangGraph routing boundary, render bounded dashboard previews with drawers for full lists, and hide machine-readable citations in the browser while retaining backend validation.

**Tech Stack:** FastAPI, LangGraph, vanilla JavaScript/CSS, pytest, Amazon Bedrock, Jira MCP.

## Global Constraints

- Jira remains read-only for WFD and WRD dashboard interactions.
- Deterministic evidence and scores are not altered by Bedrock.
- Raw Jira evidence identifiers are never displayed in chat.
- The primary desktop dashboard fits in one viewport and the chat scrolls independently.

---

### Task 1: Route broad workforce questions to project evidence

**Files:**
- Modify: `services/agent-api/src/agent_api/graph/workflow.py`
- Test: `services/agent-api/tests/test_project_chat.py`

**Interfaces:**
- Consumes: `InvestigationWorkflow._project_tool.build(project_key, correlation_id)`.
- Produces: a `DashboardSnapshot` for broad task/employee questions that the narrow task-query parser cannot answer.

- [ ] Write a failing workflow test using “Which employees are at risk and why?” and assert the project tool is called.
- [ ] Run `.venv/bin/pytest -q services/agent-api/tests/test_project_chat.py` and confirm the unsupported task-query failure.
- [ ] Catch only the narrow query's unsupported-question `ValueError`; gather the configured project snapshot without hiding transport or authorization failures.
- [ ] Run the focused tests and confirm a Bedrock-source response.

### Task 2: Render the compact reference layout

**Files:**
- Modify: `services/agent-api/src/agent_api/web/templates/chat.html`
- Modify: `services/agent-api/src/agent_api/web/static/styles.css`
- Modify: `services/agent-api/src/agent_api/web/static/chat.js`
- Test: `services/agent-api/tests/ui/test_dashboard_layout.py`
- Test: `services/agent-api/tests/ui/test_manager_supporting_views.py`

**Interfaces:**
- Consumes: existing `/api/v1/projects` and `/api/v1/dashboard` responses.
- Produces: bounded preview regions and reusable `openCollectionDrawer(title, items, renderer)` behavior.

- [ ] Add failing assertions for the 70/30 desktop grid, four compact metric cards, five employee rows, four alerts, two lower overview cards, view-all controls, and fixed chat composer.
- [ ] Run the UI tests and confirm they fail on the current long layout.
- [ ] Update semantic HTML regions to mirror the approved reference.
- [ ] Update rendering so primary tables/lists are sliced and full collections open in the existing dialog.
- [ ] Add compact spacing, independent panel scrolling, and green/orange/red risk styling.
- [ ] Run the focused UI tests and verify the responsive breakpoint keeps the mobile layout usable.

### Task 3: Present natural Bedrock conversation

**Files:**
- Modify: `services/agent-api/src/agent_api/web/static/chat.js`
- Test: `services/agent-api/tests/ui/test_contextual_chat.py`
- Test: `services/agent-api/tests/ui/test_operation_status.py`

**Interfaces:**
- Consumes: `InvestigationResponse.explanation.answer` with `source == "bedrock"`.
- Produces: plain conversational messages without raw `explanation.citations`.

- [ ] Add a failing test proving `jira:WFD-13:summary` is not rendered.
- [ ] Add a failing test proving a Bedrock paragraph is preserved verbatim.
- [ ] Render only `explanation.answer`; remove the raw citation suffix.
- [ ] Replace raw HTTP text such as `Request failed (503)` with a friendly assistant availability message.
- [ ] Run the focused UI tests.

### Task 4: Verify, commit, and deploy

**Files:**
- Modify only if a regression requires it: `.github/workflows/deploy-dev.yml`

**Interfaces:**
- Consumes: the repository's existing CI/CD workflow.
- Produces: an immutable dev release deployed to the existing AWS URL.

- [ ] Run `make lint` and `make typecheck` with the repository uv environment.
- [ ] Run the focused workflow and UI tests, then the required isolated suite.
- [ ] Commit with `feat: deliver compact manager dashboard` and push `dev`.
- [ ] Wait for `deploy-dev.yml` and its smoke checks.
- [ ] Verify the public dashboard and ask “Which employees are at risk and why?”; require an HTTP 200 Bedrock response with no raw evidence IDs in the rendered UI.
