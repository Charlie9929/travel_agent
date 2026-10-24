import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from app.core.errors import AppError

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = Path(__file__).with_name("itinerary.schema.json")
PROMPTS_ROOT = BACKEND_ROOT / "prompts"


@lru_cache
def load_itinerary_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_prompt(prompt_id: str, version: str) -> str:
    path = PROMPTS_ROOT / prompt_id / f"{version}.md"
    if not path.is_file():
        raise AppError(
            "PROMPT_NOT_FOUND",
            f"Prompt {prompt_id}/{version} 不存在",
            status_code=500,
        )
    return path.read_text(encoding="utf-8")


def validate_itinerary(data: dict[str, Any]) -> None:
    validator = Draft202012Validator(load_itinerary_schema(), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path))
    if not errors:
        return
    detail = [
        {"path": ".".join(str(part) for part in error.absolute_path), "message": error.message}
        for error in errors
    ]
    raise AppError("AGENT_OUTPUT_INVALID", "行程 JSON 不符合契约", status_code=502, detail=detail)
