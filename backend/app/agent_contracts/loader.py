import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from app.core.errors import AppError

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent
SCHEMA_PATH = Path(__file__).with_name("itinerary.schema.json")
PROMPTS_ROOT = BACKEND_ROOT / "prompts"
SHARED_PROMPTS_ROOT = REPOSITORY_ROOT / "docs" / "prompts"

SHARED_PROMPT_FILES = {
    "itinerary-generation": "行程生成Prompt-{version}.md",
    "import-guide": "攻略抽取Prompt-{version}.md",
    "revise-itinerary": "修订Prompt-{version}.md",
    "replan-day": "行中重排Prompt-{version}.md",
    "explain-diff": "差异说明Prompt-{version}.md",
}


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


@lru_cache
def load_shared_prompt(prompt_id: str, version: str) -> str:
    """读取技术一维护的 Prompt，并只提取其中的 System Prompt 代码块。"""
    pattern = SHARED_PROMPT_FILES.get(prompt_id)
    if pattern is None:
        raise AppError("PROMPT_NOT_FOUND", f"未知 Prompt {prompt_id}", status_code=500)
    path = SHARED_PROMPTS_ROOT / pattern.format(version=version)
    if not path.is_file():
        raise AppError(
            "PROMPT_NOT_FOUND",
            f"Prompt {prompt_id}/{version} 不存在",
            status_code=500,
        )
    content = path.read_text(encoding="utf-8")
    match = re.search(
        r"##\s+\d+\.\s+System Prompt.*?```(?:text)?\s*\n(.*?)```",
        content,
        flags=re.DOTALL,
    )
    if match is None:
        raise AppError(
            "PROMPT_FORMAT_INVALID",
            f"Prompt {prompt_id}/{version} 缺少 System Prompt 代码块",
            status_code=500,
        )
    return match.group(1).strip()


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
