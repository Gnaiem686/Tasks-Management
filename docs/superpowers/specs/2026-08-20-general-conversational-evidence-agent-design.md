# General Conversational Evidence Agent Design

## Status

Approved on 2026-08-20. This design supersedes fixed-intent-controlled evidence
gathering for normal chat requests. It does not change deterministic scoring,
dashboard calculations, or the approval-controlled Jira reassignment workflow.

## Problem

The current chat graph can classify unfamiliar wording into a specialist route
whose tool requires unavailable capabilities or a missing entity identifier.
Those ordinary evidence gaps become HTTP 503 responses before Bedrock is called.
Adding another phrase or handler for every new manager question cannot satisfy a
general conversational assistant.

## Selected architecture

Use an evidence-category planner followed by a `UniversalEvidenceBundle`:

```text
authenticated request
  -> structured conversational-reference resolution
  -> Bedrock evidence-planning call
  -> validated EvidencePlan
  -> allowlisted read-only collectors
  -> UniversalEvidenceBundle
  -> deterministic calculation or ranking when needed
  -> Bedrock final natural-language answer
  -> generic grounding and completeness validation
  -> response
```

Fixed intent labels may remain as telemetry, analytics, observability, or
optimization hints. They do not decide whether a question is supported and do
not select the only executable path.

## Evidence plan

The planning call returns a small Pydantic model with unknown fields forbidden:

```text
EvidencePlan
  scope: project | employee | task | mixed
  entities: resolved typed entity references
  evidence_categories: unique allowlisted EvidenceCategory values
  exhaustive: boolean
```

Allowed evidence categories are:

- `jira_issues`
- `workforce_profiles`
- `capacity_and_workload`
- `skills_and_seniority`
- `risk_results`
- `dependencies_and_blockers`
- `deadlines`
- `history`
- `operations`

The plan selects evidence categories, not handlers or arbitrary tool names. The
application maps categories to a fixed read-only collector registry. Unknown
categories, writes, and unregistered tools fail plan validation before any tool
call. A planning failure caused by invalid model output is retried only within
the Bedrock transient retry budget; a valid conservative read plan may be used
only when it can be derived from selected structured context without producing
final prose.

## Universal evidence bundle

All collectors contribute to one optional-safe typed bundle. Absence is never
silently converted to zero and never represented by misleading capacity terms.
The bundle distinguishes:

- configured capacity hours
- workload hours
- available capacity hours
- capacity headroom hours
- utilization percent
- employee workload classification
- task delivery risk
- skills and seniority
- dependencies and blockers
- deadlines
- deterministic risk results
- immutable historical snapshots
- attributable but untrusted comment metadata
- missing-data records
- source metadata, timestamps, schema versions, and correlation ID

Capacity semantics are exact:

```text
capacity_headroom_hours = configured_capacity_hours - workload_hours
available_capacity_hours = max(capacity_headroom_hours, 0)
utilization_percent = workload_hours / configured_capacity_hours * 100
```

For 24 configured hours and 36 workload hours, available capacity is 0,
headroom is -12, and utilization is 150%. A missing or non-positive configured
capacity produces insufficient data instead of a guessed utilization.

Each missing item is explicit:

```text
MissingData
  category
  reason
  entity
  required_for_claim
```

Optional missing evidence does not abort the graph. Bedrock receives the
missing-data records and explains uncertainty. Required missing evidence blocks
only the affected conclusion or action, not unrelated read-only answers.

## Collectors and deterministic derivation

Collectors are independently bounded, typed, read-only, and correlated. The
initial registry covers Jira issues, profiles, workload/capacity, skills,
deterministic risk, dependencies/blockers, deadlines, history, and read-only
operations evidence. Each collector validates schema version, environment,
timestamp, correlation ID, and success/error status.

Derived calculations operate on the bundle, never on Bedrock prose. Candidate
selection gathers the overloaded employee's tasks, candidate profiles,
capacity/workload, skills, seniority, and task requirements. Deterministic code
filters and ranks candidates. Bedrock explains only returned rankings. Missing
skills or capacity yields an insufficient-information explanation rather than
an exception or invented candidate.

## Conversation references

Conversation memory stores structured references and the preceding answer's
structured result, not raw prompts or full evidence. A general resolver handles
singular and plural references such as `this risk`, `that task`, `those tasks`,
`that employee`, `them`, and `it`. An unambiguous reference is inserted into the
plan context. Multiple candidates are presented to Bedrock as explicit choices
for a clarification response; none is guessed. No question-specific follow-up
rule is added.

## Final answer and grounding

Every successful visible answer is generated by Bedrock from the validated
bundle. Deterministic code does not write conversational templates. The final
response is plain text, not brittle mandatory JSON.

The post-generation validator extracts factual claims and checks them against
the bundle dynamically: Jira key/summary/status/assignee/priority/date/estimate,
employee facts, capacity calculations, risk calculations, dependencies,
skills, dates, assignments, and deterministic candidate rankings. Unsupported
claims are not returned. The system may make one bounded correction request to
Bedrock with the validation failures; a repeated material contradiction returns
a safe grounded-response error with the correlation ID.

For exhaustive questions, completeness validation compares mentioned entities
or findings with every matching structured record in the bundle. This is based
on typed evidence and plan scope, never hard-coded issue keys or intent names.

## Failure and retry behavior

The graph records one correlation ID across request receipt, planning, nodes,
collectors, deterministic derivation, final Bedrock generation, grounding, and
HTTP response. Timeout, throttling, and temporary 5xx failures use exponential
backoff with jitter and at most three total attempts inside the workflow
deadline. Authentication, validation, authorization, and programming errors are
not retried blindly.

Missing employee ID, missing estimate, missing skills, absent history, no
candidate, ambiguous reference, unknown wording, or an unavailable optional
collector become evidence or clarification states, not infrastructure errors.
`AI assistant temporarily unavailable` is reserved for a genuine required
service failure that remains after bounded retries.

## Write-safety boundary

The planner and collectors are read-only. They cannot call Jira mutation tools.
The sole Jira reassignment mutation remains outside generalized chat:

```text
proposal -> simulation -> explicit structured approval
         -> Jira write -> read-back verification -> audit
```

Chat text never approves or executes a write.

## Verification

Tests must prove:

- candidate and project-wide insufficient-data questions reach Bedrock instead
  of throwing missing-tool or missing-employee exceptions;
- at least twenty previously unseen phrasings work without source changes;
- multi-turn singular, plural, ambiguous, and stale references resolve safely;
- plan schemas reject unknown categories and all write tools;
- each collector returns typed evidence or `missing_data`;
- capacity semantics produce 24/36 -> 0 available, -12 headroom, 150%;
- deterministic candidate ranking cannot be changed by Bedrock;
- generic grounding rejects invented Jira, employee, capacity, risk,
  dependency, skill, date, assignment, and candidate claims;
- exhaustive completeness is data-driven;
- transient retries are bounded and genuine exhaustion is classified correctly;
- the Agent API and Workforce Risk MCP still pass separate-process Streamable
  HTTP integration tests;
- the explicit reassignment workflow remains isolated from generalized chat.

The primary acceptance criterion is that a new valid project/workforce question
does not require adding its wording to source code.
