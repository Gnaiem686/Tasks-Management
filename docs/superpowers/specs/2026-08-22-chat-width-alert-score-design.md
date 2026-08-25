# Chat Width and Alert Score Design

## Goal

Make the desktop Bedrock chat panel approximately 40% of the viewport and replace placeholder alert scores with the same deterministic employee scores shown in the team table.

## Selected design

- Use a 3:2 desktop dashboard/chat grid, allocating approximately 60% to the dashboard and 40% to chat. Existing responsive breakpoints remain unchanged.
- Add `score: int` to `AlertSummary` and populate it from the employee risk result that created the alert.
- Render the alert score from structured API data in both the preview and View all drawer.
- Never calculate or invent an alert score in JavaScript.
- Keep the manager interface read-only.

## Verification

- Layout test asserts the 3:2 desktop grid.
- Dashboard service test asserts an alert carries the employee's deterministic score.
- UI runtime test asserts alert preview and drawer display the numeric score and never `!/100`.
- Restart and verify locally at `http://127.0.0.1:8000/?project=WFD`.
