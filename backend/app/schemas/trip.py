from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.activity import ActivityRead


class TripCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    city: str = Field(min_length=1, max_length=50)
    city_adcode: str = Field(pattern=r"^\d{6}$")
    start_date: date
    end_date: date
    total_budget: Decimal | None = Field(default=None, ge=0)
    origin_city: str = Field(min_length=1, max_length=50)
    origin_city_adcode: str = Field(pattern=r"^\d{6}$")
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
    city_adcode: str | None = Field(default=None, pattern=r"^\d{6}$")
    start_date: date | None = None
    end_date: date | None = None
    total_budget: Decimal | None = Field(default=None, ge=0)
    origin_city: str | None = Field(default=None, max_length=50)
    origin_city_adcode: str | None = Field(default=None, pattern=r"^\d{6}$")
    traveler_count: int | None = Field(default=None, gt=0)
    preferences: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern=r"^(draft|ongoing|finished)$")
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_location_pairs(self) -> "TripUpdate":
        if (self.city is None) != (self.city_adcode is None):
            raise ValueError("city 与 city_adcode 必须同时修改")
        if (self.origin_city is None) != (self.origin_city_adcode is None):
            raise ValueError("origin_city 与 origin_city_adcode 必须同时修改")
        return self


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
    city_adcode: str | None
    origin_city_adcode: str | None
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


class TripRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    resource_id: int | None
    user_id: int
    user_nickname: str | None = None
    version: int
    action: str
    diff_content: dict[str, Any]
    resource_type: str
    created_at: datetime
    summary: str | None = None
    before: Any | None = None
    after: Any | None = None
    changes: list[dict[str, Any]] = Field(default_factory=list)


class CollaborationNoteUpdate(BaseModel):
    content: str = Field(default="", max_length=5000)


class CollaborationNoteRead(BaseModel):
    content: str = ""
    updated_by_nickname: str | None = None
    updated_at: datetime | None = None


class TripValidationRequest(BaseModel):
    candidate_activities: list[dict[str, Any]] | None = None
