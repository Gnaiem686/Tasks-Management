# Live Jira Progress History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make WFD refreshes use live Jira progress while PostgreSQL retains deduplicated task history for grounded current and historical analysis.

**Architecture:** Extend the typed Jira contract with time-spent evidence, persist a current task observation plus immutable change-only snapshots/events, and record observations from the existing dashboard/agent Jira read path. Keep the manager UI read-only and preserve existing authentication.

**Tech Stack:** Python 3.12, Pydantic, SQLAlchemy/Alembic, PostgreSQL, FastAPI, Atlassian Rovo MCP, pytest.

## Global Constraints

- Jira is authoritative for current task state; PostgreSQL is authoritative for stored history and profiles.
- Never infer progress from elapsed time or claim absence of actual employee work.
- Missing estimates remain unknown, never zero.
- Existing API-key and internal MCP authorization remain unchanged.
- No GitHub, CI/CD, or deployment changes are part of this plan.

---

### Task 1: Dynamic profile and Jira progress contracts

**Files:**
- Modify: `packages/contracts/src/workforce_contracts/jira.py`
- Modify: `packages/jira-mcp-client/src/jira_mcp_client/client.py`
- Modify: `packages/jira-mcp-client/src/jira_mcp_client/normalize.py`
- Modify: `domain/workforce_risk/profiles.py`
- Modify: `services/agent-api/src/agent_api/routes/profiles.py`
- Test: `packages/jira-mcp-client/tests/test_normalize.py`
- Test: `domain/workforce_risk/tests/test_profiles.py`

**Interfaces:**
- Produces: `JiraIssueEvidence.time_spent_seconds: int | None` and unrestricted stable internal employee IDs.

- [ ] Write failing tests for normalized `timespent` and non-seven employee IDs.
- [ ] Run targeted tests and confirm expected failures.
- [ ] Add `timespent` to Jira reads/normalization and replace fixed employee-ID/count validation with stable bounded identifiers.
- [ ] Run targeted tests and confirm they pass.

### Task 2: Versioned task progress persistence

**Files:**
- Modify: `packages/persistence/src/workforce_persistence/models.py`
- Create: `packages/persistence/src/workforce_persistence/progress_repository.py`
- Create: `packages/persistence/migrations/versions/0012_task_progress_history.py`
- Modify: `packages/persistence/tests/test_schema.py`
- Create: `packages/persistence/tests/test_progress_repository.py`

**Interfaces:**
- Produces: `TaskProgressObservation`, `ProgressPersistenceResult`, and `TaskProgressRepository.record_observations(...)`.

- [ ] Write failing schema/repository tests for work weeks, current state, snapshots, events, and deduplication.
- [ ] Run tests and confirm expected failures.
- [ ] Add models, migration, typed observations, transactional diff/event persistence, and weekly baselines.
- [ ] Run persistence tests and confirm they pass.

### Task 3: Record live Jira observations during current reads

**Files:**
- Create: `services/agent-api/src/agent_api/progress_history.py`
- Modify: `services/agent-api/src/agent_api/dashboard/service.py`
- Modify: `services/agent-api/src/agent_api/routes/dashboard.py`
- Modify: `services/agent-api/src/agent_api/dashboard/models.py`
- Test: `services/agent-api/tests/test_dashboard_service.py`
- Create: `services/agent-api/tests/test_progress_history.py`

**Interfaces:**
- Consumes: `TaskProgressRepository.record_observations(...)`.
- Produces: current task `time_spent_hours`, `last_recorded_progress_at`, and `remaining_change_hours` fields.

- [ ] Write failing tests for latest Jira values, current observation persistence, and safe no-database degradation.
- [ ] Run tests and confirm expected failures.
- [ ] Record validated observations after Jira normalization and expose current progress fields without adding UI mutations.
- [ ] Run dashboard/history tests and confirm they pass.

### Task 4: Historical evidence and local verification

**Files:**
- Modify: `services/agent-api/src/agent_api/evidence/models.py`
- Modify: `services/agent-api/src/agent_api/evidence/collectors.py`
- Modify: `services/agent-api/src/agent_api/web/static/chat.js`
- Test: `services/agent-api/tests/test_evidence_collectors.py`
- Test: `services/agent-api/tests/test_project_chat.py`

**Interfaces:**
- Produces: traceable historical evidence for Bedrock when the evidence plan requests history.

- [ ] Write failing tests showing history evidence reaches a historical question and current-only UI rendering remains read-only.
- [ ] Run tests and confirm expected failures.
- [ ] Load bounded history from PostgreSQL, add safe evidence references, and render current progress fields.
- [ ] Run affected and regression tests.
- [ ] Start the local stack and manually verify `http://127.0.0.1:8000/?project=WFD`.

## Self-review

- [x] No task modifies GitHub workflows or AWS deployment.
- [x] No task automatically changes Jira or decrements remaining estimates.
- [x] Current Jira evidence and historical PostgreSQL evidence have explicit ownership.
- [x] The manager UI remains read-only.
- [x] Tests precede production changes.
