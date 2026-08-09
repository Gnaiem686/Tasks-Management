# Uncertain Jira reassignment

1. Stop further action for the proposal; `uncertain` is a blocking state.
2. Locate the proposal by protected correlation logs, not metric labels.
3. Read the issue from Jira and compare its assignee with expected and proposed IDs.
4. Let reconciliation persist `executed_verified` only for an exact match.
5. Escalate ambiguous evidence to an authorized manager for manual review.
6. Never automatically retry the mutation or overwrite another Jira change.
