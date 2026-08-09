"""Add complete immutable snapshot result details."""

import sqlalchemy as sa
from alembic import op

revision = "0003_snapshot_result_details"
down_revision = "0002_capacity_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, default in (
        ("thresholds", "'{}'::json"),
        ("evidence_references", "'[]'::json"),
        ("missing_evidence", "'[]'::json"),
        ("excluded_evidence", "'[]'::json"),
    ):
        op.add_column(
            "risk_results",
            sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text(default)),
        )
        op.alter_column("risk_results", name, server_default=None)
    op.create_unique_constraint(
        "uq_evidence_snapshot_identity",
        "evidence_snapshots",
        ["environment", "subject_type", "subject_id", "fingerprint"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_evidence_snapshot_identity", "evidence_snapshots", type_="unique"
    )
    for name in (
        "excluded_evidence",
        "missing_evidence",
        "evidence_references",
        "thresholds",
    ):
        op.drop_column("risk_results", name)
