"""add canonical city adcodes to trips

Revision ID: 20261115_trip_city_adcodes
Revises: 20261113_agent_workflow
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261115_trip_city_adcodes"
down_revision: str | None = "20261113_agent_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trip", sa.Column("city_adcode", sa.String(length=6), nullable=True))
    op.add_column(
        "trip", sa.Column("origin_city_adcode", sa.String(length=6), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("trip", "origin_city_adcode")
    op.drop_column("trip", "city_adcode")
