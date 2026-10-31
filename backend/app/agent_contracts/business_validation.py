"""接入技术一维护的 Week 3 业务校验器。"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

from app.core.errors import AppError

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VALIDATORS_ROOT = REPOSITORY_ROOT / "docs" / "schemas" / "validators"


@lru_cache
def _load_validator_module(module_name: str) -> ModuleType:
    path = VALIDATORS_ROOT / f"{module_name}.py"
    if not path.is_file():
        raise AppError(
            "AGENT_VALIDATOR_UNAVAILABLE",
            f"业务校验器 {module_name} 不存在",
            status_code=500,
        )
    spec = importlib.util.spec_from_file_location(f"travel_agent_{module_name}", path)
    if spec is None or spec.loader is None:
        raise AppError(
            "AGENT_VALIDATOR_UNAVAILABLE",
            f"业务校验器 {module_name} 无法加载",
            status_code=500,
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_replan_candidate(
    old_itinerary: dict[str, Any],
    candidate: dict[str, Any],
    *,
    day_number: int,
    after_time: str | None,
) -> None:
    proposed = candidate.get("proposed_itinerary")
    diff = candidate.get("diff")
    shape_errors: list[dict[str, Any]] = []
    if not isinstance(candidate.get("summary"), str):
        shape_errors.append({"code": "SUMMARY_MISSING", "message": "缺少 summary"})
    if not isinstance(proposed, dict):
        shape_errors.append(
            {"code": "PROPOSED_ITINERARY_MISSING", "message": "缺少 proposed_itinerary"}
        )
    if not isinstance(diff, dict) or not isinstance(diff.get("ops"), list):
        shape_errors.append({"code": "DIFF_INVALID", "message": "diff.ops 必须是数组"})
    if shape_errors:
        raise AppError(
            "AGENT_OUTPUT_INVALID",
            "重排行程候选不符合契约",
            status_code=502,
            detail=shape_errors,
        )

    activity_validator: Callable[..., list[dict[str, Any]]] = _load_validator_module(
        "activity_id_validator"
    ).validate_activity_id_stability
    diff_validator: Callable[..., list[dict[str, Any]]] = _load_validator_module(
        "diff_scope_validator"
    ).validate_diff_scope
    errors = activity_validator(
        old_itinerary,
        proposed,
        scope_day_index=day_number,
        after_time=after_time,
    )
    errors.extend(
        diff_validator(diff, scope_day_index=day_number, after_time=after_time)
    )
    if errors:
        raise AppError(
            "AGENT_OUTPUT_INVALID",
            "重排行程候选未通过业务校验",
            status_code=502,
            detail=errors,
        )


def validate_revision_candidate(
    old_itinerary: dict[str, Any], candidate: dict[str, Any]
) -> None:
    proposed = candidate.get("proposed_itinerary")
    diff = candidate.get("diff")
    shape_errors: list[dict[str, Any]] = []
    if not isinstance(candidate.get("summary"), str):
        shape_errors.append({"code": "SUMMARY_MISSING", "message": "缺少 summary"})
    if not isinstance(proposed, dict):
        shape_errors.append(
            {"code": "PROPOSED_ITINERARY_MISSING", "message": "缺少 proposed_itinerary"}
        )
    if not isinstance(diff, dict) or not isinstance(diff.get("ops"), list):
        shape_errors.append({"code": "DIFF_INVALID", "message": "diff.ops 必须是数组"})
    if shape_errors:
        raise AppError(
            "AGENT_OUTPUT_INVALID",
            "行程修订候选不符合契约",
            status_code=502,
            detail=shape_errors,
        )

    activity_validator: Callable[..., list[dict[str, Any]]] = _load_validator_module(
        "activity_id_validator"
    ).validate_activity_id_stability
    diff_validator: Callable[..., list[dict[str, Any]]] = _load_validator_module(
        "diff_scope_validator"
    ).validate_diff_scope
    errors = activity_validator(old_itinerary, proposed)
    errors.extend(diff_validator(diff))
    if errors:
        raise AppError(
            "AGENT_OUTPUT_INVALID",
            "行程修订候选未通过业务校验",
            status_code=502,
            detail=errors,
        )
