# Workforce Risk Agent

An explainable workforce and project-delivery risk agent that reads synthetic
work-planning evidence from Jira through Atlassian Rovo MCP. The authoritative
architecture and executable sequence are in `docs/spec.md` and `docs/plan.md`.

## Local prerequisites

- Python 3.12 (the exact patch remains subject to the deferred version matrix)
- `uv`
- GNU Make

Bootstrap and verify the repository:

```bash
make bootstrap
make check
```

No real credentials are required for unit tests. Unit tests must not access the
network and must mock Jira, Bedrock, AWS, Kubernetes, Prometheus, Loki, GitHub,
and persistence boundaries as appropriate.

## Validation status

The stakeholder authorized Phase 1 to begin under the documented Phase 0
deviation. Deferred technical validations remain dependency and production
gates; see `docs/validations/phase-0-deviation.md`.

