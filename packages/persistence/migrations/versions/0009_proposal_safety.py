"""Persist immutable simulation and decision safety metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0009_proposal_safety"
down_revision = "0008_scan_correlation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    additions = (
        ("simulation_id", sa.String(128)),
        ("project_key", sa.String(64)),
        ("confidence", sa.String(32)),
        ("scoring_versions", sa.JSON()),
        ("simulation_payload", sa.JSON()),
        ("requested_by", sa.String(128)),
    )
    for name, column_type in additions:
        op.add_column("reassignment_proposals", sa.Column(name, column_type))
    op.execute(
        "UPDATE reassignment_proposals SET simulation_id=id::text, "
        "project_key=split_part(task_key, '-', 1), confidence='medium', "
        "scoring_versions='[]'::json, simulation_payload='{}'::json, "
        "requested_by='legacy'"
    )
    for name, _ in additions:
        op.alter_column("reassignment_proposals", name, nullable=False)
    op.add_column("approval_decisions", sa.Column("idempotency_key", sa.String(128)))
    op.execute("UPDATE approval_decisions SET idempotency_key=id::text")
    op.alter_column("approval_decisions", "idempotency_key", nullable=False)
    op.create_unique_constraint(
        "uq_decision_env_idempotency",
        "approval_decisions",
        ["environment", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_decision_env_idempotency", "approval_decisions", type_="unique"
    )
    op.drop_column("approval_decisions", "idempotency_key")
    for name in (
        "requested_by",
        "simulation_payload",
        "scoring_versions",
        "confidence",
        "project_key",
        "simulation_id",
    ):
        op.drop_column("reassignment_proposals", name)
