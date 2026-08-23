# Chat Width and Alert Score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Widen desktop chat to 40% and display authoritative deterministic scores in risk alerts.

**Architecture:** The dashboard service copies the employee score into the typed alert contract. The browser renders that value without deriving risk data. CSS changes only the desktop grid ratio.

**Tech Stack:** FastAPI, Pydantic, vanilla JavaScript/CSS, pytest, Node-based UI runtime tests.

## Global Constraints

- Local changes only; no GitHub or deployment actions.
- Manager UI remains read-only.
- Deterministic backend scoring remains authoritative.

---

### Task 1: Authoritative alert score

**Files:**
- Modify: `services/agent-api/src/agent_api/dashboard/models.py`
- Modify: `services/agent-api/src/agent_api/dashboard/service.py`
- Modify: `services/agent-api/src/agent_api/web/static/chat.js`
- Test: `services/agent-api/tests/test_dashboard_service.py`
- Test: `services/agent-api/tests/ui/test_manager_supporting_views.py`

**Interfaces:**
- Produces: `AlertSummary.score: int` populated from `EmployeeSummary.score`.

- [ ] Add failing service and UI runtime assertions for numeric alert scores.
- [ ] Run the targeted tests and confirm the expected failures.
- [ ] Add the score to the typed alert response and use it in both alert renderers.
- [ ] Run targeted tests and confirm they pass.

### Task 2: Forty-percent desktop chat

**Files:**
- Modify: `services/agent-api/src/agent_api/web/static/styles.css`
- Test: `services/agent-api/tests/ui/test_dashboard_layout.py`

**Interfaces:**
- Produces: desktop `grid-template-columns: minmax(0,3fr) minmax(24rem,2fr)`.

- [ ] Change the layout assertion first and confirm it fails.
- [ ] Apply the 3:2 desktop grid without changing responsive breakpoints.
- [ ] Run UI and regression tests.
- [ ] Rebuild and restart Agent API locally on port 8000.
