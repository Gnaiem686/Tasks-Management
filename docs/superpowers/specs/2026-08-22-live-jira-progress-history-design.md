# Live Jira Progress History Design

## Purpose

Track the four current WFD Jira assignees using recorded Jira work evidence rather than synthetic progress. Jira remains authoritative for current task state; PostgreSQL preserves immutable observations and derived changes. The system never decreases remaining work because time elapsed and never claims that a person did or did not work.

## Selected design

- Workforce profiles are dynamic and use stable internal IDs linked to Jira account IDs. There is no fixed employee count.
- Existing API-key authentication, roles, project scopes, and internal MCP authorization remain unchanged. Profile APIs stay admin-only and are not exposed in the read-only manager UI.
- WFD is scanned every 30 minutes and on dashboard/agent refresh. Identical observations update `last_observed_at` without creating duplicate detailed snapshots.
- Each Monday-Friday planning week uses 09:00-17:00 Asia/Jerusalem. Weekly capacity, allocation, and overrides remain authoritative profile inputs; remaining capacity is derived for the active window.
- A scan stores current task state, immutable change-only snapshots, and normalized progress events. Weekly baseline observations are preserved when tasks cross planning weeks.
- Structured progress is a remaining-estimate decrease, increased time spent, a forward status transition, or completion. Blocker, estimate, deadline, dependency, and assignee changes are delivery changes. Attributable comments are report-only and never affect scoring.
- Staleness counts scheduled working hours and is phrased as "no recorded Jira progress". It changes risk only together with deadline, remaining-work, priority, or blocker evidence.
- The manager UI shows current state only. Historical evidence remains available to Bedrock and weekly reporting but is not exposed as an editing or administration surface.
- The Jira mutation workflow remains isolated from the manager UI.

## Failure behavior

Validated observations are staged before replacing current project evidence. Partial or invalid Jira reads retain the last valid current state and expose freshness/degraded status. Missing profiles, mappings, estimates, worklogs, or history produce explicit missing evidence and never crash analysis.

## Local acceptance

- A Jira remaining-estimate change appears after refresh and affects the current risk calculation.
- The previous estimate remains queryable from PostgreSQL history.
- Repeating the same Jira observation does not add a duplicate snapshot/event.
- Worklog, status, blocker, due-date, assignee, and estimate changes produce typed events when evidence is available.
- The manager UI remains read-only and runs locally at `http://127.0.0.1:8000/?project=WFD`.
