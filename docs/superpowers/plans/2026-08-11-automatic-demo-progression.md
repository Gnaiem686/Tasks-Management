# Automatic Demo Progression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe laptop command that advances the guarded synthetic `WRD` Jira scenario through deterministic stages on a configurable timer.

**Architecture:** Reuse the existing fixture, MCP seeder, and verifier. Add explicit stage-aware verification, versioned progression steps, and one shell orchestrator; do not add services or deployment resources.

**Tech Stack:** Bash, Python 3.12, pytest, Atlassian MCP Streamable HTTP.

## Global Constraints

- Operate only against environment `dev` and Jira project `WRD`.
- Mutate only scenario-owned synthetic issues through existing MCP tools.
- Stop on update or verification failure; never retry ambiguous Jira writes.
- Keep AWS, scoring, and Bedrock behavior unchanged.

---

### Task 1: Make live verification stage-aware

**Files:**
- Modify: `scripts/jira/cli.py`
- Modify: `scripts/jira/verify_seed.py`
- Modify: `scripts/demo/reset.sh`
- Modify: `scripts/demo/primary.sh`
- Test: `tests/integration/test_synthetic_seed.py`

**Interfaces:**
- Consumes: `scenario_at_step(scenario, step_name)`.
- Produces: `verify_seed.py --step <name>`; omission continues to verify the base fixture.

- [ ] Add a failing integration test proving `verify_seed.py --step primary_demo` compares against the advanced fixture.
- [ ] Run `uv run pytest tests/integration/test_synthetic_seed.py -q` and confirm failure because `--step` is unsupported.
- [ ] Add optional `--step` parsing for verification; apply `scenario_at_step` before live and offline verification when supplied.
- [ ] Pass `--step balanced` from `reset.sh` and `--step primary_demo` from `primary.sh`.
- [ ] Re-run the focused tests and expect all to pass.
- [ ] Commit with `fix: verify explicit jira scenario stages`.

### Task 2: Add deterministic timed progression

**Files:**
- Modify: `tests/fixtures/scenarios/seven_employee_team.json`
- Create: `scripts/demo/auto_demo.sh`
- Modify: `tests/e2e/test_demo_scripts.py`

**Interfaces:**
- Consumes: `advance_scenario.py --step NAME` and `verify_seed.py --step NAME`.
- Produces: `DEMO_STAGE_SECONDS=60 bash scripts/demo/auto_demo.sh`; stages `balanced`, `stalled`, `blocked`, `critical`, `intervention`, `recovery`.

- [ ] Write failing tests asserting the six ordered stages, configurable non-negative delay, readiness check, stage verification, `set -euo pipefail`, and an interrupt trap.
- [ ] Run `uv run pytest tests/e2e/test_demo_scripts.py tests/integration/test_synthetic_seed.py -q` and confirm failure because the runner/stages do not exist.
- [ ] Add fixture steps with deterministic remaining-hours, blocker, due-date, pairing, and recovery updates; do not use randomness.
- [ ] Implement `auto_demo.sh` to call readiness once, reset, update and verify each stage, print URLs, sleep between stages, and exit cleanly on `INT`/`TERM` while retaining the last completed Jira state.
- [ ] Run the focused tests and `bash -n scripts/demo/auto_demo.sh`; expect success.
- [ ] Run an offline zero-delay rehearsal of stage definitions without credentials; expect all stages to validate in order.
- [ ] Commit with `feat: add automatic jira demo progression`.

### Task 3: Final verification and usage handoff

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: `scripts/demo/auto_demo.sh`.
- Produces: exact start, stop, reset, fast-demo, Jira, and AWS UI instructions.

- [ ] Document required environment variables, default 60-second execution, `DEMO_STAGE_SECONDS=5` fast mode, `Ctrl+C`, and reset behavior.
- [ ] Run `uv run pytest tests/e2e/test_demo_scripts.py tests/integration/test_synthetic_seed.py -q` and `git diff --check`; expect success.
- [ ] Run `DEMO_STAGE_SECONDS=0 bash scripts/demo/auto_demo.sh` only when live Jira credentials are present; verify every stage succeeds and no non-`WRD` issue is touched.
- [ ] Commit with `docs: explain automatic jira demo`.
