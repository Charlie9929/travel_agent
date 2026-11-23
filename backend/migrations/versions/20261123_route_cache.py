"""Add persistent route cache for batched map loading.

Revision ID: 20261123_route_cache
Revises: 20261118_municipalities
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261123_route_cache"
down_revision: str | None = "20261118_municipalities"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "route_cache",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("origin_lat_key", sa.String(length=32), nullable=False),
        sa.Column("origin_lng_key", sa.String(length=32), nullable=False),
        sa.Column("destination_lat_key", sa.String(length=32), nullable=False),
        sa.Column("destination_lng_key", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("city_code", sa.String(length=20), nullable=True),
        sa.Column("strategy", sa.String(length=50), server_default="default", nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("provider", sa.String(length=30), server_default="amap", nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "origin_lat_key", "origin_lng_key", "destination_lat_key", "destination_lng_key",
            "mode", "city_code", "strategy", name="uq_route_cache_lookup",
        ),
    )
    op.create_index("ix_route_cache_expires_at", "route_cache", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_route_cache_expires_at", table_name="route_cache")
    op.drop_table("route_cache")
