"""Make each proposal execution unique and idempotent."""

import sqlalchemy as sa
from alembic import op

revision = "0011_execution_idempotency"
down_revision = "0010_stored_simulations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proposal_executions",
        sa.Column(
            "write_attempted", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.add_column("proposal_executions", sa.Column("lease_owner", sa.String(128)))
    op.add_column(
        "proposal_executions", sa.Column("leased_at", sa.DateTime(timezone=True))
    )
    op.create_unique_constraint(
        "uq_execution_env_proposal",
        "proposal_executions",
        ["environment", "proposal_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_execution_env_proposal", "proposal_executions", type_="unique"
    )
    op.drop_column("proposal_executions", "leased_at")
    op.drop_column("proposal_executions", "lease_owner")
    op.drop_column("proposal_executions", "write_attempted")
