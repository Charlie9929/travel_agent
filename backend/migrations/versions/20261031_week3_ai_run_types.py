"""add week 3 ai run types

Revision ID: 20261031_week3_ai_run_types
Revises: 131e96243665
Create Date: 2026-10-31
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261031_week3_ai_run_types"
down_revision: str | None = "131e96243665"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_ai_run_log_run_type_enum"), "ai_run_log", type_="check")
    op.create_check_constraint(
        op.f("ck_ai_run_log_run_type_enum"),
        "ai_run_log",
        "run_type IN ('generate','revise','replan','explain_diff','import_guide')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_ai_run_log_run_type_enum"), "ai_run_log", type_="check")
    op.create_check_constraint(
        op.f("ck_ai_run_log_run_type_enum"),
        "ai_run_log",
        "run_type IN ('generate','replan','import_guide')",
    )
