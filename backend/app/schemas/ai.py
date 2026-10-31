from datetime import time
from typing import Any, Literal

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    trip_id: int
    additional_requirements: str | None = Field(default=None, max_length=4000)


class ReplanRequest(BaseModel):
    trip_id: int
    day_number: int = Field(ge=1)
    adjustment_requirements: str = Field(min_length=1, max_length=4000)
    trip_version: int = Field(ge=1)
    after_time: time | None = None
    trigger: dict[str, Any] = Field(default_factory=dict)
    candidate_replacements: list[dict[str, Any]] = Field(default_factory=list)


class ReviseRequest(BaseModel):
    trip_id: int
    changed_constraints: dict[str, Any]
    user_instruction: str | None = Field(default=None, max_length=4000)
    trip_version: int = Field(ge=1)


class ExplainDiffRequest(BaseModel):
    trip_id: int
    mode: Literal["explain", "conflict"] = "explain"
    old_itinerary: dict[str, Any]
    new_itinerary: dict[str, Any] | list[dict[str, Any]]
    teammate_itinerary: dict[str, Any] | None = None


class ImportGuideRequest(BaseModel):
    trip_id: int
    text: str = Field(min_length=1, max_length=20_000)


class ApplyAiRunRequest(BaseModel):
    trip_version: int = Field(ge=1)
    apply_mode: Literal["replace_itinerary", "append_selected"] = "replace_itinerary"
    selected_candidate_ids: list[str] = Field(default_factory=list)


class LLMResultSchema(BaseModel):
    parsed_data: dict[str, Any]
    raw_text: str
    model: str
    prompt_version: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int
    request_id: str
