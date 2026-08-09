"""Add scan correlation propagation."""

import sqlalchemy as sa
from alembic import op

revision = "0008_scan_correlation"
down_revision = "0007_report_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scan_runs", sa.Column("correlation_id", sa.String(128)))
    op.execute("UPDATE scan_runs SET correlation_id = 'legacy-' || id::text")
    op.alter_column("scan_runs", "correlation_id", nullable=False)


def downgrade() -> None:
    op.drop_column("scan_runs", "correlation_id")
