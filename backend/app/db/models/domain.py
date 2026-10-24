from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(255))
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class Trip(TimestampMixin, Base):
    __tablename__ = "trip"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="date_range"),
        CheckConstraint("total_budget IS NULL OR total_budget >= 0", name="budget_nonnegative"),
        CheckConstraint(
            "traveler_count IS NULL OR traveler_count > 0", name="traveler_count_positive"
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("status IN ('draft','ongoing','finished')", name="status_enum"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    agent_trip_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), unique=True, nullable=False, default=uuid4
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(50), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_budget: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    share_code: Mapped[str | None] = mapped_column(String(32), unique=True)
    share_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    origin_city: Mapped[str | None] = mapped_column(String(50))
    traveler_count: Mapped[int | None] = mapped_column(Integer)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    constraints: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    last_editor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class TripMember(Base):
    __tablename__ = "trip_member"
    __table_args__ = (
        UniqueConstraint("trip_id", "user_id"),
        CheckConstraint("role IN ('owner','editor','viewer')", name="role_enum"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trip.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class DayActivity(TimestampMixin, Base):
    __tablename__ = "day_activity"
    __table_args__ = (
        UniqueConstraint("trip_id", "agent_activity_id", name="uq_day_activity_agent_activity"),
        UniqueConstraint("trip_id", "day_number", "order_index", name="uq_day_activity_day_order"),
        CheckConstraint("day_number >= 1", name="day_positive"),
        CheckConstraint("order_index >= 1", name="order_positive"),
        CheckConstraint("duration_min IS NULL OR duration_min > 0", name="duration_positive"),
        CheckConstraint(
            "price_estimated IS NULL OR price_estimated >= 0", name="estimated_price_nonnegative"
        ),
        CheckConstraint("price_real IS NULL OR price_real >= 0", name="real_price_nonnegative"),
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180", name="longitude_range"
        ),
        CheckConstraint("type IN ('sight','food','hotel','transport','other')", name="type_enum"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    agent_activity_id: Mapped[str] = mapped_column(String(50), nullable=False)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trip.id", ondelete="CASCADE"), nullable=False)
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time)
    duration_min: Mapped[int | None] = mapped_column(Integer)
    location_name: Mapped[str | None] = mapped_column(String(200))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    price_estimated: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    price_real: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    price_source: Mapped[str | None] = mapped_column(String(100))
    price_queried_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    currency: Mapped[str] = mapped_column(String(3), default="CNY", server_default="CNY")
    description: Mapped[str | None] = mapped_column(Text)
    poi_provider: Mapped[str | None] = mapped_column(String(20))
    poi_id: Mapped[str | None] = mapped_column(String(100))
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class Expense(TimestampMixin, Base):
    __tablename__ = "expense"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("split_type IN ('equal','ratio')", name="split_type_enum"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trip.id", ondelete="CASCADE"), nullable=False)
    activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("day_activity.id", ondelete="SET NULL")
    )
    payer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    split_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_settled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class ExpenseSplit(Base):
    __tablename__ = "expense_split"
    __table_args__ = (
        UniqueConstraint("expense_id", "user_id"),
        CheckConstraint("ratio > 0 AND ratio <= 1", name="ratio_range"),
        CheckConstraint("should_pay >= 0", name="should_pay_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expense.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    should_pay: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)


class TripRevision(Base):
    __tablename__ = "trip_revision"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trip.id", ondelete="CASCADE"), nullable=False)
    resource_id: Mapped[int | None] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    diff_content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EditConflict(Base):
    __tablename__ = "edit_conflict"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trip.id", ondelete="CASCADE"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)
    resource_id: Mapped[int | None] = mapped_column(BigInteger)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    base_version: Mapped[int] = mapped_column(Integer, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    current_content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiRunLog(Base):
    __tablename__ = "ai_run_log"
    __table_args__ = (
        CheckConstraint("run_type IN ('generate','replan','import_guide')", name="run_type_enum"),
        CheckConstraint(
            "status IN ('running','succeeded','failed','discarded','applied')",
            name="status_enum",
        ),
        CheckConstraint("retry_count >= 0", name="retry_count_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trip.id", ondelete="CASCADE"), nullable=False)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    run_type: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    candidate_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(50))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
