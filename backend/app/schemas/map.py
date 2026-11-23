from typing import Literal

from pydantic import BaseModel, Field

RouteMode = Literal["walk", "bike", "drive", "transit"]


class RouteSegmentRequest(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    from_lat: float = Field(ge=-90, le=90)
    from_lng: float = Field(ge=-180, le=180)
    to_lat: float = Field(ge=-90, le=90)
    to_lng: float = Field(ge=-180, le=180)
    city_code: str | None = Field(default=None, max_length=20)
    modes: list[RouteMode] = Field(default_factory=lambda: ["drive"])


class RouteBatchRequest(BaseModel):
    segments: list[RouteSegmentRequest] = Field(min_length=1, max_length=100)
