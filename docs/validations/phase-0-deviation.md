# Phase 0 implementation-start deviation

Approved on: 2026-08-06

Approver: Project stakeholder and repository owner

Decision: Start Phase 1 while retaining incomplete Phase 0 technical
validations as explicit dependency gates. This approval does not represent
unrun checks as successful and does not waive production gates.

## Jira scope

The configured development Jira project remains `WRD`. No replacement Jira
project will be created. `WORKFORCE-PROD` remains read-only and forbidden to
seed, clean, or mutate.

## Evidence completed

- API-token authentication was enabled for Atlassian Rovo MCP.
- Non-interactive MCP Streamable HTTP initialization returned HTTP 200 twice.
- The required Jira read, JQL, project-discovery, account-resolution, issue
  edit, and read-back tools were exposed.
- Project discovery returned `WRD`.
- `WRD-1` returned standard structured fields and `Blocker Category` with the
  value `Need clarification`.
- A controlled assignee-only edit returned success and read-back matched the
  exact intended account identifier.
- Summary, status, priority, due date, and blocker category remained unchanged.
- No mutation retry occurred.

No credentials, email addresses, account identifiers, session identifiers, or
raw response bodies are retained in this record.

## Deferred validations

The following checks remain mandatory before their dependent work can be
considered complete:

- automated Jira scope, restart, failure, rotation, and cleanup validation;
- automated verification of the approved `workforce-employee:EMP-00N` label
  convention across the seeded `WRD` scenario;
- Amazon Bedrock regional access and deterministic fallback validation;
- compatible platform version selection and exact pins;
- provisional HPA measurement contract;
- explicit Argo CD adopt-or-omit decision.

Any Jira mutation feature remains blocked until its proposal-safety,
authorization, freshness, audit, idempotency, and read-back prerequisites pass.
Production promotion remains blocked until every applicable technical and
pre-production validation passes.
