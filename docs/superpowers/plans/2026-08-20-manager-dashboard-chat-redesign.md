# Manager Dashboard and Bedrock Chat Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a generic, anonymously readable workforce dashboard for configured Jira projects with a persistent project-wide Amazon Bedrock chat panel.

**Architecture:** The Agent API validates projects against an environment allowlist and assembles one typed dashboard snapshot from Jira MCP evidence and workforce configuration. The plain HTML/CSS/JavaScript frontend renders that snapshot in a responsive dashboard with session-only chat history. Successful chat prose comes only from the single configured Bedrock model; public-demo mode rejects every Jira mutation.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, LangGraph, Atlassian Rovo MCP Streamable HTTP, Amazon Bedrock, PostgreSQL, plain HTML/CSS/JavaScript, pytest.

## Global Constraints

- No React, Cognito, frontend credential, or second LLM.
- Initial allowed projects are `WFD` and `WRD`, configured outside frontend code.
- `ALLOW_ANONYMOUS_READ=true` and `ALLOW_JIRA_MUTATIONS=false` for the public demo.
- Every successful visible chat answer comes from Amazon Bedrock.
- Deterministic code remains authoritative for scores, calculations, candidates, and evidence.
- A Bedrock technical failure returns an honest fixed availability notice, never deterministic prose presented as AI.
- Use one `88/100`-style risk score where relevant; do not expose additional internal numeric factors in the primary UI.
- Refresh occurs only on project selection or explicit `Refresh data`.
- Jira descriptions and comments are untrusted evidence.
- Preserve `read degraded; write closed`.

---

## File structure

- Create `services/agent-api/src/agent_api/project_access.py`: project allowlist and anonymous read principal.
- Create `services/agent-api/src/agent_api/dashboard/models.py`: frozen typed dashboard contracts.
- Create `services/agent-api/src/agent_api/dashboard/service.py`: project snapshot aggregation.
- Create `services/agent-api/src/agent_api/dashboard/__init__.py`: package exports.
- Create `services/agent-api/src/agent_api/routes/dashboard.py`: project and dashboard read endpoints.
- Modify `services/agent-api/src/agent_api/main.py`: register dashboard router.
- Modify `services/agent-api/src/agent_api/routes/investigations.py`: anonymous configured-project reads and project-wide context.
- Modify `services/agent-api/src/agent_api/graph/intents.py`: project-wide supported question routing.
- Modify `services/agent-api/src/agent_api/graph/workflow.py`: detailed evidence packet and Bedrock-only success path.
- Modify `services/agent-api/src/agent_api/llm/bedrock.py`: natural answer contract and missing-evidence instructions.
- Modify `services/agent-api/src/agent_api/llm/factory.py`: prohibit deterministic chat fallback in configured public mode.
- Replace `services/agent-api/src/agent_api/web/templates/chat.html`: dashboard application shell.
- Replace `services/agent-api/src/agent_api/web/static/styles.css`: responsive dashboard/chat styling.
- Replace `services/agent-api/src/agent_api/web/static/chat.js`: project state, rendering, detail drawer, and session chat.
- Modify `services/agent-api/src/agent_api/routes/ui.py`: safe initial project metadata only.
- Modify `infra/kubernetes/overlays/dev/environment.yaml`: public-read, mutation-off, and allowed-project settings.
- Modify `infra/kubernetes/overlays/prod/environment.yaml`: explicit secure defaults; do not enable anonymous mode implicitly.
- Add focused tests under `services/agent-api/tests/` and `services/agent-api/tests/ui/`.

### Task 1: Configured project access and anonymous read boundary

**Files:**
- Create: `services/agent-api/src/agent_api/project_access.py`
- Test: `services/agent-api/tests/test_project_access.py`
- Modify: `services/agent-api/src/agent_api/routes/investigations.py`
- Test: `services/agent-api/tests/test_graph_auth_context.py`

**Interfaces:**
- Produces: `ConfiguredProject(key: str, name: str, mutation_enabled: bool)`.
- Produces: `configured_projects() -> tuple[ConfiguredProject, ...]`.
- Produces: `require_configured_project(project_key: str) -> ConfiguredProject`.
- Produces: `anonymous_read_principal(project_key: str) -> AuthenticatedPrincipal`.

- [ ] **Step 1: Write failing allowlist tests**

```python
def test_configured_projects_parse_safe_allowlist(monkeypatch):
    monkeypatch.setenv("ALLOWED_JIRA_PROJECTS", "WFD:Workforce Real Data,WRD:Workforce Risk Demo")
    assert [item.key for item in configured_projects()] == ["WFD", "WRD"]

def test_unknown_project_is_rejected(monkeypatch):
    monkeypatch.setenv("ALLOWED_JIRA_PROJECTS", "WFD:Workforce Real Data")
    with pytest.raises(ProjectAccessDenied):
        require_configured_project("OTHER")
```

- [ ] **Step 2: Verify RED**

Run: `pytest services/agent-api/tests/test_project_access.py -q`  
Expected: FAIL because `agent_api.project_access` does not exist.

- [ ] **Step 3: Implement strict project configuration**

```python
class ConfiguredProject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,19}$")
    name: str = Field(min_length=1, max_length=100)
    mutation_enabled: bool = False

def require_configured_project(project_key: str) -> ConfiguredProject:
    return next(
        (project for project in configured_projects() if project.key == project_key),
        _raise_project_denied(),
    )
```

Create an anonymous viewer principal only when `ALLOW_ANONYMOUS_READ=true`; otherwise retain the existing API-key authentication. Never use anonymous identity for proposal, profile administration, audit, or mutation routes.

- [ ] **Step 4: Add route-boundary tests**

Assert anonymous `WFD` investigation access succeeds when enabled, unknown projects return `403`, and approval/profile/audit routes still reject anonymous callers.

- [ ] **Step 5: Run GREEN checks**

Run: `pytest services/agent-api/tests/test_project_access.py services/agent-api/tests/test_graph_auth_context.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/agent-api/src/agent_api/project_access.py services/agent-api/src/agent_api/routes/investigations.py services/agent-api/tests/test_project_access.py services/agent-api/tests/test_graph_auth_context.py
git commit -m "feat: add configured anonymous project reads"
```

### Task 2: Typed project dashboard snapshot

**Files:**
- Create: `services/agent-api/src/agent_api/dashboard/__init__.py`
- Create: `services/agent-api/src/agent_api/dashboard/models.py`
- Create: `services/agent-api/src/agent_api/dashboard/service.py`
- Create: `services/agent-api/src/agent_api/routes/dashboard.py`
- Modify: `services/agent-api/src/agent_api/main.py`
- Test: `services/agent-api/tests/test_dashboard_service.py`
- Test: `services/agent-api/tests/test_dashboard_routes.py`

**Interfaces:**
- Consumes: `JiraIssueReader.search_issues(jql, project_key, correlation_id)`.
- Produces: `DashboardService.build(project_key, correlation_id) -> DashboardSnapshot`.
- Produces: `GET /api/v1/projects` and `GET /api/v1/dashboard?project_key=...`.

- [ ] **Step 1: Write failing model and aggregation tests**

```python
async def test_dashboard_groups_tasks_by_real_jira_assignee():
    snapshot = await service_with(WFD_ISSUES).build("WFD", "corr-dashboard")
    assert snapshot.project.total_tasks == 15
    assert snapshot.project.completed_tasks == 1
    assert snapshot.employees[0].remaining_hours == 36
    assert snapshot.tasks[0].jira_url.endswith("/browse/WFD-1")
    assert snapshot.correlation_id == "corr-dashboard"

async def test_dashboard_marks_missing_estimate_without_guessing():
    snapshot = await service_with((issue("WFD-14", remaining=None),)).build("WFD", "corr")
    assert snapshot.tasks[0].remaining_hours is None
    assert "WFD-14.remaining_estimate" in snapshot.missing_evidence
```

- [ ] **Step 2: Verify RED**

Run: `pytest services/agent-api/tests/test_dashboard_service.py -q`  
Expected: FAIL because the dashboard package is missing.

- [ ] **Step 3: Define frozen snapshot contracts**

Create models for `ProjectSummary`, `EmployeeSummary`, `TaskSummary`, `AlertSummary`, `WorkloadDistribution`, and `DashboardSnapshot`. Include only one visible score per employee, a risk level, concrete top-risk text, timestamps, provenance, missing sources, and Jira links.

- [ ] **Step 4: Implement one bounded Jira read and aggregation**

Use strict JQL constructed by the service:

```python
jql = f'project = "{project.key}" ORDER BY updated DESC, key ASC'
```

Reject any returned key outside the selected project. Group normal work items by structured Jira assignee. Exclude employee-profile records and completed work from active workload totals. Derive completion and workflow counts from Jira status categories, never from Bedrock.

- [ ] **Step 5: Add project and dashboard routes**

```python
@router.get("/projects", response_model=ProjectListResponse)
async def list_projects() -> ProjectListResponse: ...

@router.get("/dashboard", response_model=DashboardSnapshot)
async def dashboard(project_key: str, request: Request) -> DashboardSnapshot: ...
```

Validate the allowlist before calling Jira. Propagate `X-Correlation-ID`. A partial read returns explicit `degraded=true` and missing sources only when safe.

- [ ] **Step 6: Verify routes and project isolation**

Run: `pytest services/agent-api/tests/test_dashboard_service.py services/agent-api/tests/test_dashboard_routes.py -q`  
Expected: PASS, including `WFD`/`WRD` isolation and unknown-project rejection.

- [ ] **Step 7: Commit**

```bash
git add services/agent-api/src/agent_api/dashboard services/agent-api/src/agent_api/routes/dashboard.py services/agent-api/src/agent_api/main.py services/agent-api/tests/test_dashboard_service.py services/agent-api/tests/test_dashboard_routes.py
git commit -m "feat: expose project workforce dashboard"
```

### Task 3: Project-wide evidence and Bedrock-only chat answers

**Files:**
- Modify: `services/agent-api/src/agent_api/graph/intents.py`
- Modify: `services/agent-api/src/agent_api/graph/workflow.py`
- Modify: `services/agent-api/src/agent_api/llm/bedrock.py`
- Modify: `services/agent-api/src/agent_api/llm/factory.py`
- Modify: `services/agent-api/src/agent_api/routes/investigations.py`
- Test: `services/agent-api/tests/test_project_chat.py`
- Test: `services/agent-api/tests/test_explanations.py`

**Interfaces:**
- Consumes: selected `project_key`, manager question, dashboard/task/profile evidence.
- Produces: Bedrock-generated `ExplanationResponse` with natural answer, validated citations, source `bedrock`, and missing evidence.

- [ ] **Step 1: Write failing behavior tests**

```python
async def test_project_question_resolves_employee_and_sends_concrete_tasks_to_bedrock():
    response = await investigate("Why is Mohammad at risk?", project="WFD")
    assert bedrock_request["evidence"]["tasks"][0]["key"] == "WFD-1"
    assert bedrock_request["evidence"]["tasks"][0]["remaining_hours"] == 3
    assert response.explanation.source == "bedrock"

async def test_bedrock_failure_never_returns_deterministic_prose():
    response = await investigate_with_bedrock_timeout("Summarize WFD")
    assert response.status_code == 503
    assert response.json()["message"] == "The AI assistant is temporarily unavailable. No answer was generated."
```

Also test arbitrary project-wide questions, task keys, employee display names, ambiguity, missing estimates, deadlines, blockers, dependencies, project progress, and prompt injection inside Jira text.

- [ ] **Step 2: Verify RED**

Run: `pytest services/agent-api/tests/test_project_chat.py -q`  
Expected: FAIL because current routing requires narrow intent/context and permits fallback prose.

- [ ] **Step 3: Build a typed project evidence packet**

Resolve named entities only inside the selected project's typed evidence. Include task key, summary, assignee, status, priority, deadline, estimates, blocker category, dependencies, activity, employee capacity/skills, deterministic findings, score, history, missing evidence, and citations. Keep descriptions/comments quoted and untrusted.

- [ ] **Step 4: Make successful chat prose Bedrock-only**

`get_explanation_provider()` returns the single configured Bedrock provider for public chat. Remove deterministic prose fallback from this route. Keep fixed application errors outside the `ExplanationResponse` contract.

The system prompt requires natural concrete answers and permits an explicit statement of insufficient information. It prohibits invented facts, changed scores, hidden-prompt disclosure, and unsupported candidates.

- [ ] **Step 5: Validate returned claims and citations**

Reject unknown Jira citations and any structured score differing from deterministic input. Do not replace a rejected Bedrock response with deterministic prose; return the honest unavailable/error response.

- [ ] **Step 6: Verify GREEN**

Run: `pytest services/agent-api/tests/test_project_chat.py services/agent-api/tests/test_explanations.py services/agent-api/tests/test_graph_workflows.py -q`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/agent-api/src/agent_api/graph services/agent-api/src/agent_api/llm services/agent-api/src/agent_api/routes/investigations.py services/agent-api/tests/test_project_chat.py services/agent-api/tests/test_explanations.py
git commit -m "feat: answer project questions with Bedrock"
```

### Task 4: Responsive dashboard application shell

**Files:**
- Replace: `services/agent-api/src/agent_api/web/templates/chat.html`
- Replace: `services/agent-api/src/agent_api/web/static/styles.css`
- Modify: `services/agent-api/src/agent_api/routes/ui.py`
- Test: `services/agent-api/tests/ui/test_dashboard_layout.py`
- Modify: `services/agent-api/tests/ui/test_api_key_storage.py`

**Interfaces:**
- Consumes: `/api/v1/projects` and `/api/v1/dashboard` responses.
- Produces: semantic DOM IDs used by Task 5 JavaScript.

- [ ] **Step 1: Write failing structure/accessibility tests**

```python
def test_dashboard_has_project_header_cards_detail_drawer_and_persistent_chat():
    html = template()
    for element in (
        "project-select", "refresh-dashboard", "summary-cards", "team-risk-table",
        "risk-alerts", "project-progress", "workload-distribution", "detail-drawer",
        "chat-panel", "chat-messages", "chat-composer",
    ):
        assert f'id="{element}"' in html

def test_frontend_contains_no_api_key_control_or_wrapped_secret():
    assert 'id="api-key"' not in template()
    assert "Authorization: `Bearer" not in script()
```

- [ ] **Step 2: Verify RED**

Run: `pytest services/agent-api/tests/ui/test_dashboard_layout.py services/agent-api/tests/ui/test_api_key_storage.py -q`  
Expected: FAIL against the old single-column page.

- [ ] **Step 3: Replace the template with semantic dashboard regions**

Use header, main dashboard, complementary chat aside, accessible tables/lists, a closeable detail dialog/drawer, loading/error regions with `aria-live`, and suggested-question buttons. Remove API-key and mutation controls from the public UI.

- [ ] **Step 4: Implement responsive visual hierarchy**

Desktop grid: `minmax(0, 7fr) minmax(22rem, 3fr)`. Use compact cards, risk chips with icon and text, progress bars with accessible labels, sticky chat composer, and a mobile breakpoint that stacks content and exposes chat through an accessible control. Honor reduced motion.

- [ ] **Step 5: Verify GREEN**

Run: `pytest services/agent-api/tests/ui/test_dashboard_layout.py services/agent-api/tests/ui/test_api_key_storage.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/agent-api/src/agent_api/web services/agent-api/src/agent_api/routes/ui.py services/agent-api/tests/ui
git commit -m "feat: redesign workforce manager dashboard"
```

### Task 5: Dashboard rendering, detail drawer, and session chat

**Files:**
- Replace: `services/agent-api/src/agent_api/web/static/chat.js`
- Test: `services/agent-api/tests/ui/test_dashboard_behavior.py`
- Modify: `services/agent-api/tests/ui/test_contextual_chat.py`

**Interfaces:**
- Consumes: DOM from Task 4 and APIs from Tasks 2–3.
- Produces: `loadProjects()`, `loadDashboard(projectKey)`, `renderDashboard(snapshot)`, `openDetail(kind, id)`, and `sendChat(question)`.

- [ ] **Step 1: Write failing static behavior tests**

Assert that JavaScript obtains projects from `/api/v1/projects`, uses `URLSearchParams`, passes the selected project to dashboard/chat calls, contains no hardcoded `project_key=WRD`, renders all snapshot regions, preserves messages in `sessionStorage` by project, supports suggested questions, creates safe Jira links, and performs no mutation request.

- [ ] **Step 2: Verify RED**

Run: `pytest services/agent-api/tests/ui/test_dashboard_behavior.py services/agent-api/tests/ui/test_contextual_chat.py -q`  
Expected: FAIL against the old script.

- [ ] **Step 3: Implement project state and atomic refresh**

Load configured projects, prefer the safe `?project=` value, otherwise choose the first project. Fetch one dashboard snapshot, render it only after validation, update the timestamp, and preserve the previous view with a degraded warning if refresh fails.

- [ ] **Step 4: Implement dashboard and drawer rendering**

Use DOM APIs and `textContent`, never untrusted `innerHTML`. Render summary cards, employee rows, alerts, progress, workload distribution, and task detail content. Link only validated keys to the configured Jira site.

- [ ] **Step 5: Implement project-wide chat**

Send:

```json
{
  "question": "Which tasks may miss their deadlines?",
  "context": {"project_key": "WFD"}
}
```

Render user and Bedrock messages, source, citations, missing-information notices, loading state, and fixed technical errors. Persist bounded message history in `sessionStorage` under `workforce-chat:<project>` and clear it when requested.

- [ ] **Step 6: Verify GREEN and accessibility**

Run: `pytest services/agent-api/tests/ui -q`  
Expected: PASS, including keyboard-accessible drawer and non-color-only status.

- [ ] **Step 7: Commit**

```bash
git add services/agent-api/src/agent_api/web/static/chat.js services/agent-api/tests/ui
git commit -m "feat: add project dashboard interactions"
```

### Task 6: Environment configuration and end-to-end validation

**Files:**
- Modify: `infra/kubernetes/overlays/dev/environment.yaml`
- Modify: `infra/kubernetes/overlays/prod/environment.yaml`
- Modify: `scripts/validation/smoke_dev.sh`
- Test: `tests/infrastructure/test_environment_config.py`
- Modify: `README.md`

**Interfaces:**
- Produces: dev deployment with WFD/WRD public reads and Jira writes disabled.

- [ ] **Step 1: Write failing configuration tests**

Assert dev explicitly contains the configured projects, anonymous read flag, mutation-off flag, Bedrock model configuration, and no credential value. Assert prod does not accidentally enable anonymous read.

- [ ] **Step 2: Verify RED**

Run: `pytest tests/infrastructure/test_environment_config.py -q`  
Expected: FAIL because the new settings are absent.

- [ ] **Step 3: Add safe environment configuration**

```yaml
ALLOW_ANONYMOUS_READ: "true"
ALLOW_JIRA_MUTATIONS: "false"
ALLOWED_JIRA_PROJECTS: "WFD:Workforce Real Data,WRD:Workforce Risk Demo"
```

Keep credentials in existing Kubernetes/AWS secret delivery. Document how to add a project without changing frontend code.

- [ ] **Step 4: Extend dev smoke checks**

Verify project listing, WFD dashboard load, WRD dashboard isolation, one WFD Bedrock response with `source=bedrock`, citations, no mutation control in HTML, and mutation endpoint rejection.

- [ ] **Step 5: Run complete verification**

```bash
pytest services/agent-api/tests -q
pytest tests/infrastructure/test_environment_config.py -q
ruff format --check services/agent-api tests/infrastructure
ruff check services/agent-api tests/infrastructure
mypy services/agent-api/src
```

Expected: all commands exit zero.

- [ ] **Step 6: Run locally**

```bash
docker compose up --build
```

Open `http://localhost:8000/?project=WFD`, verify the dashboard, ask a WFD question, inspect Jira links, switch to WRD, and confirm no Jira write action is available.

- [ ] **Step 7: Commit**

```bash
git add infra/kubernetes/overlays/dev/environment.yaml infra/kubernetes/overlays/prod/environment.yaml scripts/validation/smoke_dev.sh tests/infrastructure/test_environment_config.py README.md
git commit -m "chore: configure public workforce dashboard"
```
