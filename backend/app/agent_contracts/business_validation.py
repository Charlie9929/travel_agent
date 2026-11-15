"""接入技术一维护的 Week 3 业务校验器。"""

from __future__ import annotations

import importlib.util
import re
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

from app.core.errors import AppError

LUNCH_DAY_START = 11 * 60 + 30
LUNCH_DAY_END = 13 * 60 + 30
LUNCH_WORD_RE = re.compile(r"午餐|午饭|中饭|中餐|午间用餐|午间简餐")
PARK_DAY_RE = re.compile(
    r"乐园|迪士尼|度假区|动物园|动物世界|海洋王国|水上王国|欢乐谷|环球影城|方特|园区"
)


def _clock_minutes(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    parts = value.split(":")
    if len(parts) < 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return hour * 60 + minute if 0 <= hour <= 23 and 0 <= minute <= 59 else None


def lunch_requirement_errors(itinerary: dict[str, Any]) -> list[dict[str, Any]]:
    """Require lunch on days spanning midday, except a long in-park visit."""
    errors: list[dict[str, Any]] = []
    for day_position, day in enumerate(itinerary.get("days") or []):
        activities = [
            item
            for item in day.get("activities") or []
            if isinstance(item, dict) and item.get("status") != "removed"
        ]
        timed: list[tuple[dict[str, Any], int, int]] = []
        for activity in activities:
            slot = activity.get("time_slot") or {}
            start = _clock_minutes(slot.get("start"))
            end = _clock_minutes(slot.get("end"))
            if start is not None and end is not None and end > start:
                timed.append((activity, start, end))
        if not timed:
            continue
        day_spans_lunch = (
            min(start for _, start, _ in timed) <= LUNCH_DAY_START
            and max(end for _, _, end in timed) >= LUNCH_DAY_END
        )
        if not day_spans_lunch:
            continue
        has_lunch = any(
            activity.get("type") == "meal"
            and LUNCH_WORD_RE.search(
                " ".join(
                    str(value or "")
                    for value in (
                        activity.get("title"),
                        (activity.get("location") or {}).get("name"),
                        activity.get("note"),
                    )
                )
            )
            for activity in activities
        )
        if has_lunch:
            continue
        has_all_day_park = any(
            activity.get("type") in {"poi", "free_time"}
            and start <= LUNCH_DAY_START
            and end >= LUNCH_DAY_END
            and (end - start >= 180 or "全天" in str(activity.get("title") or ""))
            and PARK_DAY_RE.search(
                " ".join(
                    str(value or "")
                    for value in (
                        activity.get("title"),
                        (activity.get("location") or {}).get("name"),
                        activity.get("note"),
                    )
                )
            )
            for activity, start, end in timed
        )
        if not has_all_day_park:
            errors.append(
                {
                    "code": "MISSING_LUNCH",
                    "path": f"days.{day_position}.activities",
                    "day_index": day.get("day_index", day_position + 1),
                    "message": (
                        "当天行程跨越午餐时段，必须安排标题或说明明确包含午餐、午饭、"
                        "中饭等字样的用餐活动；仅全天在同一园区游玩时可省略"
                    ),
                }
            )
    return errors


def _new_lunch_errors(
    old_itinerary: dict[str, Any], proposed_itinerary: dict[str, Any]
) -> list[dict[str, Any]]:
    old_missing_days = {
        item.get("day_index") for item in lunch_requirement_errors(old_itinerary)
    }
    return [
        item
        for item in lunch_requirement_errors(proposed_itinerary)
        if item.get("day_index") not in old_missing_days
    ]

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
    errors.extend(_new_lunch_errors(old_itinerary, proposed))
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
    errors.extend(_new_lunch_errors(old_itinerary, proposed))
    if errors:
        raise AppError(
            "AGENT_OUTPUT_INVALID",
            "行程修订候选未通过业务校验",
            status_code=502,
            detail=errors,
        )
