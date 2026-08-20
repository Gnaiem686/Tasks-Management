# Manager Dashboard and Bedrock Chat Redesign

Date: 2026-08-20  
Status: Approved design

## Purpose

Replace the current long, single-column manager page with a project-wide workforce dashboard and a persistent Amazon Bedrock chat panel. A manager must be able to see the important delivery situation at a glance and ask natural-language questions about any employee, task, alert, deadline, blocker, dependency, skill fit, or project condition.

The redesign remains generic across configured Jira projects. It initially supports `WFD` and `WRD` without hardcoding either project into frontend behavior.

## Selected approach

Use a responsive application shell with approximately 70% of desktop width assigned to the dashboard and 30% to a persistent right-side chat. This most closely matches the approved reference while allowing managers to compare Bedrock answers with visible project evidence.

Plain HTML, CSS, and JavaScript remain sufficient. React and Cognito are not introduced.

## Public-demo boundary

The current demonstration is anonymously readable:

- no login or browser API-key field;
- no credential embedded in HTML or JavaScript;
- Jira, Bedrock, database, and AWS credentials remain backend-only;
- only backend-configured Jira projects are visible;
- all real Jira mutations are disabled.

The governing configuration is equivalent to:

```text
ALLOW_ANONYMOUS_READ=true
ALLOW_JIRA_MUTATIONS=false
ALLOWED_JIRA_PROJECTS=WFD,WRD
```

Anonymous users may load dashboards, inspect employees and tasks, refresh evidence, ask Bedrock questions, view business alerts and reports, and run read-only what-if simulations. They may not change Jira assignments, edit tasks, administer profiles or scoring rules, access unrestricted audit data, or perform operational actions.

## Application shell

### Header

The header contains:

- Workforce Risk Manager branding;
- a project selector populated from the backend-configured allowlist;
- the evidence timestamp;
- a `Refresh data` action;
- visible stale or degraded-data warnings.

The selected project is reflected in a bookmarkable URL such as `/?project=WFD`. The URL does not grant access: the API independently validates the project against its allowlist.

### Dashboard

The main dashboard contains:

1. Summary cards for high-risk employees, at-risk tasks, project completion, and workload balance.
2. A team-risk overview showing employee name and role, one deterministic `88/100`-style score, risk level, assigned remaining hours versus capacity, and the primary risk reason.
3. A risk-alert feed showing the affected employee or task, severity, concrete reason, timestamp, and recurrence.
4. A project/task overview showing workflow distribution and counts for overdue, due-soon, blocked, review-waiting, and missing-estimate tasks.
5. A workload-distribution view showing overloaded, balanced, and underutilized capacity.
6. Secondary report and audit views that do not dominate the primary dashboard.

### Detail drawer

Selecting an employee, task, or alert opens a detail drawer without restricting the chat context.

Employee details include role, seniority, skills, capacity, assigned remaining work, urgent tasks, the current risk result, a concrete explanation, risk history, and Jira links.

Task details include key, summary, status, assignee, priority, deadline, original and remaining estimate, required skills, employee fit, blockers, dependencies, activity, missing evidence, findings, and a Jira link.

Alert details include why the alert exists, affected subjects, first detection, latest occurrence, evidence timestamp, recommended actions, and recurrence history.

### Responsive behavior

Desktop keeps dashboard and chat side by side. Tablet narrows the chat panel. Mobile presents the dashboard first and exposes chat through a persistent accessible control. All interactions remain keyboard accessible and screen-reader friendly, and status is never communicated by color alone.

## Project and data model

The backend owns project configuration and authorization. The frontend receives only safe project metadata:

```yaml
projects:
  - key: WFD
    name: Workforce Real Data
    enabled: true
    mutation_enabled: false
  - key: WRD
    name: Workforce Risk Demo
    enabled: true
    mutation_enabled: false
```

The proposed read APIs are:

```text
GET  /api/v1/projects
GET  /api/v1/dashboard?project_key=WFD
GET  /api/v1/employees?project_key=WFD
GET  /api/v1/tasks?project_key=WFD
POST /api/v1/investigations?project_key=WFD
```

The dashboard endpoint returns one typed snapshot containing its timestamp and correlation ID, project summary, workflow progress, employee risks, task risks, alerts, workload distribution, evidence completeness, and missing sources. Every component renders from the same snapshot.

Jira supplies structured work facts: assignee, workflow state, priority, deadline, estimates, dependencies, labels, and activity. The Workforce Risk service supplies authoritative employee profiles, capacity, skills, seniority, allocation, account mapping, deterministic risk results, findings, and history. Employee profiles are not represented as Jira task rows.

Selecting a project or pressing `Refresh data` retrieves a fresh snapshot. Partial results identify missing sources. Stale data is visibly timestamped. The rule remains `read degraded; write closed`.

## Project-wide Bedrock chat

Chat always uses the complete selected project as its scope. Clicking a dashboard item does not limit chat context. Managers refer to employees and tasks naturally in their questions.

Conversation history exists only in the current browser session. The browser stores compact message and entity references, not raw evidence bundles, hidden prompts, credentials, or tokens.

The question flow is:

```text
manager question
→ constrained intent and entity resolution within the selected project
→ Jira MCP structured evidence retrieval
→ Workforce Risk MCP profile, risk, candidate, and history retrieval
→ deterministic evidence packet
→ single configured Amazon Bedrock model
→ evidence and citation validation
→ natural-language answer and Jira links
```

Every successful visible conversational answer is produced by the single configured Bedrock model. There is no deterministic prose fallback and no secondary model. Deterministic services remain responsible for numeric scores, evidence selection, entity resolution, candidate selection, and factual calculations.

Bedrock may answer naturally with paragraphs, lists, task summaries, uncertainty, and recommended next steps. It is not forced into the previous Contributors/Recommendations template. Answers must use concrete task facts—names, keys, deadlines, remaining hours, priorities, blockers, dependencies, and capacity—rather than only abstract factor names.

Bedrock must not invent employees, tasks, dates, estimates, dependencies, scores, or reassignment candidates. It receives explicit missing-data information and may state that it lacks enough information, that a field is absent, that a name is ambiguous, or that historical evidence is unavailable. If Bedrock itself fails technically, the API returns a short fixed availability notice stating that no AI answer was generated; this notice is not represented as a Bedrock answer.

Each task claim carries a validated Jira citation. Historical answers cite immutable snapshots, state the relevant date, and distinguish historical evidence from current Jira state.

## Project and what-if analysis

Project analysis includes workflow completion, elapsed-time comparison when sprint dates exist, remaining work versus team capacity, workload concentration, blocked and overdue tasks, review delays, missing estimates, and evidence completeness.

What-if simulation is available from task and employee details. It compares current and proposed assignments using the same deterministic scoring version and shows the approved employee/project scores, risk levels, workload impact, skill fit, deadlines, and dependencies. In the public demo it cannot execute a Jira write.

## Failure behavior

- Jira unavailable: show which dashboard data could not be refreshed.
- Workforce Risk MCP unavailable: structured Jira facts may be shown, but no risk result is claimed.
- Bedrock unavailable: state that the AI assistant is temporarily unavailable and that no answer was generated.
- Missing evidence: Bedrock describes the missing information when a response can still be generated safely.
- Stale evidence: display the timestamp and a prominent warning.
- Unknown or ambiguous entity: request a more specific name or key.
- Project outside the allowlist: return a safe `403`.
- Rate limit reached: show a retry-later response.
- Jira mutation request: reject it while public-demo mode is active.

Public endpoints have bounded request sizes and rate limits. Jira descriptions, comments, and other external content remain untrusted evidence and cannot change system instructions, select tools, or expose hidden prompts.

## Testing

Frontend tests cover responsive dashboard/chat layout, removal of browser credentials, project selector and URL synchronization, whole-snapshot refresh, detail drawers, project-wide session chat, accessibility, stale/degraded/missing-data states, and hidden or disabled mutation controls.

API and domain tests cover project allowlisting, unknown-project rejection, snapshot consistency, `WFD`/`WRD` isolation, Jira/profile mapping, entity resolution, detailed evidence packets, Bedrock-only successful answers, absence of deterministic prose fallback, honest Bedrock failure, missing evidence, citation validation, prompt-injection resistance, rate limiting, and mutation rejection.

The mandatory acceptance scenario is:

1. Open the public AWS URL without entering a key.
2. Select `WFD` from the configured project list.
3. View current project, employee, task, workload, and alert information.
4. Ask Bedrock a detailed question about any employee, task, or the complete workflow.
5. Receive a natural, concrete, evidence-backed response.
6. Open cited work items in Jira.
7. Confirm that no Jira mutation control is available in public-demo mode.

## Deferred hardening

Authentication, private access, per-user authorization, persistent conversation history, and enabling approval-controlled Jira mutations are deferred. Reintroducing mutations requires verified manager identity and the existing structured proposal, freshness, idempotency, audit, saga execution, and read-back controls; chat text can never constitute approval.
