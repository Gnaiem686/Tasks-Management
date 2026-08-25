# Evidence-Specific Bedrock Explanations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Bedrock answer manager questions with detailed, factor-specific evidence instead of generic explanations.

**Architecture:** Deterministic code derives ordered contributor and mitigating-factor guidance from the existing immutable risk result. The allowlisted payload and system prompt guide Bedrock, while response validation rejects generic or numerically unsafe prose and preserves the existing fallback path.

**Tech Stack:** Python 3.12, Pydantic, Amazon Bedrock Converse API, pytest.

## Global Constraints

- Deterministic code remains the sole owner of scores and risk levels.
- Manager-facing prose may include only the overall `0–100` score, not numeric factor contributions or invented scores.
- Bedrock may use only supplied work-planning evidence and citations.
- Existing bounded retries, circuit breaker, citation validation, candidate validation, and deterministic fallback remain active.

---

### Task 1: Derive allowlisted explanation guidance

**Files:**
- Modify: `services/agent-api/src/agent_api/llm/schemas.py`
- Modify: `services/agent-api/tests/test_explanations.py`

**Interfaces:**
- Consumes: `ExplanationRequest.risk.factors`.
- Produces: `build_model_payload()` keys `strongest_contributors` and `mitigating_factors`, each containing deterministic factor names, directions, and safe evidence references.

- [ ] Write failing tests for deterministic ordering, positive contributors, zero/low contributors, and missing evidence.
- [ ] Run `.venv/bin/pytest services/agent-api/tests/test_explanations.py -q` and confirm the guidance assertions fail.
- [ ] Implement the smallest deterministic payload derivation without changing scoring.
- [ ] Rerun the focused tests and confirm they pass.

### Task 2: Require detailed factor-specific Bedrock prose

**Files:**
- Modify: `services/agent-api/src/agent_api/llm/bedrock.py`
- Modify: `services/agent-api/tests/test_explanations.py`

**Interfaces:**
- Consumes: the enriched payload and `ModelExplanation.answer`.
- Produces: validated detailed answers that mention supplied factor names in canonical or human-readable form and contain no numeric factor contribution values.

- [ ] Write failing tests proving generic prose and factor-point disclosure are rejected, while a detailed low-risk overdue explanation is accepted.
- [ ] Run the focused test file and confirm failures occur for the new requirements.
- [ ] Strengthen `SYSTEM_PROMPT` and `_validate_result()` minimally, preserving all existing safety checks.
- [ ] Update existing valid fixtures to use evidence-specific prose.
- [ ] Run focused tests and confirm they pass.

### Task 3: Verification and commit

**Files:**
- Verify all files above.

- [ ] Run `.venv/bin/ruff check services/agent-api/src/agent_api/llm services/agent-api/tests/test_explanations.py`.
- [ ] Run `.venv/bin/mypy services/agent-api/src/agent_api/llm`.
- [ ] Run `.venv/bin/pytest services/agent-api/tests/test_explanations.py services/agent-api/tests/test_graph_workflow.py -q`.
- [ ] Run `git diff --check`.
- [ ] Commit with `feat: require evidence-specific Bedrock explanations`.
