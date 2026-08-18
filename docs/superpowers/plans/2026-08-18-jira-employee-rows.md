# Jira Employee Rows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the seven synthetic employees as stable rows in the existing `WRD` Jira project.

**Architecture:** Extend the existing MCP-only scenario seeder to upsert display-only profile work items derived from `ScenarioProfile`. Keep their labels separate from task-assignment labels so scoring behavior is unchanged.

**Tech Stack:** Python 3.12, Pydantic, Atlassian Rovo MCP Streamable HTTP, pytest.

## Global Constraints

- Use only the guarded synthetic `WRD` project.
- Do not create Jira users or use Jira REST.
- Employee profile rows must never enter deterministic task scoring.
- Writes must remain idempotent and MCP-only.

---

### Task 1: Upsert display-only employee profile rows

**Files:**
- Modify: `scripts/jira/mcp_scenario.py`
- Modify: `tests/integration/test_synthetic_seed.py`
- Modify: `scripts/demo/reset.sh`

**Interfaces:**
- Consumes: `ScenarioDefinition.profiles` and `ScenarioMcpTransport.call_tool`.
- Produces: seven idempotent Jira rows carrying `workforce-record:employee-profile` and `workforce-profile-id:<ID>` labels.

- [ ] Write a failing transport test asserting seven profile rows, stable labels, and absence of task-assignment labels.
- [ ] Run the focused test and confirm it fails because profile rows are not yet created.
- [ ] Add the smallest profile upsert loop to `RovoScenarioSeeder.seed`.
- [ ] Add the profile-only JQL URL to reset output.
- [ ] Run focused tests, formatting, lint, and typing.
- [ ] Seed live `WRD`, verify exactly seven profile rows, and open the profile filter URL.
- [ ] Commit, push, merge to `dev`, and deploy through the existing workflow.

