from datetime import datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActivityFields(BaseModel):
    day_number: int = Field(ge=1)
    order_index: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=100)
    type: str = Field(pattern=r"^(sight|food|hotel|transport|other)$")
    start_time: time | None = None
    duration_min: int | None = Field(default=None, gt=0)
    location_name: str | None = Field(default=None, max_length=200)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    price_estimated: Decimal | None = Field(default=None, ge=0)
    price_real: Decimal | None = Field(default=None, ge=0)
    price_source: str | None = Field(default=None, max_length=100)
    description: str | None = None
    poi_provider: str | None = Field(default=None, max_length=20)
    poi_id: str | None = Field(default=None, max_length=100)
    extra: dict[str, Any] = Field(default_factory=dict)


class ActivityCreate(ActivityFields):
    agent_activity_id: str | None = Field(default=None, max_length=50)
    trip_version: int = Field(ge=1)


class ActivityUpdate(BaseModel):
    day_number: int | None = Field(default=None, ge=1)
    order_index: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=100)
    type: str | None = Field(default=None, pattern=r"^(sight|food|hotel|transport|other)$")
    start_time: time | None = None
    duration_min: int | None = Field(default=None, gt=0)
    location_name: str | None = Field(default=None, max_length=200)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    price_estimated: Decimal | None = Field(default=None, ge=0)
    price_real: Decimal | None = Field(default=None, ge=0)
    price_source: str | None = Field(default=None, max_length=100)
    description: str | None = None
    poi_provider: str | None = Field(default=None, max_length=20)
    poi_id: str | None = Field(default=None, max_length=100)
    extra: dict[str, Any] | None = None
    trip_version: int = Field(ge=1)


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_activity_id: str
    trip_id: int
    day_number: int
    order_index: int
    title: str
    type: str
    start_time: time | None
    duration_min: int | None
    location_name: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    price_estimated: Decimal | None
    price_real: Decimal | None
    price_source: str | None
    description: str | None
    poi_provider: str | None
    poi_id: str | None
    extra: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ActivityDeleteRequest(BaseModel):
    trip_version: int = Field(ge=1)


class ActivityReorderRequest(BaseModel):
    day_number: int = Field(ge=1)
    id_order: list[int] = Field(min_length=1)
    trip_version: int = Field(ge=1)
