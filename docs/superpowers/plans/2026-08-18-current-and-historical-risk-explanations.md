# Current and Historical Risk Explanations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce concrete, Jira-verifiable current and historical employee-risk explanations containing task dates, remaining work, priorities, blockers, dependencies, capacity, and changes over time.

**Architecture:** Add an allowlisted `RiskEvidenceDossier` assembled from project-scoped Jira MCP reads and authoritative capacity. Pass it beside the unchanged deterministic `RiskResult` to Bedrock and the fallback. Persist the dossier in immutable evidence snapshots and query snapshots for historical/comparison questions.

**Tech Stack:** Python 3.12, Pydantic, FastAPI, LangGraph, Atlassian Rovo MCP Streamable HTTP, Amazon Bedrock, SQLAlchemy/PostgreSQL, pytest.

## Global Constraints

- Deterministic code remains solely responsible for scores and risk levels.
- Jira descriptions and comments are untrusted and report-only; they never affect scoring, confidence, candidate ranking, or proposal evidence.
- Jira reads are restricted to the authenticated environment's configured project and exclude employee-profile rows.
- Jira search results must be complete through bounded pagination or fail as incomplete.
- Bedrock may use only allowlisted structured evidence and known citations.
- Historical answers never substitute current state when a requested snapshot is unavailable.
- Preserve `read degraded; write closed` and never retry ambiguous Jira mutations.

---

### Task 1: Typed current risk-evidence dossier

**Files:**
- Create: `services/agent-api/src/agent_api/risk_evidence.py`
- Modify: `services/agent-api/src/agent_api/dependencies.py`
- Modify: `packages/jira-mcp-client/src/jira_mcp_client/client.py`
- Test: `services/agent-api/tests/test_risk_evidence.py`
- Test: `packages/jira-mcp-client/tests/test_client.py`

**Interfaces:**
- Produces: `TaskSituation`, `RiskEvidenceDossier`, and `JiraRiskEvidenceProvider.get_current_dossier(employee_id, project_key, correlation_id)`.
- Consumes: `JiraEvidenceClient.search_issues(...)`, normalized `JiraIssueEvidence`, and configured employee capacity.

- [ ] **Step 1: Write failing dossier tests**

Create fixtures with three unfinished employee tasks and one employee-profile row. Assert exact task keys, status, priority, due date, remaining hours, blocker category, links, total remaining hours, overdue/due-soon/blocked sets, capacity, evidence time, and citations. Assert profile rows and completed tasks are excluded.

- [ ] **Step 2: Write failing Jira boundary tests**

Assert pagination retrieves all pages, truncation fails closed, and scope-broadening JQL such as `project = "WRD" OR statusCategory != Done` is rejected. Assert timeout retries and circuit state follow the existing bounded read policy.

- [ ] **Step 3: Run focused tests and confirm failure**

Run:
```bash
uv run pytest services/agent-api/tests/test_risk_evidence.py packages/jira-mcp-client/tests/test_client.py -q
```
Expected: failures because the dossier/provider do not exist and unsafe JQL is not rejected.

- [ ] **Step 4: Implement the typed dossier and project-safe reads**

Define frozen, extra-forbidden Pydantic models. Build Jira JQL inside the client/tool boundary from typed project and employee predicates rather than accepting an arbitrary scope-bearing expression. Fetch every bounded page; reject inconsistent project keys, employee IDs, profile records, or incomplete results. Derive factual aggregates without changing score inputs.

- [ ] **Step 5: Run focused tests**

Run the Step 3 command. Expected: all dossier and Jira-client tests pass.

- [ ] **Step 6: Commit checkpoint**

```bash
git add services/agent-api/src/agent_api/risk_evidence.py services/agent-api/src/agent_api/dependencies.py services/agent-api/tests/test_risk_evidence.py packages/jira-mcp-client/src/jira_mcp_client/client.py packages/jira-mcp-client/tests/test_client.py
git commit -m "feat: collect concrete Jira risk evidence"
```

### Task 2: Evidence-rich Bedrock and fallback explanations

**Files:**
- Modify: `services/agent-api/src/agent_api/llm/schemas.py`
- Modify: `services/agent-api/src/agent_api/llm/bedrock.py`
- Modify: `services/agent-api/src/agent_api/llm/fallback.py`
- Modify: `services/agent-api/src/agent_api/graph/state.py`
- Modify: `services/agent-api/src/agent_api/graph/workflow.py`
- Modify: `services/agent-api/src/agent_api/prompts/workforce_analysis.txt`
- Modify: `services/agent-api/tests/test_explanations.py`
- Modify: `services/agent-api/tests/test_graph_workflows.py`

**Interfaces:**
- Consumes: `RiskEvidenceDossier` from Task 1 and unchanged `RiskResult`.
- Produces: `ExplanationRequest.evidence_dossier` and validated natural-language explanations with only known factual claims/citations.

- [ ] **Step 1: Write failing payload and fallback tests**

Assert the allowlisted payload includes task keys, dates, priorities, remaining hours, blocker categories, dependencies, totals, and capacity but excludes raw comments/descriptions. Assert fallback prose names the concrete overdue and blocked tasks.

- [ ] **Step 2: Write failing Bedrock-validation tests**

Reject responses containing an unknown Jira key, unsupported date/hours, unknown blocker, changed score/level, or unknown citation. Accept natural prose with supported facts even when it does not use fixed headings.

- [ ] **Step 3: Write failing graph test**

Assert an employee-risk workflow retrieves the dossier after deterministic scoring and passes the same correlation ID to Jira, the dossier, and Bedrock.

- [ ] **Step 4: Run focused tests and confirm failure**

Run:
```bash
uv run pytest services/agent-api/tests/test_explanations.py services/agent-api/tests/test_graph_workflows.py -q
```
Expected: failures because `ExplanationRequest` has no dossier and the graph does not collect it.

- [ ] **Step 5: Implement current evidence flow**

Add the dossier to graph state and `ExplanationRequest`. After risk scoring, retrieve it using the selected employee and authorized project. Extend the system prompt to lead with urgency and describe exact tasks, dates, workload/capacity, blockers, dependencies, missing evidence, and first management action. Keep score validation unchanged and add dossier fact validation.

- [ ] **Step 6: Implement concrete deterministic fallback**

Render a short situation summary from the same dossier, explicitly marking missing facts. Never generate facts from citation names alone.

- [ ] **Step 7: Run focused tests**

Run the Step 4 command. Expected: all tests pass.

- [ ] **Step 8: Commit checkpoint**

```bash
git add services/agent-api/src/agent_api/llm services/agent-api/src/agent_api/graph services/agent-api/src/agent_api/prompts/workforce_analysis.txt services/agent-api/tests/test_explanations.py services/agent-api/tests/test_graph_workflows.py
git commit -m "feat: explain risks with concrete Jira facts"
```

### Task 3: Immutable historical dossiers and comparisons

**Files:**
- Modify: `services/agent-api/src/agent_api/risk_evidence.py`
- Modify: `services/agent-api/src/agent_api/scans/pipeline.py`
- Modify: `packages/persistence/src/workforce_persistence/repositories.py`
- Create: `packages/persistence/src/workforce_persistence/snapshot_queries.py`
- Modify: `services/agent-api/src/agent_api/graph/intents.py`
- Modify: `services/agent-api/src/agent_api/graph/workflow.py`
- Test: `services/agent-api/tests/test_scan_pipeline.py`
- Create: `packages/persistence/tests/test_snapshot_queries.py`
- Modify: `services/agent-api/tests/test_graph_workflows.py`

**Interfaces:**
- Produces: `HistoricalRiskEvidenceReader.get_at(employee_id, observed_at, environment)` and `.compare(employee_id, start, end, environment)`.
- Consumes: serialized `RiskEvidenceDossier` embedded in immutable `EvidenceSnapshot.evidence`.

- [ ] **Step 1: Write failing persistence tests**

Assert a scan stores the dossier with the score input, repeated identical evidence remains idempotent, old snapshots remain unchanged after Jira changes, and environment/employee filters cannot cross boundaries.

- [ ] **Step 2: Write failing historical-query tests**

Assert nearest-at-or-before lookup, explicit no-snapshot result, and deterministic comparison of remaining hours, completed/disappeared tasks, new tasks, deadline changes, and blocker changes.

- [ ] **Step 3: Write failing intent/graph tests**

Cover “Why did Employee 3 have high risk on August 18?” and “Has Employee 3 improved since August 18?”. Assert no current Jira substitution when history is unavailable.

- [ ] **Step 4: Run focused tests and confirm failure**

Run:
```bash
uv run pytest services/agent-api/tests/test_scan_pipeline.py packages/persistence/tests/test_snapshot_queries.py services/agent-api/tests/test_graph_workflows.py -q
```
Expected: failures because dossiers are not persisted/queryable and historical intents are unsupported.

- [ ] **Step 5: Persist and query immutable dossiers**

Store the allowlisted dossier JSON inside the existing snapshot evidence record; do not add raw Jira text. Add bounded, environment-scoped snapshot queries and typed comparison results. Extend constrained intent parsing for explicit historical dates and improvement/comparison questions.

- [ ] **Step 6: Explain historical and comparison evidence**

Pass the selected historical dossier or typed comparison to the explainer. Include snapshot timestamps and reject unsupported historical claims exactly as for current evidence.

- [ ] **Step 7: Run focused tests**

Run the Step 4 command. Expected: all tests pass.

- [ ] **Step 8: Commit checkpoint**

```bash
git add services/agent-api/src/agent_api/risk_evidence.py services/agent-api/src/agent_api/scans/pipeline.py services/agent-api/src/agent_api/graph packages/persistence/src/workforce_persistence packages/persistence/tests/test_snapshot_queries.py services/agent-api/tests/test_scan_pipeline.py services/agent-api/tests/test_graph_workflows.py
git commit -m "feat: explain historical workforce risk"
```

### Task 4: UI evidence verification and end-to-end acceptance

**Files:**
- Modify: `services/agent-api/src/agent_api/web/static/chat.js`
- Modify: `services/agent-api/src/agent_api/web/templates/chat.html`
- Modify: `services/agent-api/tests/test_manager_ui.py`
- Modify: `services/agent-api/tests/test_risk_endpoint.py`

**Interfaces:**
- Consumes: explanation citations and current/historical source metadata.
- Produces: manager-visible evidence list with exact Jira task keys and links for current facts; snapshot timestamps for historical facts.

- [ ] **Step 1: Write failing UI/API acceptance tests**

Assert current answers display Jira task links and concrete situation text. Assert historical answers display snapshot time and do not link an immutable claim as if it were current Jira state.

- [ ] **Step 2: Run focused tests and confirm failure**

Run:
```bash
uv run pytest services/agent-api/tests/test_manager_ui.py services/agent-api/tests/test_risk_endpoint.py -q
```
Expected: failures because evidence references are not rendered as verification links/source context.

- [ ] **Step 3: Implement verification presentation**

Render current Jira citations as project-scoped issue links and historical citations with an “as observed” timestamp. Preserve accessible link text and safe escaping.

- [ ] **Step 4: Run complete verification**

Run:
```bash
uv run ruff check domain packages services tests
uv run mypy domain packages services
uv run pytest -q
```
Expected: lint and typing succeed; all tests pass.

- [ ] **Step 5: Perform live dev acceptance**

Ask current and historical questions for the seeded WRD scenario. Verify every displayed current task fact in Jira and verify the historical answer remains unchanged after advancing the scenario. Confirm Bedrock and deterministic-fallback paths both produce concrete answers.

- [ ] **Step 6: Commit checkpoint**

```bash
git add services/agent-api/src/agent_api/web services/agent-api/tests/test_manager_ui.py services/agent-api/tests/test_risk_endpoint.py
git commit -m "feat: show verifiable risk evidence"
```
