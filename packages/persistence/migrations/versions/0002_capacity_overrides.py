"""Add versioned workforce capacity overrides."""

from typing import cast

from alembic import op
from sqlalchemy import Table
from workforce_persistence.models import CapacityOverride

revision = "0002_capacity_overrides"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cast(Table, CapacityOverride.__table__).create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    cast(Table, CapacityOverride.__table__).drop(bind=op.get_bind(), checkfirst=True)
