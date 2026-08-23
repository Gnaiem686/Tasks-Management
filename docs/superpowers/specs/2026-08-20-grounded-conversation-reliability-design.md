# Grounded Conversation Reliability Design

## Problem

The assistant currently persists rendered chat text in the browser but does not
preserve typed Jira results between turns. A follow-up such as "that task" can
therefore lose its WFD-7 referent and trigger an unrelated lookup or Bedrock
claim. Intermittent Jira, graph, and Bedrock failures are also collapsed into a
generic 503, making the actual server-side cause hard to diagnose.

## Selected design

Simple Jira facts are resolved by deterministic intent handlers. The handlers
read typed Jira MCP evidence, format the response directly, and return a bounded
`GroundedAnswerContext` containing the issue key, summary, assignee, status, due
date, estimate, blocker, and dependency facts used by the answer. The browser
returns this context on the next request. A single prior issue resolves "that
task"; multiple prior issues require clarification; no prior issue cannot be
guessed.

Bedrock remains responsible for explanations and synthesis. Before a generated
answer is returned, its Jira issue claims must match the structured evidence for
issue key, summary, assignee, and status. Failed grounding never reaches the UI.

## Deterministic Jira intents

- list tasks in the Done status category;
- read current task status;
- read task assignee;
- list tasks missing remaining estimates;
- list blocked tasks;
- list overdue tasks;
- list tasks due within seven days.

These paths do not require Bedrock.

## Observability and failure handling

Every assistant request uses one correlation ID across structured logs for the
request, project, intent, graph node, Jira MCP call and duration, Bedrock call
and duration, structured parsing, grounding validation, and final response.
Server logs record safe exception type and message. They never record secrets,
tokens, raw prompts, or unminimized Jira content.

Failures are classified as `jira_mcp_timeout`, `jira_mcp_auth_error`,
`jira_mcp_rate_limit`, `bedrock_timeout`, `bedrock_throttling`,
`bedrock_model_error`, `output_parse_error`, `grounding_validation_error`, or
`internal_exception`. Only timeouts, throttling, and temporary 5xx failures are
retried, with exponential backoff and jitter for at most three total attempts.
Authentication, parsing, grounding, and programming errors are not blindly
retried. The UI receives a safe message and the correlation ID.

## Validation

Tests reproduce the WFD-7 follow-up, ambiguous prior results, deterministic
handlers, grounding rejection, retry eligibility, failure classification, and
correlation propagation. Existing graph, Jira MCP, Bedrock, and UI tests must
remain green. The application is then exercised locally against WFD.
