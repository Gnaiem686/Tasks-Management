"""Add current Jira task state and immutable progress history."""

from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0012_task_progress_history"
down_revision = "0011_execution_idempotency"
branch_labels = None
depends_on = None


def _record_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "work_weeks",
        *_record_columns(),
        sa.Column("project_key", sa.String(64), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("week_end", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "environment",
            "project_key",
            "week_start",
            name="uq_work_week_env_project_start",
        ),
    )
    op.create_table(
        "task_current_states",
        *_record_columns(),
        sa.Column("project_key", sa.String(64), nullable=False),
        sa.Column("issue_key", sa.String(64), nullable=False),
        sa.Column("work_week_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(128), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("jira_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_structured_progress_at", sa.DateTime(timezone=True)),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["work_week_id"], ["work_weeks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "environment",
            "project_key",
            "issue_key",
            name="uq_task_current_env_project_issue",
        ),
    )
    op.create_table(
        "task_progress_snapshots",
        *_record_columns(),
        sa.Column("work_week_id", sa.Uuid(), nullable=False),
        sa.Column("project_key", sa.String(64), nullable=False),
        sa.Column("issue_key", sa.String(64), nullable=False),
        sa.Column("assignee_id", sa.String(256)),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("jira_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(128), nullable=False),
        sa.Column("original_estimate_hours", sa.Float()),
        sa.Column("remaining_estimate_hours", sa.Float()),
        sa.Column("time_spent_hours", sa.Float()),
        sa.Column("due_date", sa.Date()),
        sa.Column("priority", sa.String(64)),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.Column("blocker_issue_keys", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(128), nullable=False),
        sa.ForeignKeyConstraint(["work_week_id"], ["work_weeks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "environment",
            "project_key",
            "issue_key",
            "work_week_id",
            "evidence_fingerprint",
            name="uq_task_snapshot_env_issue_week_fingerprint",
        ),
    )
    op.create_table(
        "task_progress_events",
        *_record_columns(),
        sa.Column("work_week_id", sa.Uuid(), nullable=False),
        sa.Column("project_key", sa.String(64), nullable=False),
        sa.Column("issue_key", sa.String(64), nullable=False),
        sa.Column("employee_id", sa.String(128)),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("old_value", sa.JSON()),
        sa.Column("new_value", sa.JSON()),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("event_fingerprint", sa.String(128), nullable=False),
        sa.ForeignKeyConstraint(["work_week_id"], ["work_weeks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "environment",
            "event_fingerprint",
            name="uq_task_progress_event_env_fingerprint",
        ),
    )


def downgrade() -> None:
    op.drop_table("task_progress_events")
    op.drop_table("task_progress_snapshots")
    op.drop_table("task_current_states")
    op.drop_table("work_weeks")
