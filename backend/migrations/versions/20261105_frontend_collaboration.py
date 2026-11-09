"""add frontend collaboration capabilities

Revision ID: 20261105_frontend_collaboration
Revises: 20261031_add_query_indexes
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261105_frontend_collaboration"
down_revision: str | None = "20261031_add_query_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lobby_message",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("trip_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_id", sa.BigInteger(), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(20), server_default="trip", nullable=False),
        sa.Column("reply_to_id", sa.BigInteger(), nullable=True),
        sa.Column("structured_data", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('user','agent','system')", name=op.f("ck_lobby_message_kind_enum")
        ),
        sa.CheckConstraint("visibility = 'trip'", name=op.f("ck_lobby_message_visibility_enum")),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reply_to_id"], ["lobby_message.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lobby_message_trip_id_id", "lobby_message", ["trip_id", "id"])

    op.create_table(
        "lobby_read_state",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("trip_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("last_read_message_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["last_read_message_id"], ["lobby_message.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", "user_id"),
    )

    op.create_table(
        "agent_conversation",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("trip_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", "user_id"),
    )

    op.create_table(
        "agent_chat_message",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), server_default="succeeded", nullable=False),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "role IN ('user','assistant')", name=op.f("ck_agent_chat_message_role_enum")
        ),
        sa.CheckConstraint(
            "status IN ('pending','succeeded','failed')",
            name=op.f("ck_agent_chat_message_status_enum"),
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["agent_conversation.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_chat_message_conversation_id_id",
        "agent_chat_message",
        ["conversation_id", "id"],
    )

    op.create_table(
        "travel_requirement",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("trip_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("content", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("filled_by", sa.BigInteger(), nullable=True),
        sa.Column("shared_summary", sa.Text(), nullable=True),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending','completed')", name=op.f("ck_travel_requirement_status_enum")
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["filled_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", "user_id"),
    )

    op.create_table(
        "user_memory",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(20), server_default="private", nullable=False),
        sa.Column("authorized_trip_ids", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "visibility IN ('private','shared')", name=op.f("ck_user_memory_visibility_enum")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_memory_user_id", "user_memory", ["user_id"])

    op.create_table(
        "trip_highlight",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("trip_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trip_highlight_trip_id", "trip_highlight", ["trip_id"])


def downgrade() -> None:
    op.drop_index("ix_trip_highlight_trip_id", table_name="trip_highlight")
    op.drop_table("trip_highlight")
    op.drop_index("ix_user_memory_user_id", table_name="user_memory")
    op.drop_table("user_memory")
    op.drop_table("travel_requirement")
    op.drop_index("ix_agent_chat_message_conversation_id_id", table_name="agent_chat_message")
    op.drop_table("agent_chat_message")
    op.drop_table("agent_conversation")
    op.drop_table("lobby_read_state")
    op.drop_index("ix_lobby_message_trip_id_id", table_name="lobby_message")
    op.drop_table("lobby_message")
