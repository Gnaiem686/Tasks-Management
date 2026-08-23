# Chat Reliability Design

## Goal

Normal project questions must return HTTP 200 even when evidence is incomplete,
references are ambiguous, no candidate exists, or Bedrock prose fails semantic
validation. HTTP 503 is reserved for an exhausted required dependency failure.

## Selected design

The generalized evidence pipeline remains unchanged. Reliability is added at
four boundaries:

1. Invalid but successfully returned planner output degrades to the conservative
   allowlisted read plan. Planner transport exhaustion still fails as Bedrock
   unavailability.
2. Candidate derivation returns `CandidateRankingResult` with `success`,
   `insufficient_data`, or `no_candidates`; normal missing data never raises.
3. Optional collector gaps are represented in `missing_data` and passed to final
   Bedrock generation.
4. Grounding or completeness rejection gets one repair generation. If repair is
   still semantically invalid, a final Bedrock conservative-answer call produces
   an insufficient-information response. Only failure of that Bedrock call is a
   service failure.

Ambiguous references are included in `UniversalEvidenceBundle`; Bedrock asks a
clarifying question. The generalized planner remains read-only and Jira writes
remain outside chat.

## HTTP classification

Missing evidence, ambiguity, no candidates, invalid optional planner output and
semantic validation disagreement return HTTP 200. Exhausted Bedrock/Jira MCP or
required persistence failures may return HTTP 503. Unexpected programming errors
are logged with their original exception and must not be mislabeled as Bedrock.

## Testing

Tests inject each optional-data failure independently, validate typed candidate
outcomes, force initial and repaired grounding failures, exercise planner
malformation, and run at least fifty generated question variants. Persistent
Bedrock and required Jira failures are the only expected 503 cases.
