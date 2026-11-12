"""link travel records to activities and add record images

Revision ID: 20261112_activity_records
Revises: 20261105_frontend_collaboration
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261112_activity_records"
down_revision: str | None = "20261105_frontend_collaboration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trip_highlight", sa.Column("activity_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_trip_highlight_activity_id_day_activity"),
        "trip_highlight",
        "day_activity",
        ["activity_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_trip_highlight_activity_id", "trip_highlight", ["activity_id"])

    op.create_table(
        "trip_highlight_media",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("highlight_id", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by", sa.BigInteger(), nullable=False),
        sa.Column("file_url", sa.String(500), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(50), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 8388608",
            name=op.f("ck_trip_highlight_media_size_limit"),
        ),
        sa.CheckConstraint(
            "sort_order >= 1 AND sort_order <= 3",
            name=op.f("ck_trip_highlight_media_sort_order_range"),
        ),
        sa.ForeignKeyConstraint(
            ["highlight_id"], ["trip_highlight.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("highlight_id", "sort_order"),
    )
    op.create_index(
        "ix_trip_highlight_media_highlight_id",
        "trip_highlight_media",
        ["highlight_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_trip_highlight_media_highlight_id", table_name="trip_highlight_media")
    op.drop_table("trip_highlight_media")
    op.drop_index("ix_trip_highlight_activity_id", table_name="trip_highlight")
    op.drop_constraint(
        op.f("fk_trip_highlight_activity_id_day_activity"),
        "trip_highlight",
        type_="foreignkey",
    )
    op.drop_column("trip_highlight", "activity_id")
