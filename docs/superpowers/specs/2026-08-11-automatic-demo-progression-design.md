# Automatic Demo Progression Design

## Goal

Provide a deterministic, accelerated workforce demo that runs from the presenter's laptop and updates only the guarded synthetic `WRD` Jira project through the existing Atlassian MCP integration. The deployed AWS agent remains independent and observes the resulting Jira state through MCP.

## Workflow

`scripts/demo/auto_demo.sh` resets the fixture and advances through fixed stages: balanced, stalled, blocked, critical risk, intervention, and recovery. One configurable delay represents one simulated day; the default is 60 seconds. The script prints the current stage and the Jira and manager-UI links after every successful update.

The process can be stopped safely with `Ctrl+C`. Jira retains the last completed stage. A later run starts from a clean deterministic reset by default, and `scripts/demo/reset.sh` remains the explicit reset command. No background service, Kubernetes workload, AWS scheduler, or random data is introduced.

## Safety and boundaries

- Refuse production and any Jira project other than `WRD`.
- Require the existing Jira MCP authorization before starting.
- Use only existing synthetic scenario records and MCP mutation tools.
- Stop immediately when a stage update or verification fails.
- Never retry an ambiguous Jira mutation automatically.
- Keep deterministic scoring and Bedrock behavior unchanged.

## Verification correction

The current verifier compares an advanced Jira stage with the base fixture. Verification will accept an explicit stage and compare Jira against the fixture after that stage is applied. Reset verifies `balanced`; the primary demo verifies `primary_demo`.

## Tests and acceptance

Focused tests verify stage order, configurable delay, interruption behavior, project/environment refusal, explicit-stage verification, and failure-stop behavior. Acceptance requires a short-delay local run to update Jira through at least two stages, while the AWS manager UI can be refreshed to observe the changed deterministic risk and Bedrock explanation.
