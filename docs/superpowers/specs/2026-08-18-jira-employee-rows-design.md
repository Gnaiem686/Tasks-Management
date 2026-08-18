# Jira Employee Rows Design

The guarded `WRD` synthetic project will contain seven Jira work items that act
as display-only employee profile rows. Each row is derived from the existing
authoritative seven-person scenario profile and uses `workforce-profile:*`
labels, never the `workforce-employee:*` task-assignment label consumed by risk
analysis.

The existing MCP scenario reset/seed operation will search for each profile by
its stable external label, create it when absent, and update it when present.
Rows use the existing Jira `Task` type to avoid Jira administration changes.
Their summaries identify the employee, role, and seniority; their descriptions
and labels expose work-planning capacity, allocation, mentoring availability,
and documented skills. A fixed JQL URL filters `WRD` to these seven rows.

No Jira accounts are created, profile rows are never candidates for task
scoring, and no application API or deterministic score behavior changes.

