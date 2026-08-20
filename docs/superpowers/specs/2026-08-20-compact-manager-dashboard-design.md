# Compact Manager Dashboard Design

## Goal

Make the manager UI match the approved reference: a compact, colored, one-screen workforce dashboard with a persistent Bedrock chat panel.

## Layout

- Desktop uses a 70/30 split between dashboard and chat.
- The dashboard fits the primary information within one viewport: four summary cards, a five-row team-risk overview, four risk alerts, compact project progress, and a workload distribution chart.
- Longer employee, alert, project, and task collections use **View all** drawers rather than extending the main page.
- Green represents healthy conditions, orange represents warnings, and red represents high or critical risk.
- The chat panel remains fixed, scrolls internally, and keeps its composer visible.

## Chat behavior

- Manager questions use the selected project as implicit context.
- Broad questions such as “Which employees are at risk and why?” fall back to the project evidence snapshot when no narrower deterministic query applies.
- Successful messages display Bedrock's natural-language answer without forcing headings or exposing raw evidence identifiers.
- Validated Jira citations remain internal. When useful, the UI may show friendly task links containing a Jira key and summary, never strings such as `jira:WFD-13:summary`.
- Missing evidence is explained naturally by Bedrock. Internal failures display a short friendly availability message and correlation reference, not raw service details.

## Data and safety

- Existing Jira MCP evidence, deterministic scores, access boundaries, and read-only project configuration remain unchanged.
- Bedrock receives the validated project snapshot and cannot create scores, candidates, approvals, or mutations.
- The redesign changes presentation and question routing only.

## Verification

- UI tests assert compact regions, row limits, view-all controls, responsive layout, and risk colors.
- Chat tests assert raw citations are hidden and Bedrock prose is preserved.
- A workflow regression test proves “Which employees are at risk and why?” gathers project evidence and returns a Bedrock answer rather than HTTP 503.
- Existing lint, typing, unit, security, and deployment smoke checks must pass before deployment.
