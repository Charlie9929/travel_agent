from __future__ import annotations

import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from app.core.errors import AppError
from app.integrations.amap import AmapClient
from app.services.poi_enrichment import poi_unavailable_reason


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
            location = activity.get("location") or {}
            if not location.get("name"):
                errors.append(
                    {
                        "code": "LOCATION_UNCONFIRMED",
                        "path": f"{path}.location",
                        "message": "每个活动都必须有具体地点",
                    }
                )
            elif (
                location.get("poi_source") != "amap"
                or not location.get("poi_id")
                or location.get("lng") is None
                or location.get("lat") is None
            ):
                errors.append(
                    {
                        "code": "LOCATION_UNVERIFIED",
                        "path": f"{path}.location",
                        "message": "地点必须经过高德查证并包含 POI ID 与坐标",
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
            unavailable_reason = poi_unavailable_reason(
                {
                    "name": location.get("name"),
                    "business_status": location.get("business_status"),
                    "open_hours": activity.get("open_hours_hint"),
                }
            )
            if unavailable_reason:
                errors.append(
                    {
                        "code": "POI_UNAVAILABLE",
                        "path": f"{path}.location.name",
                        "message": f"地点已标记为“{unavailable_reason}”，不能排入行程",
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
            if (
                activity.get("type") != "transport"
                and _valid_time(start)
                and isinstance(open_hours, str)
            ):
                ranges = _opening_ranges(open_hours)
                if ranges and not _activity_fits_open_hours(start, end, ranges):
                    errors.append(
                        {
                            "code": "OUTSIDE_OPEN_HOURS",
                            "path": f"{path}.time_slot.start",
                            "message": (
                                f"活动时段 {start}-{end} 不在查询到的营业时段 {open_hours} 内"
                            ),
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
                item["code"]
                in {
                    "LOCATION_UNCONFIRMED",
                    "LOCATION_UNVERIFIED",
                    "UNTRUSTED_POI_ID",
                    "POI_UNAVAILABLE",
                    "QUOTED_PRICE_MISSING_TIMESTAMP",
                }
                for item in errors
            ),
            "opening_hours": not any(item["code"] == "OUTSIDE_OPEN_HOURS" for item in errors),
        },
        "cost": {"total_estimate": total_amount, "by_day": by_day_amount},
    }


async def enrich_route_checks(
    itinerary: dict[str, Any], *, client: AmapClient, reschedule: bool = False
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Query real routes, persist transfers, and optionally assign exact clock times."""
    data = deepcopy(itinerary)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    city_code = (data.get("city") or {}).get("adcode")
    for day in data.get("days", []):
        activities = day.get("activities", [])
        transfers: list[dict[str, Any]] = []
        original_slots = [deepcopy(activity.get("time_slot")) for activity in activities]
        schedule_failed = False
        if reschedule and activities:
            first_slot = activities[0].get("time_slot") or {}
            first_start = first_slot.get("start")
            if _valid_time(first_start):
                schedule_error = _reschedule_activity(
                    activities[0], earliest_start=_minutes(first_start)
                )
                if schedule_error:
                    schedule_failed = True
                    errors.append(
                        {
                            "code": schedule_error[0],
                            "path": f"days.{day.get('day_index')}.activities.0",
                            "message": schedule_error[1],
                        }
                    )
        for index, (current, following) in enumerate(zip(activities, activities[1:], strict=False)):
            if schedule_failed:
                break
            origin = current.get("location") or {}
            destination = following.get("location") or {}
            durations: list[int] = []
            explicit_transport = (
                current.get("type") == "transport" or following.get("type") == "transport"
            )
            if explicit_transport:
                # The transport activity itself already owns the movement duration.
                # Querying another route beside it would count the same trip twice.
                pass
            elif None in (
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
            else:
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
                    result = None
                if result is not None:
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
                    durations = [
                        item["duration_min"] for item in options if item["duration_min"] > 0
                    ]

            current_end = (current.get("time_slot") or {}).get("end")
            next_start = (following.get("time_slot") or {}).get("start")
            if reschedule and _valid_time(current_end) and _valid_time(next_start):
                travel_and_buffer = (
                    0
                    if explicit_transport
                    else min(durations) + 15
                    if durations
                    else 30
                )
                earliest_start = max(
                    _minutes(next_start), _minutes(current_end) + travel_and_buffer
                )
                schedule_error = _reschedule_activity(following, earliest_start=earliest_start)
                if schedule_error:
                    schedule_failed = True
                    errors.append(
                        {
                            "code": schedule_error[0],
                            "path": f"days.{day.get('day_index')}.activities.{index + 1}",
                            "message": schedule_error[1],
                        }
                    )
                    break
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
        if schedule_failed:
            # Do not return a half-rescheduled day. Otherwise later validation reports
            # misleading overlaps between shifted and still-original activities.
            for activity, original_slot in zip(activities, original_slots, strict=True):
                activity["time_slot"] = original_slot
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


def _format_minutes(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def _opening_ranges(value: str) -> list[tuple[str, str]]:
    """Parse AMap ranges, including its common all-day marker 00:00-24:00."""
    ranges: list[tuple[str, str]] = []
    for start_hour, start_minute, end_hour, end_minute in re.findall(
        r"(\d{1,2}):(\d{2})\s*[-~至—]\s*(\d{1,2}):(\d{2})", value
    ):
        start_h, start_m = int(start_hour), int(start_minute)
        end_h, end_m = int(end_hour), int(end_minute)
        if not (0 <= start_h <= 23 and 0 <= start_m <= 59):
            continue
        if not (0 <= end_h <= 24 and 0 <= end_m <= 59):
            continue
        if end_h == 24 and end_m != 0:
            continue
        ranges.append((f"{start_h:02d}:{start_m:02d}", f"{end_h:02d}:{end_m:02d}"))
    return ranges


def _reschedule_activity(
    activity: dict[str, Any], *, earliest_start: int
) -> tuple[str, str] | None:
    slot = activity.get("time_slot") or {}
    start = slot.get("start")
    end = slot.get("end")
    if not (_valid_time(start) and _valid_time(end)):
        return None
    duration = max(_minutes(end) - _minutes(start), 30)
    open_hours = None
    if activity.get("type") != "transport":
        open_hours = activity.get("open_hours_hint") or (activity.get("extra") or {}).get(
            "open_hours_hint"
        )
    ranges = _opening_ranges(open_hours) if isinstance(open_hours, str) else []
    scheduled_start = _next_open_start(earliest_start, duration, ranges)
    if scheduled_start is None:
        return (
            "OPEN_HOURS_NO_FIT",
            f"活动“{activity.get('title')}”无法在营业时段 {open_hours} 内安排完整时长",
        )
    scheduled_end = scheduled_start + duration
    if scheduled_end >= 24 * 60:
        return "DAY_SCHEDULE_OVERFLOW", "结合营业时间和交通耗时后，当天活动无法在午夜前完成"
    activity["time_slot"] = {
        "start": _format_minutes(scheduled_start),
        "end": _format_minutes(scheduled_end),
    }
    return None


def _next_open_start(
    earliest_start: int, duration: int, ranges: list[tuple[str, str]]
) -> int | None:
    if not ranges:
        return earliest_start
    candidates: list[int] = []
    for start, end in ranges:
        start_minute = _minutes(start)
        end_minute = _minutes(end)
        intervals = (
            [(start_minute, end_minute)]
            if end_minute >= start_minute
            else [(start_minute, 24 * 60), (0, end_minute)]
        )
        for interval_start, interval_end in intervals:
            candidate = max(earliest_start, interval_start)
            if candidate + duration <= interval_end:
                candidates.append(candidate)
    return min(candidates) if candidates else None


def _activity_fits_open_hours(start: str, end: str, ranges: list[tuple[str, str]]) -> bool:
    start_minute = _minutes(start)
    end_minute = _minutes(end)
    duration = max(end_minute - start_minute, 0)
    return _next_open_start(start_minute, duration, ranges) == start_minute


def _time_in_range(value: str, start: str, end: str) -> bool:
    current = _minutes(value)
    start_minute = _minutes(start)
    end_minute = _minutes(end)
    if end_minute >= start_minute:
        return start_minute <= current <= end_minute
    return current >= start_minute or current <= end_minute
