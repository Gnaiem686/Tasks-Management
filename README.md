# Workforce Risk Agent

An explainable workforce and project-delivery risk agent that reads synthetic
work-planning evidence from Jira through Atlassian Rovo MCP. The authoritative
architecture and executable sequence are in `docs/spec.md` and `docs/plan.md`.

## Local prerequisites

- Python 3.12 (the exact patch remains subject to the deferred version matrix)
- `uv`
- GNU Make
- Docker Engine with the Compose and Buildx plugins

Bootstrap and verify the repository:

```bash
make bootstrap
make check
```

No real credentials are required for unit tests. Unit tests must not access the
network and must mock Jira, Bedrock, AWS, Kubernetes, Prometheus, Loki, GitHub,
and persistence boundaries as appropriate.

## Complete local stack

The local stack uses synthetic evidence and disables Jira mutation. It runs the
Agent API and embedded manager UI, both custom MCP servers, the notification
worker, PostgreSQL, and LocalStack:

```bash
docker compose build
docker compose up -d --wait
docker compose ps
```

Open `http://127.0.0.1:8000`. Stop the stack without deleting PostgreSQL data
with `docker compose down`; add `--volumes` only when intentionally resetting
the local database.

## Automatic Jira demo

After exporting `ATLASSIAN_MCP_AUTHORIZATION`, `DEV_MANAGER_API_KEY`, and the
AWS `AGENT_DEV_URL`, run the deterministic laptop simulation:

```bash
bash scripts/demo/auto_demo.sh
```

The default delay is 60 seconds per simulated day. For a quick rehearsal:

```bash
DEMO_STAGE_SECONDS=5 bash scripts/demo/auto_demo.sh
```

Refresh Jira and the manager UI after each printed stage. Stop safely with
`Ctrl+C`; Jira retains the last completed stage. Restore the deterministic
starting point with `bash scripts/demo/reset.sh`.

## Validation status

The stakeholder authorized Phase 1 to begin under the documented Phase 0
deviation. Deferred technical validations remain dependency and production
gates; see `docs/validations/phase-0-deviation.md`.
