"""Add idempotent notification delivery state."""

from typing import cast

from alembic import op
from sqlalchemy import Table
from workforce_persistence.models import NotificationDelivery

revision = "0006_notification_delivery"
down_revision = "0005_alert_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cast(Table, NotificationDelivery.__table__).create(
        bind=op.get_bind(), checkfirst=True
    )


def downgrade() -> None:
    cast(Table, NotificationDelivery.__table__).drop(
        bind=op.get_bind(), checkfirst=True
    )
