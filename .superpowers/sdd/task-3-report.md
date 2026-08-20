# Task 3 Report

## Summary

Implemented the Bedrock chat presentation cleanup so project answers now render only natural assistant prose, never expose raw Jira citation identifiers in the visible message, and convert investigation 503 failures into friendly availability copy with correlation context when present.

## TDD Cycle

1. Added failing runtime-oriented UI coverage in:
   - `services/agent-api/tests/ui/test_contextual_chat.py`
   - `services/agent-api/tests/ui/test_operation_status.py`
2. Ran the focused task tests before the production fix:
   - Command: `/home/gnaiem/Tasks-Management/.worktrees/cicd-dev-promotion/.venv/bin/python -m pytest /home/gnaiem/Tasks-Management/.worktrees/cicd-dev-promotion/services/agent-api/tests/ui/test_contextual_chat.py /home/gnaiem/Tasks-Management/.worktrees/cicd-dev-promotion/services/agent-api/tests/ui/test_operation_status.py`
   - Result: `2 failed, 3 passed`
   - Failures proved the UI still appended `Evidence: jira:...` to Bedrock answers and surfaced a raw object-shaped 503 failure instead of natural assistant availability copy
3. Implemented the minimal production change in `services/agent-api/src/agent_api/web/static/chat.js`:
   - preserved only `payload.explanation.answer` for Bedrock responses
   - removed the raw citation suffix from visible assistant messages
   - captured HTTP status and correlation metadata on fetch failures
   - mapped 503 investigation failures to friendly assistant availability copy with correlation when available
4. Re-ran the focused task tests after the fix:
   - Command: `/home/gnaiem/Tasks-Management/.worktrees/cicd-dev-promotion/.venv/bin/python -m pytest /home/gnaiem/Tasks-Management/.worktrees/cicd-dev-promotion/services/agent-api/tests/ui/test_contextual_chat.py /home/gnaiem/Tasks-Management/.worktrees/cicd-dev-promotion/services/agent-api/tests/ui/test_operation_status.py`
   - Result: `5 passed`

## Files Changed

- `services/agent-api/src/agent_api/web/static/chat.js`
- `services/agent-api/tests/ui/test_contextual_chat.py`
- `services/agent-api/tests/ui/test_operation_status.py`

## Notes

- The chat UI still requires `source == "bedrock"` and now also requires a non-empty Bedrock `answer` before rendering assistant prose.
- Correlation text is only shown for temporary availability failures when the API provides a correlation identifier.
