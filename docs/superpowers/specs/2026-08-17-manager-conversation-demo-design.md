# Manager conversation and demo reliability design

## Goal

Allow an authorized manager to ask natural work-management questions about a
selected employee, Jira task, project, or the whole managed workflow and
receive a correct, evidence-grounded conversational answer. Improve the Jira
simulation so its stages complete reliably and visibly demonstrate changing
risk.

## Boundaries

Questions are limited to authorized Jira sites and projects, workforce-planning
data, reports, risk, and read-only operational evidence. Chat remains advisory.
It cannot approve or execute reassignment or another external mutation. The
existing structured proposal and approval workflow remains the only Jira-write
path.

## Selected approach

Use a hybrid constrained LangGraph supervisor. After Agent API authentication
and project authorization, Bedrock maps natural language to a typed, read-only
query plan. Deterministic code validates its scope, context, operation, tool
allowlist, and limits before any specialist agent calls an MCP tool.

The plan supports employee, task, project, workflow, comparison, history,
simulation, and read-only operations contexts. When phrasing is ambiguous, the
selected UI context supplies the safe default investigation scope. Explicit
mutation language remains rejected from chat.

## Evidence and answer flow

The Workforce Analysis, Project Delivery, Reassignment Planning, or Operations
Diagnostic Agent gathers structured evidence through allowlisted Jira,
Workforce Risk, or DevOps MCP tools. Workforce Risk MCP remains authoritative
for deterministic scores, findings, candidate selection, and proposal state.

Bedrock receives only validated, minimal work evidence. Its final response uses
a validated internal envelope containing a free-form natural-language answer,
citations, and the final score and risk level needed for consistency checks.
The UI displays the natural answer directly rather than forcing contributors
and recommendations into a rigid template. Missing optional presentation
sections do not cause fallback.

The validator rejects changes to deterministic scores or risk levels, unknown
entities or citations, invented candidates, claims of blocked or overdue work
that contradict structured counts, and claims of improvement without
comparable snapshots. Bedrock failure or a material contradiction produces an
accurate, visibly labelled deterministic fallback.

## Manager UI

Provide one simple manager workspace with:

- a context selector for whole workflow, employee, or Jira task;
- conversational chat with safe context-reference memory;
- a visible `Amazon Bedrock` or `Deterministic fallback` source indicator;
- final aggregate score such as `88/100`, risk grade, confidence, freshness,
  natural explanation, citations, and suggested follow-up questions;
- secondary alert, report, proposal/approval, audit, and demo-stage panels.

The UI hides normalized factor values, factor weights, contribution points,
thresholds, and intermediate calculations. These remain persisted for audit,
testing, reproducibility, and write safety. The four risk grades remain Low,
Medium, High, and Critical.

## Demo simulation

The laptop-controlled script verifies Jira credentials, Agent API access,
required MCP tools, and the target environment. It reports whether the target
is local or AWS and checks the deployed Bedrock configuration rather than only
the laptop environment.

It resets the WRD synthetic project to balanced, then advances through stalled,
blocked, critical, intervention, and recovery. After each stage it waits for a
completed scan, prints the three moving employees' risk grades, and provides
the Jira and manager URLs. It must print a safe failure reason and correlation
ID instead of silently exiting. Interrupting it preserves the last completed
stage.

Balanced and recovery resolve active alerts. Critical produces meaningful
active alerts for EMP-001, EMP-002, and EMP-006. Jira remains the visible,
external synthetic task-management field for the demonstration.

## Failure behavior

- Bedrock unavailable: visibly labelled deterministic fallback.
- Bedrock presentation differs but facts remain valid: return its natural
  answer.
- Bedrock contradicts protected facts: reject it and return fallback.
- Jira evidence unavailable: identify the missing source and reduce confidence.
- Scan failure: expose a safe failure code and correlation ID.
- Stale evidence: warn and offer refresh.
- Insufficient mandatory evidence: do not guess or create proposals.
- Chat mutation request: direct the manager to structured proposal controls.

The governing rule remains `read degraded; write closed`.

## Verification

Tests cover all approved example questions and paraphrases across employee,
task, project, workflow, comparison, history, and operational contexts. They
also cover follow-ups, authorization, mutation refusal, missing and stale
evidence, natural Bedrock prose, protected-fact contradictions, fallback source
labelling, aggregate-score presentation, and hidden intermediate calculations.

The separate-process MCP integration test remains mandatory. Live acceptance
requires the six-stage Jira simulation to complete, three employees to reach
meaningful critical risk, recovery to resolve alerts, the AWS UI to answer
employee and workflow questions, and the API to expose the actual explanation
source. Deployment smoke tests must pass before success is reported.
