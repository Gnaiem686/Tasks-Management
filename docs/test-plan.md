# Executable test plan

## Purpose and governing rules

This document defines test boundaries, entry criteria, commands, success
criteria, and retained evidence for the Workforce Risk Agent. A test is not
complete merely because it was written: it must run in the designated gate and
produce inspectable evidence.

Every defect fixed during implementation receives a regression test. The
governing behavior remains `read degraded; write closed`. No test may
automatically retry an ambiguous Jira mutation.

## Test categories and gates

### Required pull-request tests

Command:

```bash
make check
```

The PR gate runs formatting, linting, strict typing, no-network unit tests,
security contract tests, secret scanning, dependency auditing, SBOM generation,
and documentation contracts. It retains JUnit, coverage, audit, SBOM, and
failed-test artifacts and publishes a GitHub Actions summary.

Success means every required check passes, the lockfile is unchanged, no secret
is detected, and required artifacts are non-empty.

### Required dev-deployment smoke tests

Command:

```bash
make smoke-dev
```

The future dev gate covers Agent API health, the lightweight UI, API-key
authentication, Jira MCP read, Workforce Risk MCP scoring, read-only DevOps MCP,
PostgreSQL transactions, S3 report round-trip, SQS/SES notification flow, one
seeded overload detection, and one non-mutating simulation.

Success means every dependency is environment-scoped, the seeded scenario is
detected with the expected score version, and no production resource is read or
mutated.

### Optional live Bedrock tests

Command:

```bash
uv run pytest -m live_bedrock tests/integration/test_bedrock_smoke.py -q
```

These tests are opt-in, require an approved dev role, use minimized synthetic
evidence, and never run on ordinary PRs. Unit and integration tests mock the
Bedrock/LLM boundary. A missing live credential skips this category rather than
weakening deterministic tests.

### Controlled dev-only failure injection

Command:

```bash
make test-failure-injection-dev
```

This future gate covers dependency timeouts, circuit opening, SQS duplication,
worker termination, crash after Jira write, uncertain verification, missed
scans, failed readiness, and rollback rehearsal. Guards must refuse to run when
the environment is not dev.

## Test levels

### Unit

Boundary: no network and no real credentials. Unit tests mock Bedrock/LLM,
Jira, AWS services, Kubernetes, Prometheus, Loki, GitHub, and repositories where
appropriate. Agent logic and MCP tool handlers run in isolation; direct handler
tests do not claim MCP transport coverage.

Command:

```bash
make test-unit
```

Success means deterministic logic, state transitions, authorization rules,
normalization, schemas, fallbacks, and refusal behavior match exact expected
values. Critical domain modules receive explicit coverage thresholds rather
than relying on one repository-wide percentage.

### Contract

Command:

```bash
uv run pytest -m contract tests/contract -q
```

Success means typed HTTP and MCP envelopes reject malformed data, unknown schema
versions, wrong environments, missing timestamps, and broken correlation IDs.

### Integration

Command:

```bash
make test-integration
```

The mandatory test proves the Agent API and Workforce Risk MCP run as separate real processes
and communicate through MCP Streamable HTTP. Direct handler calls and
mocked MCP clients do not satisfy it. The named test is
`tests/integration/test_agent_workforce_mcp_streamable_http.py`.

Success asserts:

- HTTP status;
- deterministic score;
- risk level;
- confidence;
- factor contributions;
- evidence references;
- scoring version;
- correlation propagation;
- typed schema;
- proof of real transport.

Persistence integration
uses PostgreSQL and S3-compatible services. Jira tests use only dedicated dev
data and credentials.

Transport failure coverage includes connection failure, timeout, malformed
response, schema-version mismatch, unauthorized tool call, duplicate request,
and service restart during interaction.

### End to end

Command:

```bash
uv run pytest -m e2e tests/e2e -q
```

Success means the resettable seeded business scenario proceeds from scheduled
detection through alert, investigation, simulation, explicit approval,
assignee-only Jira mutation, exact read-back, and append-only audit evidence
using one correlation chain.

### Infrastructure

Command:

```bash
uv run pytest -m infrastructure tests/infrastructure -q
```

Success means Terraform validates, nodes join, both namespaces become healthy,
environment isolation holds, manifests and policies validate, TLS ingress works,
and backup/restore rehearsal succeeds.

### Performance

Command:

```bash
uv run pytest -m performance tests/performance -q
```

Success is measured against approved thresholds for realistic workspace
scoring, daily scan duration, investigation latency, concurrent simulations,
notification backlog, and HPA behavior.

### Accessibility and browser UI

Command:

```bash
make ui-test
```

Success means keyboard operation, screen-reader labels, semantic tables and
alerts, visible confidence/staleness warnings, and approval confirmation that
does not depend on color.

### Security and resilience

Command:

```bash
uv run pytest -m security tests/security -q
```

Success includes prompt-injection resistance, forged/replayed API-key refusal,
cross-environment denial, role enforcement, stale/duplicate approval refusal,
secret-free outputs, crash reconciliation, audit tamper detection, and graceful
shutdown.

## Deterministic scenario fixtures

Required fixtures cover a balanced team, overloaded employee, difficult task
without mentoring, the same task with senior pairing, overloaded proposed
assignee, insufficient data, and stale proposal evidence. Each fixture records
the scoring version and exact expected score family outcomes.

## Data safety and cleanup

Automated Jira tests operate only on `WRD`, use synthetic work data, and tag
owned records for deterministic cleanup. Cleanup refuses `WORKFORCE-PROD` and
any unknown environment. Raw tokens, email addresses, full account IDs, and raw
comment bodies do not enter test reports.

## CI evidence

Required artifacts include:

- `artifacts/tests/junit.xml` and coverage XML;
- failed-test diagnostics;
- vulnerability and secret-scan summaries;
- CycloneDX SBOM;
- Terraform plan and validation summaries;
- Kubernetes validation summaries;
- deployment and smoke-test summaries.

`docs/test-mapping.md` maps every numbered requirement to planned automated
evidence. Status changes from `planned` only when the named test exists and its
designated gate has passed.
