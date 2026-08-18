# Current and Historical Risk Explanations Design

## Problem and outcome

Current Bedrock answers receive deterministic scores and factor names but not enough structured Jira context to explain the real work situation. Managers need answers that name the relevant tasks, dates, remaining work, priorities, blockers, dependencies, capacity, and changes over time. Every factual claim must be verifiable in Jira or an immutable historical snapshot.

## Selected approach

The Agent API will build a typed risk-evidence dossier before requesting an explanation. Current questions use refreshed structured Jira evidence for all active unfinished tasks belonging to the selected employee. Historical questions use the immutable risk snapshot closest to the requested time. Change-over-time questions compare two snapshots.

The deterministic score and its three score families remain unchanged. Bedrock explains supplied facts and recommendations; it does not calculate or alter scores. MCP servers remain tools, not agents.

## Current evidence dossier

For each active unfinished task, the dossier contains only allowlisted structured work-planning facts:

- Jira key and summary;
- status and priority;
- due date and remaining estimate;
- structured blocker category;
- blocking and dependent issue references;
- last activity timestamp;
- evidence timestamp and field-level references.

The dossier also contains authoritative employee capacity and deterministic aggregates: active task count, total remaining hours, available hours, overdue tasks, due-soon tasks, blocked tasks, and missing evidence. Jira descriptions and comments remain untrusted, report-only evidence and cannot affect scoring, confidence, candidate selection, or proposal evidence.

Jira queries are restricted to the configured project, exclude employee-profile records, paginate until complete, and fail as incomplete rather than returning a silently truncated answer.

## Historical evidence and comparison

Every persisted risk snapshot retains the exact structured task facts and aggregates used at that time, its evidence fingerprint, timestamp, confidence, missing evidence, and scoring-model version. Historical snapshots are immutable even if Jira tasks later change or disappear.

A historical answer must state the snapshot time. If no suitable snapshot exists, the agent reports that historical evidence is unavailable and must not substitute current Jira state. A comparison answer describes factual changes between two snapshots, such as work completed, new or removed blockers, changed deadlines, and changed remaining workload.

## Explanation flow

```text
Manager question
-> authenticated Agent API context
-> constrained current, historical, or comparison intent
-> deterministic risk result
-> Jira MCP refresh or immutable snapshot lookup
-> typed risk-evidence dossier and deterministic aggregates
-> Bedrock natural-language explanation
-> output validation and citation checking
-> Manager UI answer with Jira-verification references
```

Answers should lead with the situation and urgency, then explain exact tasks and management actions. A representative historical comparison is:

> On August 18, Employee 3 had high risk because they had 72 remaining hours against 40 available hours. WRD-4 was overdue, WRD-6 was blocked pending review, and WRD-7 depended on WRD-6. By August 20, WRD-6 was unblocked and 24 hours of work were completed, reducing the risk.

The displayed numbers and issue statements must come from the dossier; this example is not a hard-coded answer.

## Safety and failure behavior

- Bedrock cannot introduce unknown tasks, dates, hours, blockers, dependencies, scores, or citations.
- Output validation rejects unsupported factual claims and preserves the existing bounded retry and circuit-breaker behavior.
- The deterministic fallback produces concrete dossier-based prose when Bedrock is unavailable.
- Missing or stale evidence is stated explicitly.
- Jira read failures may produce a clearly degraded current explanation only when confidence rules permit; historical snapshots remain readable.
- The governing rule remains `read degraded; write closed`.

## Testing and acceptance

Tests will cover current explanations, historical explanations, snapshot comparison, missing snapshots, incomplete evidence, Jira timeout and pagination, employee-profile exclusion, project-scope enforcement, unsupported Bedrock claims, citation validation, and dossier-based deterministic fallback.

Acceptance requires the Manager UI to answer current and historical risk questions with concrete task keys, dates, remaining work, priorities, blockers, dependencies, capacity context, and evidence references. A reviewer must be able to open the cited Jira tasks and verify each current fact step by step.
