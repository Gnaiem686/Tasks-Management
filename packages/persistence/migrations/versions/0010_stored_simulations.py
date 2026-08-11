"""Store deterministic simulations before proposal creation."""

from typing import cast

from alembic import op
from sqlalchemy import Table
from workforce_persistence.models import ReassignmentSimulation

revision = "0010_stored_simulations"
down_revision = "0009_proposal_safety"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cast(Table, ReassignmentSimulation.__table__).create(
        bind=op.get_bind(), checkfirst=True
    )


def downgrade() -> None:
    cast(Table, ReassignmentSimulation.__table__).drop(
        bind=op.get_bind(), checkfirst=True
    )
