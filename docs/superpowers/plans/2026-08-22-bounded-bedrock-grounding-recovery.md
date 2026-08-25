# Bounded Bedrock Grounding Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** End infinite grounding-validation loops while keeping every successful chat response Bedrock-generated.

**Architecture:** `BedrockExplanationProvider` keeps persistent retry behavior for transport failures, but counts grounding repair failures separately. Once the configured grounding repair budget is exhausted, it returns the last non-empty Bedrock prose with `source="bedrock"` and logs the bounded bypass.

**Tech Stack:** Python 3.12, asyncio, Amazon Bedrock adapter, pytest.

## Global Constraints

- Local changes only; no GitHub or AWS deployment actions.
- Never generate deterministic chat prose.
- Do not weaken evidence collection or initial grounding validation.

---

### Task 1: Bound grounding recovery

**Files:**
- Modify: `services/agent-api/src/agent_api/llm/bedrock.py`
- Test: `services/agent-api/tests/test_explanations.py`

**Interfaces:**
- Consumes: `BedrockExplanationProvider._max_attempts` and the latest non-empty Bedrock response.
- Produces: a finite `ExplanationResponse` with `source="bedrock"` after exhausted semantic validation.

- [ ] Change the persistent-repair test so permanently rejected Bedrock prose must return within the configured attempt budget.
- [ ] Run the test and confirm the current implementation times out.
- [ ] Separate grounding attempt exhaustion from persistent transport retry behavior.
- [ ] Return the final Bedrock prose after bounded grounding repair and log the validation bypass.
- [ ] Run targeted and Agent API regression tests.
- [ ] Rebuild and restart only the local Agent API container on port 8000.
