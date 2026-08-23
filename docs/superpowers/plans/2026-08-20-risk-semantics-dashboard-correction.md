# Risk Semantics and Dashboard Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct dashboard risk semantics and make Bedrock explanations match deterministic WFD evidence.

**Architecture:** Normalize Jira task facts in `DashboardService`, keep local
workforce capacity in environment configuration, and validate Bedrock output
against the normalized snapshot. Render only manager-facing identifiers and
labels in the existing compact UI.

**Tech Stack:** Python, FastAPI, Pydantic, JavaScript, pytest

## Global Constraints

- Work locally only; do not push or deploy to AWS.
- Scores remain deterministic; Bedrock only explains evidence.
- Missing evidence is never silently treated as low risk.

---

### Task 1: Normalize workload and dependency facts

**Files:**
- Modify: `services/agent-api/src/agent_api/dashboard/service.py`
- Modify: `services/agent-api/src/agent_api/dashboard/models.py`
- Test: `services/agent-api/tests/test_dashboard_service.py`

**Interfaces:**
- Consumes: normalized `JiraIssueEvidence`
- Produces: corrected `DashboardSnapshot`

- [ ] Write failing tests for Done work, blocked direction, and attention filtering.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement effective remaining work and explicit data-quality findings.
- [ ] Run focused tests and confirm they pass.

### Task 2: Configure local WFD capacity and visible levels

**Files:**
- Modify: `compose.yaml`
- Modify: `services/agent-api/src/agent_api/web/static/chat.js`
- Test: `services/agent-api/tests/ui/test_manager_supporting_views.py`

**Interfaces:**
- Consumes: authoritative `WORKFORCE_DASHBOARD_PROFILES`
- Produces: Low, Medium, High, or Insufficient data manager display

- [ ] Write failing profile and visible-level tests.
- [ ] Add the approved local WFD capacity configuration.
- [ ] Map Critical to High only at presentation boundaries.
- [ ] Verify UI tests.

### Task 3: Enforce explanation consistency

**Files:**
- Modify: `services/agent-api/src/agent_api/llm/bedrock.py`
- Test: `services/agent-api/tests/test_project_chat.py`

**Interfaces:**
- Consumes: corrected `DashboardSnapshot`
- Produces: evidence-specific Bedrock prose preserving deterministic levels

- [ ] Write a failing test for an explanation that promotes Insufficient data.
- [ ] Reject contradictory model classifications and retry with correction.
- [ ] Verify focused Bedrock and project-chat tests.

### Task 4: Run local acceptance check

**Files:**
- No production files

**Interfaces:**
- Consumes: local Jira and Bedrock credentials
- Produces: current compact UI at `http://127.0.0.1:8000`

- [ ] Run lint and focused tests.
- [ ] Restart local MCP and Agent API processes.
- [ ] Verify dashboard totals, employee levels, blocked count, and chat answers.
