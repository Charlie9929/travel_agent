from __future__ import annotations

import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from app.core.errors import AppError
from app.integrations.amap import AmapClient


def validate_trip_rules(
    itinerary: dict[str, Any], candidate_activities: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    data = deepcopy(itinerary)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if candidate_activities:
        days = {day.get("day_index"): day for day in data.get("days", [])}
        for index, activity in enumerate(candidate_activities):
            day_number = activity.get("day_number", activity.get("day_index"))
            if day_number not in days:
                errors.append(
                    {
                        "code": "INVALID_DAY",
                        "path": f"candidate_activities.{index}.day_number",
                        "message": "候选活动不在行程日期范围内",
                    }
                )
                continue
            days[day_number].setdefault("activities", []).append(activity)

    by_day_amount: list[dict[str, Any]] = []
    total_amount = 0.0
    for day in data.get("days", []):
        day_index = day.get("day_index")
        timed: list[tuple[str, str, str]] = []
        day_amount = 0.0
        seen_ids: set[str] = set()
        for index, activity in enumerate(day.get("activities", [])):
            path = f"days.{day_index}.activities.{index}"
            activity_id = activity.get("activity_id")
            if activity_id:
                if activity_id in seen_ids:
                    errors.append(
                        {
                            "code": "DUPLICATE_ACTIVITY_ID",
                            "path": f"{path}.activity_id",
                            "message": "同一天存在重复 activity_id",
                        }
                    )
                seen_ids.add(activity_id)
            slot = activity.get("time_slot") or {}
            start = slot.get("start")
            end = slot.get("end")
            if start or end:
                if not (_valid_time(start) and _valid_time(end)):
                    errors.append(
                        {
                            "code": "INVALID_TIME",
                            "path": f"{path}.time_slot",
                            "message": "开始和结束时间必须是 HH:MM",
                        }
                    )
                elif start >= end:
                    errors.append(
                        {
                            "code": "INVALID_TIME_RANGE",
                            "path": f"{path}.time_slot",
                            "message": "结束时间必须晚于开始时间",
                        }
                    )
                else:
                    timed.append((start, end, activity_id or str(index)))
            activity_type = activity.get("type")
            location = activity.get("location") or {}
            if activity_type in {"poi", "meal", "hotel"} and not location.get("name"):
                warnings.append(
                    {
                        "code": "LOCATION_UNCONFIRMED",
                        "path": f"{path}.location",
                        "message": "地点尚未确认",
                    }
                )
            if location.get("poi_id") and location.get("poi_source") == "llm":
                errors.append(
                    {
                        "code": "UNTRUSTED_POI_ID",
                        "path": f"{path}.location.poi_id",
                        "message": "LLM 不得直接提供可用 POI ID",
                    }
                )
            cost = activity.get("cost") or {}
            amount = cost.get("amount")
            if isinstance(amount, (int, float)):
                day_amount += float(amount)
            if cost.get("price_type") == "quoted" and not cost.get("fetched_at"):
                errors.append(
                    {
                        "code": "QUOTED_PRICE_MISSING_TIMESTAMP",
                        "path": f"{path}.cost.fetched_at",
                        "message": "真实报价必须带查询时间",
                    }
                )
            quoted_cost = activity.get("quoted_cost") or {}
            if (
                quoted_cost.get("amount") is not None
                and quoted_cost.get("source") != "manual"
                and not quoted_cost.get("fetched_at")
            ):
                errors.append(
                    {
                        "code": "QUOTED_PRICE_MISSING_TIMESTAMP",
                        "path": f"{path}.quoted_cost.fetched_at",
                        "message": "外部查询价格必须带查询时间",
                    }
                )
            open_hours = activity.get("open_hours_hint") or (activity.get("extra") or {}).get(
                "open_hours_hint"
            )
            if _valid_time(start) and isinstance(open_hours, str):
                ranges = _opening_ranges(open_hours)
                if ranges and not any(
                    _time_in_range(start, item_start, item_end) for item_start, item_end in ranges
                ):
                    errors.append(
                        {
                            "code": "OUTSIDE_OPEN_HOURS",
                            "path": f"{path}.time_slot.start",
                            "message": f"活动开始时间 {start} 不在查询到的营业时段 {open_hours} 内",
                        }
                    )
        timed.sort()
        for previous, current in zip(timed, timed[1:], strict=False):
            if current[0] < previous[1]:
                errors.append(
                    {
                        "code": "TIME_OVERLAP",
                        "path": f"days.{day_index}.activities",
                        "message": f"{previous[2]} 与 {current[2]} 时间重叠",
                    }
                )
        total_amount += day_amount
        by_day_amount.append({"day_index": day_index, "amount": day_amount})

    budget = data.get("meta", {}).get("budget_total", {}).get("amount")
    if isinstance(budget, (int, float)) and budget > 0 and total_amount > float(budget):
        errors.append(
            {
                "code": "BUDGET_EXCEEDED",
                "path": "cost_summary.total_estimate",
                "message": f"预计费用 {total_amount:.2f} 超出预算 {float(budget):.2f}",
            }
        )
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "time": not any(item["code"].startswith(("TIME", "INVALID_TIME")) for item in errors),
            "budget": not any(item["code"] == "BUDGET_EXCEEDED" for item in errors),
            "location_and_source": not any(
                item["code"] in {"UNTRUSTED_POI_ID", "QUOTED_PRICE_MISSING_TIMESTAMP"}
                for item in errors
            ),
            "opening_hours": not any(item["code"] == "OUTSIDE_OPEN_HOURS" for item in errors),
        },
        "cost": {"total_estimate": total_amount, "by_day": by_day_amount},
    }


async def enrich_route_checks(
    itinerary: dict[str, Any], *, client: AmapClient
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Query real routes, persist transfer options, and verify adjacent time gaps."""
    data = deepcopy(itinerary)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    city_code = (data.get("city") or {}).get("adcode")
    for day in data.get("days", []):
        activities = day.get("activities", [])
        transfers: list[dict[str, Any]] = []
        for index, (current, following) in enumerate(zip(activities, activities[1:], strict=False)):
            origin = current.get("location") or {}
            destination = following.get("location") or {}
            if None in (
                origin.get("lat"),
                origin.get("lng"),
                destination.get("lat"),
                destination.get("lng"),
            ):
                warnings.append(
                    {
                        "code": "ROUTE_COORDINATE_MISSING",
                        "path": f"days.{day.get('day_index')}.transfers.{index}",
                        "message": "活动缺少真实坐标，无法校验交通时间",
                    }
                )
                continue
            try:
                result = await client.routes(
                    from_lng=float(origin["lng"]),
                    from_lat=float(origin["lat"]),
                    to_lng=float(destination["lng"]),
                    to_lat=float(destination["lat"]),
                    city_code=city_code,
                )
            except AppError as exc:
                warnings.append(
                    {
                        "code": "ROUTE_PROVIDER_UNAVAILABLE",
                        "path": f"days.{day.get('day_index')}.transfers.{index}",
                        "message": f"真实路线暂时无法查询：{exc.message}",
                    }
                )
                continue
            queried_at = result.get("queried_at")
            if isinstance(queried_at, datetime):
                queried_at = queried_at.astimezone(UTC).isoformat()
            options = [
                {
                    "mode": mode,
                    "distance_km": round(float(route.get("distance_m", 0)) / 1000, 2),
                    "duration_min": int(route.get("duration_min") or 0),
                    "transit_count": route.get("transit_count"),
                    "source": "amap",
                    "fetched_at": queried_at,
                }
                for mode, route in (result.get("routes") or {}).items()
                if route.get("available")
            ]
            transfers.append(
                {
                    "from_activity_id": current.get("activity_id"),
                    "to_activity_id": following.get("activity_id"),
                    "options": options,
                }
            )
            durations = [item["duration_min"] for item in options if item["duration_min"] > 0]
            current_end = (current.get("time_slot") or {}).get("end")
            next_start = (following.get("time_slot") or {}).get("start")
            if durations and _valid_time(current_end) and _valid_time(next_start):
                available_gap = _minutes(next_start) - _minutes(current_end)
                if available_gap >= 0 and min(durations) > available_gap:
                    route_minutes = min(durations)
                    errors.append(
                        {
                            "code": "ROUTE_TIME_INFEASIBLE",
                            "path": f"days.{day.get('day_index')}.activities.{index + 1}",
                            "message": (
                                f"从“{current.get('title')}”到“{following.get('title')}”"
                                f"最快约 {route_minutes} 分钟，但只预留了 {available_gap} 分钟"
                            ),
                        }
                    )
        day["transfers"] = transfers
    return data, errors, warnings


def _valid_time(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError:
        return False
    return True


def _minutes(value: str) -> int:
    hour, minute = value.split(":", maxsplit=1)
    return int(hour) * 60 + int(minute)


def _opening_ranges(value: str) -> list[tuple[str, str]]:
    """Parse common AMap ranges such as 09:00-18:00 without guessing prose."""
    return [
        (f"{start_hour}:{start_minute}", f"{end_hour}:{end_minute}")
        for start_hour, start_minute, end_hour, end_minute in re.findall(
            r"([01]\d|2[0-3]):([0-5]\d)\s*[-~至—]\s*([01]\d|2[0-3]):([0-5]\d)",
            value,
        )
    ]


def _time_in_range(value: str, start: str, end: str) -> bool:
    current = _minutes(value)
    start_minute = _minutes(start)
    end_minute = _minutes(end)
    if end_minute >= start_minute:
        return start_minute <= current <= end_minute
    return current >= start_minute or current <= end_minute
