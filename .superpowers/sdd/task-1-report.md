# Task 1 Report

## Summary

Implemented the project-evidence fallback in `InvestigationWorkflow` so broad workforce questions can recover from unsupported narrow Jira task-query parsing and still produce a Bedrock-backed project answer.

## TDD Cycle

1. Added a new regression test in `services/agent-api/tests/test_project_chat.py`:
   - `test_broad_workforce_question_falls_back_to_project_snapshot`
   - Forces the workflow into the `JIRA_TASK_QUERY` branch for the question `"Which employees are at risk and why?"`
   - Simulates the narrow parser failure with `ValueError("employee is required for a deadline task query")`
   - Asserts the workflow falls back to project evidence and returns a Bedrock-source explanation
2. Ran the focused test file before the fix:
   - Command: `.venv/bin/pytest -q services/agent-api/tests/test_project_chat.py`
   - Result: `1 failed, 5 passed`
   - Failure: the `ValueError("employee is required for a deadline task query")` escaped from the `gather` node
3. Implemented the minimal workflow change in `services/agent-api/src/agent_api/graph/workflow.py`:
   - Catch only specific unsupported narrow-query `ValueError` messages
   - Re-raise all other `ValueError` cases unchanged
   - Spend the second tool call on `project_tool.build(...)`
   - Switch the resolved intent to `Intent.EXPLAIN_PROJECT_RISK`
4. Re-ran the focused test file after the fix:
   - Command: `.venv/bin/pytest -q services/agent-api/tests/test_project_chat.py`
   - Result: `6 passed`

## Files Changed

- `services/agent-api/src/agent_api/graph/workflow.py`
- `services/agent-api/tests/test_project_chat.py`

## Notes

- The fallback is intentionally narrow so authorization, transport, and explicit invalid-scope query failures still surface instead of being masked by project chat.
- No unrelated files were modified.

## Follow-up: deployed classification root cause

- Production debugging showed the original regression test was too artificial: the workflow was never reaching the Jira task-query branch for `"Which employees are at risk and why?"`.
- Real root cause: `classify_intent(..., default_scope="project")` matched the substring `"which employee"` inside `"which employees"` and returned `Intent.REASSIGNMENT_CANDIDATES` before the project-scope fallback could route the question to project risk.

### Follow-up TDD cycle

1. Added failing tests for the real production path:
   - `test_project_scope_routes_broad_workforce_risk_question_to_project_risk`
   - `test_broad_workforce_question_sends_project_snapshot_to_bedrock`
   - Preserved candidate coverage with `"Which employee could take WRD-8?"`
2. Ran:
   - `.venv/bin/pytest -q services/agent-api/tests/test_graph_workflows.py services/agent-api/tests/test_project_chat.py`
   - Observed failures showing:
     - `"Which employees are at risk and why?"` classified as `REASSIGNMENT_CANDIDATES`
     - workflow attempted the core investigation path instead of project chat
3. Implemented the minimal classifier fix:
   - narrowed reassignment detection from a loose substring match to bounded candidate phrasing:
     - `"candidate"`
     - `"could take"`
     - regex `\\bwhich employee\\b`
4. Re-ran the same focused suite:
   - Result: `33 passed`

### Follow-up files changed

- `services/agent-api/src/agent_api/graph/intents.py`
- `services/agent-api/tests/test_graph_workflows.py`
- `services/agent-api/tests/test_project_chat.py`
