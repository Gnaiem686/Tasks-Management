from __future__ import annotations

import inspect

import pytest
from workforce_persistence.models import Base
from workforce_persistence.repositories import AuditRepository

EXPECTED_TABLES = {
    "api_key_principals",
    "employee_profiles",
    "employee_skills",
    "capacity_allocations",
    "scoring_versions",
    "evidence_snapshots",
    "risk_results",
    "comment_evidence",
    "reassignment_proposals",
    "approval_decisions",
    "proposal_executions",
    "alerts",
    "alert_occurrences",
    "report_metadata",
    "scan_runs",
    "outbox_events",
    "audit_events",
}


@pytest.mark.unit
def test_schema_contains_every_principal_record_with_environment() -> None:
    assert set(Base.metadata.tables) >= EXPECTED_TABLES
    for table_name in EXPECTED_TABLES:
        table = Base.metadata.tables[table_name]
        assert "id" in table.c
        assert "environment" in table.c


@pytest.mark.unit
def test_api_key_schema_never_contains_raw_key_material() -> None:
    columns = set(Base.metadata.tables["api_key_principals"].c.keys())

    assert {
        "actor_id",
        "key_digest",
        "role",
        "environment",
        "project_scopes",
        "expires_at",
        "revoked_at",
    } <= columns
    assert "raw_key" not in columns
    assert "api_key" not in columns


@pytest.mark.unit
def test_comment_evidence_schema_never_stores_raw_comment_body() -> None:
    columns = set(Base.metadata.tables["comment_evidence"].c.keys())

    assert "body" not in columns
    assert "raw_body" not in columns
    assert "comment_text" not in columns


@pytest.mark.unit
def test_state_and_idempotency_constraints_are_declared() -> None:
    proposals = Base.metadata.tables["reassignment_proposals"]
    scans = Base.metadata.tables["scan_runs"]
    outbox = Base.metadata.tables["outbox_events"]

    proposal_constraints = {constraint.name for constraint in proposals.constraints}
    scan_constraints = {constraint.name for constraint in scans.constraints}
    outbox_constraints = {constraint.name for constraint in outbox.constraints}
    assert "ck_reassignment_proposals_state" in proposal_constraints
    assert "uq_reassignment_proposals_environment_idempotency" in proposal_constraints
    assert "ck_scan_runs_state" in scan_constraints
    assert "uq_scan_runs_environment_idempotency" in scan_constraints
    assert "uq_outbox_events_consumer_key" in outbox_constraints


@pytest.mark.unit
def test_audit_repository_exposes_append_and_verify_only() -> None:
    public_methods = {
        name
        for name, _ in inspect.getmembers(AuditRepository, inspect.isfunction)
        if not name.startswith("_")
    }

    assert public_methods == {"append", "verify_chain"}
