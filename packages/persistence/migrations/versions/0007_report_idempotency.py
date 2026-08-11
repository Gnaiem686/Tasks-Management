"""Enforce environment-scoped report idempotency."""

from alembic import op

revision = "0007_report_idempotency"
down_revision = "0006_notification_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_reports_env_idempotency",
        "report_metadata",
        ["environment", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_reports_env_idempotency", "report_metadata", type_="unique")
