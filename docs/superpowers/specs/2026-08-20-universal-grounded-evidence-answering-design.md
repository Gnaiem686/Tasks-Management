# Universal Grounded Evidence Answering Design

## Goal

Every manager question about the selected Jira project must receive a useful,
natural-language Bedrock answer grounded in the structured project evidence
available through Jira MCP and the workforce-risk services. Generic
"not enough information" responses are a last resort, not a substitute for
collecting or using available evidence.

## Root cause

The current Jira project snapshot already contains task keys, summaries,
statuses, priorities, assignees, due dates, remaining hours, blockers,
dependencies, employee workload, capacity, skills, and deterministic risk
levels. The failure is in the chat evidence pipeline:

- a Bedrock-generated evidence plan may classify a task question as a broad
  mixed/workforce request;
- the completeness validator can consequently reject a concrete task answer
  for omitting unrelated employee coverage;
- the general project-evidence path does not persist the tasks or employees
  used in an answer as structured conversation context;
- follow-ups such as "name those tasks" therefore lack a reliable referent;
- semantic-validation exhaustion invokes a deliberately vague conservative
  Bedrock response even when structured evidence is present.

Jira MCP availability is not the root cause. The application must preserve and
focus the evidence it already retrieves.

## Selected architecture

Use an evidence-first conversational pipeline:

```text
Manager question
-> resolve structured references from the previous answer
-> Bedrock plans required evidence categories
-> deterministic code validates and corrects the plan scope
-> allowlisted Jira MCP and workforce reads collect evidence
-> deterministic code creates a focused AnswerEvidenceSet
-> Bedrock generates the final natural-language answer
-> deterministic grounding and completeness validation
-> structured answer context is retained for the next turn
```

Bedrock remains responsible for every successful user-visible chat answer.
Deterministic code selects, normalizes, derives, and validates facts; it does
not generate final chat prose. Risk scores and classifications remain
deterministic and unchanged.

## Components

### Evidence plan normalization

The Bedrock evidence planner remains flexible and is not replaced by a fixed
intent whitelist. A deterministic normalizer checks that the planned scope and
categories are compatible with the question and resolved references. It must:

- preserve task scope for questions asking which/list/name tasks or work;
- preserve employee scope for questions about people, workload, capacity,
  skills, or employee risk;
- use mixed scope when a question connects employees and tasks;
- include deadlines for due-date or schedule questions;
- include dependencies and blockers for blocked, waiting, dependency, or
  downstream-impact questions;
- preserve resolved task and employee entities from prior turns;
- default to a broad read-only evidence plan when the planner output is invalid
  without converting every question into an employee-completeness request.

The normalizer selects evidence categories, never writes data and never creates
a final answer.

### AnswerEvidenceSet

After the existing project snapshot is collected, a focused evidence set is
derived for the current question. It contains:

- the selected project and evidence timestamp;
- relevant employees with authoritative role, skills, capacity, remaining
  workload, active tasks, and deterministic risk level;
- relevant tasks with key, summary, status, priority, assignee, due date,
  remaining estimate, explicit blocker, and dependency direction;
- deterministic derived facts such as capacity headroom, overdue/due-soon
  state, blocked versus downstream-blocking state, and missing fields;
- the complete matching entity set for exhaustive list questions;
- explicit `MissingData` records and ambiguous references;
- safe Jira URLs or identifiers used for validation, not internal transport
  details shown to managers.

The set may contain the whole bounded WFD snapshot when the question is broad,
but the prompt highlights the facts relevant to the question so Bedrock cannot
silently ignore them.

### Conversation context

Every grounded answer stores the structured tasks and employees that supported
it, not a copy of raw prompts or Jira bodies. The context includes the previous
question, evidence focus, task facts, employee references, and whether the
answer represented an exhaustive set.

Plural follow-ups such as "name those tasks" reuse the complete prior entity
set. Singular follow-ups use the one prior entity or ask a concise
clarification when multiple candidates exist. A follow-up never performs an
unrelated semantic lookup while a valid structured referent exists.

## Missing evidence behavior

"No matching evidence" and "evidence unavailable" are distinct:

- a successful Jira search returning no blocked tasks supports the answer that
  no tasks are currently blocked;
- a missing task estimate produces a specific data-quality statement naming
  the task and the missing field;
- missing capacity or skills produces a specific workforce-data request;
- an ambiguous reference produces a question naming the possible entities;
- a transient MCP or Bedrock failure follows its retry policy rather than being
  described as missing business evidence.

Before saying information is insufficient, the agent must resolve prior
references, run the relevant focused reads, read issue relationships/details,
and use a broader safe project read when the focused result is incomplete.
Only then may Bedrock explain exactly what was checked, what is missing, and
what the manager should provide. Vague insufficiency language is rejected when
the evidence set contains facts that answer the question.

## Bedrock generation and grounding

Bedrock receives the exact question, selected project, focused evidence set,
resolved prior context, deterministic findings, and explicit missing data. It
returns plain natural-language prose without exposing internal evidence IDs.

Grounding validates every claimed Jira key, summary, status, priority,
assignee, due date, estimate, blocker, dependency, employee attribute,
capacity value, and risk level against the focused evidence. Completeness is
evaluated against the entities relevant to the question, not unrelated
categories in the raw planner output.

If a response is incomplete or ungrounded, Bedrock receives a correction with
a smaller explicit evidence set and retries. A conservative answer is allowed
only when the focused evidence genuinely cannot support the requested claim.
It must name the exact missing data or ambiguity instead of returning a generic
refusal.

Transient Bedrock failures retain the existing persistent browser behavior:
the UI displays `Bedrock is still working...` and retries until Bedrock answers
or the manager cancels/leaves. There is no deterministic chat-text fallback.

## Testing

Tests must cover:

- exact Jira MCP/project snapshot evidence for WFD tasks and employees;
- plan normalization for task, employee, mixed, blocker, deadline, skills,
  workload, project-progress, and unknown free-form questions;
- focused evidence selection and exhaustive matching;
- blocked versus downstream-blocking direction;
- deadline-risk evidence including dates, remaining work, priority, and
  dependencies;
- employee risk, capacity, skills, missing estimates, and insufficient-data
  distinctions;
- follow-ups including "name those tasks," "who owns that task," and ambiguous
  singular references;
- rejection of every unsupported Jira/workforce factual claim;
- rejection of vague insufficiency when usable evidence exists;
- exact missing-data clarification when evidence is genuinely absent;
- preservation of persistent Bedrock retry behavior;
- local end-to-end representative questions against the WFD evidence path.

Representative acceptance questions include:

- Which employees are at risk and why?
- Which tasks are most likely to miss their deadlines?
- Name those tasks.
- Which work is blocked right now?
- Name the tasks that are blocked.
- Who owns WFD-11 and what is blocking it?
- Who has available capacity and the relevant skills to help?
- What information is missing from the current analysis?

For each question, the answer must contain the concrete facts available in the
focused evidence set or a precise, evidence-backed request for the missing
field as the final option.

## Scope boundaries

This change modifies only the read-only chat evidence, conversation-context,
Bedrock-prompt, grounding, and related test paths. It does not redesign the UI,
scoring model, Jira mutation workflow, deployment, or infrastructure.
