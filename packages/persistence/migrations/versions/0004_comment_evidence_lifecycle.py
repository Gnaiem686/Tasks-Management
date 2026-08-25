"""Add immutable normalized comment observation metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0004_comment_evidence_lifecycle"
down_revision = "0003_snapshot_result_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("comment_evidence")}
    timestamp_columns = ("comment_created_at", "updated_at", "retrieved_at")
    for name in timestamp_columns:
        if name not in columns:
            op.add_column(
                "comment_evidence",
                sa.Column(
                    name,
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.func.now(),
                ),
            )
            op.alter_column("comment_evidence", name, server_default=None)
    for name, default in (
        ("freshness", "stale"),
        ("availability_status", "unavailable"),
    ):
        if name not in columns:
            op.add_column(
                "comment_evidence",
                sa.Column(name, sa.String(32), nullable=False, server_default=default),
            )
            op.alter_column("comment_evidence", name, server_default=None)
    if "observation_fingerprint" not in columns:
        op.add_column(
            "comment_evidence",
            sa.Column("observation_fingerprint", sa.String(128), nullable=True),
        )
        op.execute(
            "UPDATE comment_evidence SET observation_fingerprint = md5(id::text) "
            "WHERE observation_fingerprint IS NULL"
        )
        op.alter_column("comment_evidence", "observation_fingerprint", nullable=False)
    constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("comment_evidence")
    }
    if "uq_comment_evidence_observation" not in constraints:
        op.create_unique_constraint(
            "uq_comment_evidence_observation",
            "comment_evidence",
            ["environment", "jira_comment_id", "observation_fingerprint"],
        )


def downgrade() -> None:
    op.drop_constraint(
        "uq_comment_evidence_observation", "comment_evidence", type_="unique"
    )
    for name in (
        "observation_fingerprint",
        "availability_status",
        "freshness",
        "retrieved_at",
        "updated_at",
        "comment_created_at",
    ):
        op.drop_column("comment_evidence", name)
