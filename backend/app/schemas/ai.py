from typing import Any

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    trip_id: int
    additional_requirements: str | None = Field(default=None, max_length=4000)


class LLMResultSchema(BaseModel):
    parsed_data: dict[str, Any]
    raw_text: str
    model: str
    prompt_version: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int
    request_id: str
