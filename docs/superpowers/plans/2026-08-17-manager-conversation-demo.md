# Manager Conversation and Demo Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let managers ask natural questions about employees and the managed WRD workflow, receive fact-grounded Bedrock prose with a visible source, and run a reliable six-stage Jira demonstration.

**Architecture:** An authenticated Agent API invokes a constrained Bedrock planner that returns only an allowlisted `Intent`; deterministic context validation and MCP tools gather evidence and calculate risk. Bedrock then returns free-form prose inside a minimal validated envelope, while the UI shows only the aggregate score, grade, confidence, freshness, source, prose, and citations.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, Pydantic, Amazon Bedrock Converse API, Jira and Workforce Risk MCP Streamable HTTP, HTML/CSS/JavaScript, pytest, Bash, Kubernetes, GitHub Actions.

## Global Constraints

- Authentication and project authorization occur before LangGraph runs.
- Chat is read-only; Jira mutation remains behind structured proposal approval.
- Workforce Risk MCP owns deterministic scoring and proposal state.
- Bedrock cannot change scores, grades, evidence, entities, or candidates.
- `read degraded; write closed` remains governing behavior.
- Show one aggregate score such as `88/100`; hide factor values, weights, contribution points, thresholds, and intermediate calculations.
- Preserve Low, Medium, High, and Critical grades.
- Do not expose raw tokens, credentials, prompts, or untrusted Jira text.

---

### Task 1: Constrained natural-language planning

**Files:**
- Create: `services/agent-api/src/agent_api/graph/planner.py`
- Modify: `services/agent-api/src/agent_api/graph/workflow.py`
- Modify: `services/agent-api/src/agent_api/graph/state.py`
- Modify: `services/agent-api/src/agent_api/routes/investigations.py`
- Test: `services/agent-api/tests/test_question_planner.py`
- Test: `services/agent-api/tests/test_graph_workflows.py`

**Interfaces:**
- Produces: `QueryPlan(intent: Intent, scope: Literal["employee", "task", "project", "workflow", "operations"], needs_refresh: bool)`.
- Produces: `QuestionPlanner.plan(question, references, correlation_id) -> QueryPlan`.
- Consumes: authenticated `EntityReferences`; never consumes a JWT or API key.

- [ ] **Step 1: Write failing planner tests**

Add parameterized cases for every approved question, including overdue/blocked,
urgency, first action, reassignment, prevention, evidence, missing information,
improvement, and simple-language requests. Assert employee context routes to
`EXPLAIN_EMPLOYEE_OVERLOAD`; workflow context routes to
`EXPLAIN_PROJECT_RISK`; approval language remains `UNSUPPORTED`.

- [ ] **Step 2: Verify the tests fail**

Run:

```bash
.venv/bin/python -m pytest services/agent-api/tests/test_question_planner.py -q
```

Expected: failure because `agent_api.graph.planner` does not exist.

- [ ] **Step 3: Implement the typed planner**

Define a Pydantic `QueryPlan` with `extra="forbid"`. Implement a Bedrock-backed
planner whose tool schema permits only existing `Intent` values and the five
scopes. Reject write language before Bedrock. If Bedrock planning fails, choose
the safe read-only intent from selected context: employee → overload, task →
task fit, project/workflow → project risk. Never default to a write-oriented
intent.

- [ ] **Step 4: Wire the planner into LangGraph**

Replace keyword-only `classify_supported_intent` with an async plan node. Store
the validated plan in `GraphState`, preserve tool and step limits, and inject
the planner from `get_question_planner()` in the authenticated route.

- [ ] **Step 5: Verify planner and graph behavior**

```bash
.venv/bin/python -m pytest services/agent-api/tests/test_question_planner.py services/agent-api/tests/test_graph_workflows.py -q
.venv/bin/python -m ruff check services/agent-api/src/agent_api/graph services/agent-api/tests
```

Expected: all tests pass; mutations remain unsupported.

- [ ] **Step 6: Commit**

```bash
git add services/agent-api/src/agent_api/graph services/agent-api/src/agent_api/routes/investigations.py services/agent-api/tests
git commit -m "feat: plan natural manager questions safely"
```

### Task 2: Natural Bedrock answers with fact consistency

**Files:**
- Modify: `services/agent-api/src/agent_api/llm/schemas.py`
- Modify: `services/agent-api/src/agent_api/llm/factory.py`
- Modify: `services/agent-api/src/agent_api/llm/bedrock.py`
- Modify: `services/agent-api/src/agent_api/llm/fallback.py`
- Test: `services/agent-api/tests/test_explanations.py`

**Interfaces:**
- Produces: `NaturalExplanation(answer: str, citations: tuple[str, ...], score: int | None, risk_level: str | None)`.
- `ExplanationResponse` adds `source`, `correlation_id`, and `suggested_questions` while retaining protected facts.

- [ ] **Step 1: Write failing natural-answer tests**

Test valid free-form prose without contributor/recommendation arrays, exact
score and grade preservation, citation allowlisting, zero blocked/overdue fact
consistency, missing-data wording, invented entity rejection, Bedrock timeout,
and deterministic fallback labelling.

- [ ] **Step 2: Verify tests fail**

```bash
.venv/bin/python -m pytest services/agent-api/tests/test_explanations.py -q
```

Expected: failures because the current schema requires rigid root-cause and
recommendation lists.

- [ ] **Step 3: Implement the minimal answer envelope**

Change the Bedrock tool schema to require `answer`, `citations`, `score`, and
`risk_level`; make suggested questions optional and bounded. Include explicit
structured factor facts in `build_model_payload`. Update the system prompt to
answer the manager's exact question naturally and distinguish facts from
recommendations.

- [ ] **Step 4: Add deterministic consistency checks**

Keep exact score/grade, citation, and candidate checks. Reject explicit positive
blocked/overdue claims when their normalized structured values are zero. Do not
reject an otherwise valid answer merely because it lacks optional headings.
Return the fallback only for unavailable Bedrock or material contradictions.

- [ ] **Step 5: Verify**

```bash
.venv/bin/python -m pytest services/agent-api/tests/test_explanations.py -q
.venv/bin/python -m ruff check services/agent-api/src/agent_api/llm services/agent-api/tests/test_explanations.py
```

Expected: natural prose is accepted; contradictory facts fall back safely.

- [ ] **Step 6: Commit**

```bash
git add services/agent-api/src/agent_api/llm services/agent-api/tests/test_explanations.py
git commit -m "feat: return grounded natural Bedrock answers"
```

### Task 3: Context-first manager UI

**Files:**
- Modify: `services/agent-api/src/agent_api/web/templates/chat.html`
- Modify: `services/agent-api/src/agent_api/web/static/chat.js`
- Modify: `services/agent-api/src/agent_api/web/static/styles.css`
- Test: `services/agent-api/tests/ui/test_contextual_chat.py`

**Interfaces:**
- Consumes: `InvestigationResponse.explanation.answer`, `.source`, `.citations`, and `.suggested_questions`.
- Sends: bounded `EntityReferences`, never evidence bundles or hidden context.

- [ ] **Step 1: Write failing UI tests**

Assert context controls for workflow/employee/task, a source badge, natural
answer region, aggregate score and grade, confidence/freshness, citations, and
follow-up buttons. Assert factor value/weight/contribution columns are absent.

- [ ] **Step 2: Verify tests fail**

```bash
.venv/bin/python -m pytest services/agent-api/tests/ui/test_contextual_chat.py -q
```

- [ ] **Step 3: Implement the accessible UI**

Make chat the primary panel. Add a context-type select and conditional employee
or task reference input. Render `Amazon Bedrock` or `Deterministic fallback`,
the free-form answer, `score/100`, grade, confidence, evidence age, citations,
and suggested follow-ups. Keep alerts, reports, proposals, and audit panels.
Remove the factor calculation table from manager presentation.

- [ ] **Step 4: Verify UI behavior**

```bash
.venv/bin/python -m pytest services/agent-api/tests/ui/test_contextual_chat.py -q
.venv/bin/python -m pytest services/agent-api/tests/test_graph_workflows.py -q
```

Expected: tests pass and API keys remain session-storage-only.

- [ ] **Step 5: Commit**

```bash
git add services/agent-api/src/agent_api/web services/agent-api/tests/ui
git commit -m "feat: redesign contextual manager conversation"
```

### Task 4: Reliable observable Jira demo

**Files:**
- Modify: `scripts/demo/readiness.sh`
- Modify: `scripts/demo/auto_demo.sh`
- Modify: `services/agent-api/src/agent_api/routes/scans.py`
- Modify: `packages/persistence/src/workforce_persistence/scan_repository.py`
- Test: `tests/e2e/test_demo_scripts.py`
- Test: `services/agent-api/tests/test_scan_routes.py`

**Interfaces:**
- Scan status returns safe `failure_code` and its correlation ID for failed runs.
- Demo script prints stage, scan terminal state, and EMP-001/EMP-002/EMP-006 grade.

- [ ] **Step 1: Write failing scan and script tests**

Cover successful six-stage progression, failed-scan diagnostics, interruption,
AWS/local endpoint labelling, deployed explanation-source probe, three moving
employees, and absence of secrets in output.

- [ ] **Step 2: Verify tests fail**

```bash
.venv/bin/python -m pytest tests/e2e/test_demo_scripts.py services/agent-api/tests/test_scan_routes.py -q
```

- [ ] **Step 3: Implement safe scan diagnostics**

Map stored internal exceptions to allowlisted failure codes in the scan status
response. Include correlation ID; never return credentials, raw exceptions, or
stack traces.

- [ ] **Step 4: Make the demo self-explanatory**

Detect the configured target URL, probe the API's actual explanation source,
poll each scan to a bounded terminal state, print safe diagnostics on failure,
query each moving employee after a completed scan, and print its grade. Preserve
the last completed Jira stage on interruption.

- [ ] **Step 5: Verify locally**

```bash
.venv/bin/python -m pytest tests/e2e/test_demo_scripts.py services/agent-api/tests/test_scan_routes.py -q
bash -n scripts/demo/readiness.sh scripts/demo/auto_demo.sh
```

Expected: tests pass and scripts have valid syntax.

- [ ] **Step 6: Commit**

```bash
git add scripts/demo services/agent-api/src/agent_api/routes/scans.py packages/persistence/src/workforce_persistence/scan_repository.py tests/e2e services/agent-api/tests/test_scan_routes.py
git commit -m "fix: make Jira demo progression observable"
```

### Task 5: Full verification, PR, AWS deployment, and runbook

**Files:**
- Modify: `README.md`
- Modify: `docs/runbooks/demo.md`
- Test: existing repository test suites and deployed smoke tests.

**Interfaces:**
- Documents instance start, application readiness, credentials, simulation, Jira view, UI view, interruption, and cleanup commands.

- [ ] **Step 1: Run required local verification**

```bash
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest -m 'unit or security' -q
.venv/bin/python -m pytest services/agent-api/tests tests/e2e/test_demo_scripts.py -q
git diff --check
```

Expected: all commands pass.

- [ ] **Step 2: Document exact operating commands**

Document starting stopped EC2 instances using the Terraform-owned instance IDs
resolved by project tags, waiting for SSM and Kubernetes readiness, retrieving
the dev manager key without printing it into history, exporting Jira MCP
authorization locally, opening Jira and the Manager UI, running
`DEMO_STAGE_SECONDS=10 bash scripts/demo/auto_demo.sh`, and safely stopping the
demo or instances.

- [ ] **Step 3: Commit documentation**

```bash
git add README.md docs/runbooks/demo.md
git commit -m "docs: add AWS manager demo runbook"
```

- [ ] **Step 4: Push a feature branch and open a PR to `dev`**

```bash
git push -u origin HEAD
gh pr create --base dev --fill
gh pr checks --watch
```

Expected: required CI passes.

- [ ] **Step 5: Merge and verify AWS**

Merge only after CI passes. Wait for `deploy-dev.yml`, then run the deployed
question matrix and the full six-stage script. Confirm Bedrock source for valid
calls, explicit fallback when injected, three critical alerts, recovery
resolution, Jira changes, and no secret leakage.

- [ ] **Step 6: Record evidence**

Attach CI, deployment, question-matrix, scan-stage, and screenshot summaries to
the PR or deployment artifacts. Do not claim completion unless all live gates
pass.
