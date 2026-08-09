"""Add alert deduplication and occurrence history."""

import sqlalchemy as sa
from alembic import op

revision = "0005_alert_outbox"
down_revision = "0004_comment_evidence_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("risk_type", sa.String(64), nullable=True))
    op.add_column("alerts", sa.Column("scoring_window", sa.String(64), nullable=True))
    op.add_column("alerts", sa.Column("dedup_key", sa.String(128), nullable=True))
    op.add_column(
        "alerts", sa.Column("evidence_fingerprint", sa.String(128), nullable=True)
    )
    op.add_column("alerts", sa.Column("last_notified_at", sa.DateTime(timezone=True)))
    op.execute(
        "UPDATE alerts SET risk_type='legacy', scoring_window='legacy', "
        "dedup_key=id::text, evidence_fingerprint=id::text"
    )
    for column in ("risk_type", "scoring_window", "dedup_key", "evidence_fingerprint"):
        op.alter_column("alerts", column, nullable=False)
    op.create_unique_constraint(
        "uq_alerts_env_dedup", "alerts", ["environment", "dedup_key"]
    )
    op.add_column(
        "alert_occurrences",
        sa.Column("sequence_number", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "alert_occurrences",
        sa.Column("severity", sa.String(32), nullable=False, server_default="high"),
    )
    op.add_column(
        "alert_occurrences",
        sa.Column(
            "evidence_fingerprint",
            sa.String(128),
            nullable=False,
            server_default="legacy",
        ),
    )


def downgrade() -> None:
    op.drop_column("alert_occurrences", "evidence_fingerprint")
    op.drop_column("alert_occurrences", "severity")
    op.drop_column("alert_occurrences", "sequence_number")
    op.drop_constraint("uq_alerts_env_dedup", "alerts", type_="unique")
    op.drop_column("alerts", "last_notified_at")
    op.drop_column("alerts", "evidence_fingerprint")
    op.drop_column("alerts", "dedup_key")
    op.drop_column("alerts", "scoring_window")
    op.drop_column("alerts", "risk_type")
