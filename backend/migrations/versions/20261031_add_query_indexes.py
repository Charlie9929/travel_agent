"""add query indexes from the v1.1 database design

Revision ID: 20261031_add_query_indexes
Revises: 20261031_week3_ai_run_types
Create Date: 2026-10-31
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261031_add_query_indexes"
down_revision: str | None = "20261031_week3_ai_run_types"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_trip_creator_id", "trip", ["creator_id"], unique=False)
    op.create_index("ix_trip_member_user_id", "trip_member", ["user_id"], unique=False)
    op.create_index(
        "ix_trip_revision_trip_version",
        "trip_revision",
        ["trip_id", "version"],
        unique=False,
    )
    op.create_index(
        "ix_trip_revision_resource",
        "trip_revision",
        ["resource_type", "resource_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trip_revision_resource", table_name="trip_revision")
    op.drop_index("ix_trip_revision_trip_version", table_name="trip_revision")
    op.drop_index("ix_trip_member_user_id", table_name="trip_member")
    op.drop_index("ix_trip_creator_id", table_name="trip")
