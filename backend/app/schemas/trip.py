from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.activity import ActivityRead


class TripCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    city: str = Field(min_length=1, max_length=50)
    start_date: date
    end_date: date
    total_budget: Decimal | None = Field(default=None, ge=0)
    origin_city: str | None = Field(default=None, max_length=50)
    traveler_count: int | None = Field(default=None, gt=0)
    preferences: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dates(self) -> "TripCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date 不能早于 start_date")
        return self


class TripUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    city: str | None = Field(default=None, min_length=1, max_length=50)
    start_date: date | None = None
    end_date: date | None = None
    total_budget: Decimal | None = Field(default=None, ge=0)
    origin_city: str | None = Field(default=None, max_length=50)
    traveler_count: int | None = Field(default=None, gt=0)
    preferences: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern=r"^(draft|ongoing|finished)$")
    version: int = Field(ge=1)


class TripRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_trip_id: UUID
    title: str
    city: str
    start_date: date
    end_date: date
    total_budget: Decimal | None
    creator_id: int
    version: int
    status: str
    origin_city: str | None
    traveler_count: int | None
    preferences: dict[str, Any]
    constraints: dict[str, Any]
    last_editor_id: int | None
    created_at: datetime
    updated_at: datetime


class TripDayRead(BaseModel):
    day_number: int
    date: date
    activities: list[ActivityRead]


class TripDetail(TripRead):
    days: list[TripDayRead]


class TripList(BaseModel):
    items: list[TripRead]
    page: int
    page_size: int


class TripDeleteRequest(BaseModel):
    version: int = Field(ge=1)
