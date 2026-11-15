from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from app.core.errors import AppError
from app.db.models import Trip
from app.services.trip_constraints import normalize_pace

ALLOWED_ACTIVITY_TYPES = {"poi", "meal", "hotel", "transport", "free_time"}
TOP_LEVEL_KEYS = {"city", "title", "days"}
DAY_KEYS = {"date", "day_index", "theme", "activities"}
ACTIVITY_KEYS = {
    "activity_id",
    "type",
    "title",
    "duration_minutes",
    "location",
    "cost",
    "note",
    "open_hours_hint",
    "journey_role",
    "transport_mode",
    "origin_city",
    "destination_city",
    "transport_service",
    "transport_status",
    "transport_source",
    "transport_queried_at",
}
LOCATION_KEYS = {"name", "poi_id"}
COST_KEYS = {"amount"}
PLACEHOLDER_LOCATION_RE = re.compile(
    r"(?:附近|周边|当地|市区|具体门店|现场选择|待确认|自由安排|返回酒店|酒店休息|"
    r"某(?:餐厅|酒店|景点)|合适的|任选|随便)",
    re.IGNORECASE,
)


def compile_generation_draft(raw: dict[str, Any], trip: Trip) -> dict[str, Any]:
    """Validate the model-only planning draft and compile it into the final itinerary contract.

    The model chooses real place names, order, durations, and estimated costs. Exact clock
    times and all system-owned fields are produced here so a malformed model time cannot be
    silently converted into a plausible-looking itinerary.
    """

    errors: list[dict[str, Any]] = []
    if not isinstance(raw, dict):
        _raise_invalid([_error("", "输出必须是 JSON 对象", "DRAFT_NOT_OBJECT")])

    _check_keys(raw, TOP_LEVEL_KEYS, "", errors)
    city = raw.get("city")
    if not isinstance(city, str) or city.strip() != trip.city.strip():
        errors.append(_error("city", f"city 必须精确等于 {trip.city}", "CITY_MISMATCH"))
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(_error("title", "title 必须是非空字符串", "TITLE_REQUIRED"))

    raw_days = raw.get("days")
    if not isinstance(raw_days, list):
        errors.append(_error("days", "days 必须是数组", "DAYS_REQUIRED"))
        _raise_invalid(errors)

    expected_dates = [
        trip.start_date + timedelta(days=offset)
        for offset in range((trip.end_date - trip.start_date).days + 1)
    ]
    if len(raw_days) != len(expected_dates):
        errors.append(
            _error(
                "days",
                f"必须覆盖 {len(expected_dates)} 天，实际为 {len(raw_days)} 天",
                "DAY_COUNT_MISMATCH",
            )
        )

    compiled_days: list[dict[str, Any]] = []
    seen_activity_ids: set[str] = set()
    total_cost = 0.0
    for day_position, expected_date in enumerate(expected_dates, start=1):
        if day_position > len(raw_days):
            break
        raw_day = raw_days[day_position - 1]
        path = f"days.{day_position - 1}"
        if not isinstance(raw_day, dict):
            errors.append(_error(path, "day 必须是对象", "DAY_NOT_OBJECT"))
            continue
        _check_keys(raw_day, DAY_KEYS, path, errors)
        if raw_day.get("date") != expected_date.isoformat():
            errors.append(
                _error(
                    f"{path}.date",
                    f"日期必须是 {expected_date.isoformat()}",
                    "DATE_MISMATCH",
                )
            )
        if raw_day.get("day_index") != day_position:
            errors.append(
                _error(
                    f"{path}.day_index",
                    f"day_index 必须是 {day_position}",
                    "DAY_INDEX_MISMATCH",
                )
            )
        raw_activities = raw_day.get("activities")
        if not isinstance(raw_activities, list) or not raw_activities:
            errors.append(
                _error(f"{path}.activities", "每天至少需要一个活动", "EMPTY_GENERATED_DAY")
            )
            continue

        compiled_activities: list[dict[str, Any]] = []
        cursor = datetime.combine(date.min, datetime.strptime("09:00", "%H:%M").time())
        for activity_position, raw_activity in enumerate(raw_activities):
            activity_path = f"{path}.activities.{activity_position}"
            if not isinstance(raw_activity, dict):
                errors.append(_error(activity_path, "activity 必须是对象", "ACTIVITY_NOT_OBJECT"))
                continue
            _check_keys(raw_activity, ACTIVITY_KEYS, activity_path, errors)
            activity_id = raw_activity.get("activity_id")
            if not isinstance(activity_id, str) or not re.fullmatch(r"act-\d+", activity_id):
                errors.append(
                    _error(
                        f"{activity_path}.activity_id",
                        "activity_id 必须使用 act-N 格式",
                        "INVALID_ACTIVITY_ID",
                    )
                )
                activity_id = f"invalid-{day_position}-{activity_position}"
            elif activity_id in seen_activity_ids:
                errors.append(
                    _error(
                        f"{activity_path}.activity_id",
                        "activity_id 在全行程中必须唯一",
                        "DUPLICATE_ACTIVITY_ID",
                    )
                )
            seen_activity_ids.add(str(activity_id))

            activity_type = raw_activity.get("type")
            if activity_type not in ALLOWED_ACTIVITY_TYPES:
                errors.append(
                    _error(
                        f"{activity_path}.type",
                        "type 必须是 poi/meal/hotel/transport/free_time",
                        "INVALID_ACTIVITY_TYPE",
                    )
                )
                activity_type = "free_time"
            journey_role = raw_activity.get("journey_role")
            if journey_role not in {
                None,
                "outbound",
                "return",
                "intercity_transfer",
                "local_transfer",
            }:
                errors.append(
                    _error(
                        f"{activity_path}.journey_role",
                        "journey_role 不合法",
                        "INVALID_JOURNEY_ROLE",
                    )
                )
                journey_role = None
            transport_mode = raw_activity.get("transport_mode")
            if (
                journey_role in {"outbound", "return", "intercity_transfer"}
                and transport_mode not in {"flight", "high_speed_rail", "rail"}
            ):
                errors.append(
                    _error(
                        f"{activity_path}.transport_mode",
                        "大交通仅支持 flight/high_speed_rail/rail",
                        "UNSUPPORTED_INTERCITY_MODE",
                    )
                )
            activity_title = raw_activity.get("title")
            if not isinstance(activity_title, str) or not activity_title.strip():
                errors.append(
                    _error(f"{activity_path}.title", "title 必须是非空字符串", "TITLE_REQUIRED")
                )
                activity_title = "未命名活动"

            duration = raw_activity.get("duration_minutes")
            max_duration = 720 if journey_role in {"outbound", "return"} else 240
            if (
                not isinstance(duration, int)
                or isinstance(duration, bool)
                or not 30 <= duration <= max_duration
            ):
                errors.append(
                    _error(
                        f"{activity_path}.duration_minutes",
                        f"duration_minutes 必须是 30 到 {max_duration} 的整数",
                        "INVALID_DURATION",
                    )
                )
                duration = 60

            location = raw_activity.get("location")
            location_name = None
            requested_poi_id = None
            if not isinstance(location, dict):
                errors.append(
                    _error(
                        f"{activity_path}.location",
                        "每个活动都必须提供具体 location",
                        "LOCATION_REQUIRED",
                    )
                )
            else:
                _check_keys(location, LOCATION_KEYS, f"{activity_path}.location", errors)
                location_name = location.get("name")
                requested_poi_id = location.get("poi_id")
                if not isinstance(location_name, str) or not location_name.strip():
                    errors.append(
                        _error(
                            f"{activity_path}.location.name",
                            "location.name 必须是具体地点名",
                            "LOCATION_REQUIRED",
                        )
                    )
                elif PLACEHOLDER_LOCATION_RE.search(location_name):
                    errors.append(
                        _error(
                            f"{activity_path}.location.name",
                            "地点不能使用附近、周边、现场选择或待确认等占位表述",
                            "PLACEHOLDER_LOCATION",
                        )
                    )
                if requested_poi_id is not None and not isinstance(requested_poi_id, str):
                    errors.append(
                        _error(
                            f"{activity_path}.location.poi_id",
                            "poi_id 必须是字符串或 null",
                            "INVALID_POI_ID",
                        )
                    )

            cost = raw_activity.get("cost")
            amount = None
            if not isinstance(cost, dict):
                errors.append(_error(f"{activity_path}.cost", "cost 必须是对象", "COST_REQUIRED"))
            else:
                _check_keys(cost, COST_KEYS, f"{activity_path}.cost", errors)
                amount = cost.get("amount")
                if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 0:
                    errors.append(
                        _error(
                            f"{activity_path}.cost.amount",
                            "cost.amount 必须是非负数字",
                            "INVALID_COST",
                        )
                    )
                    amount = 0
            total_cost += float(amount or 0)

            start = cursor
            end = start + timedelta(minutes=int(duration))
            if end.date() != date.min or end.strftime("%H:%M") > "23:30":
                errors.append(
                    _error(
                        activity_path,
                        "当天活动总时长过长，无法在 09:00-23:30 内完成",
                        "DAY_TOO_LONG",
                    )
                )
            compiled_activities.append(
                {
                    "activity_id": activity_id,
                    "type": activity_type,
                    "journey_role": journey_role,
                    "transport_mode": transport_mode,
                    "origin_city": raw_activity.get("origin_city"),
                    "destination_city": raw_activity.get("destination_city"),
                    "transport_service": raw_activity.get("transport_service"),
                    "transport_status": raw_activity.get("transport_status"),
                    "transport_source": raw_activity.get("transport_source"),
                    "transport_queried_at": raw_activity.get("transport_queried_at"),
                    "title": str(activity_title),
                    "time_slot": {"start": start.strftime("%H:%M"), "end": end.strftime("%H:%M")},
                    "location": {
                        "name": str(location_name or activity_title),
                        "address": None,
                        "lng": None,
                        "lat": None,
                        "poi_id": requested_poi_id if isinstance(requested_poi_id, str) else None,
                        "poi_source": None,
                    },
                    "cost": {
                        "amount": float(amount or 0),
                        "currency": "CNY",
                        "price_type": "estimate",
                        "source": "llm",
                        "note": None,
                    },
                    "note": (
                        raw_activity.get("note")
                        if isinstance(raw_activity.get("note"), str)
                        else None
                    ),
                    "open_hours_hint": (
                        raw_activity.get("open_hours_hint")
                        if isinstance(raw_activity.get("open_hours_hint"), str)
                        else None
                    ),
                    "status": "planned",
                    "replaced_reason": None,
                }
            )
            next_activity = (
                raw_activities[activity_position + 1]
                if activity_position + 1 < len(raw_activities)
                and isinstance(raw_activities[activity_position + 1], dict)
                else None
            )
            next_type = next_activity.get("type") if next_activity else None
            # A transport activity already represents the transfer between two stops.
            # Do not add the generic inter-activity buffer on either side of it, or the
            # same journey is counted once in transport.duration and again as a gap.
            gap_minutes = 0 if "transport" in {activity_type, next_type} else 30
            cursor = end + timedelta(minutes=gap_minutes)

        compiled_days.append(
            {
                "date": expected_date.isoformat(),
                "day_index": day_position,
                "theme": raw_day.get("theme") if isinstance(raw_day.get("theme"), str) else None,
                "weather": None,
                "activities": compiled_activities,
                "transfers": [],
            }
        )

    budget = float(trip.total_budget or 0)
    if budget > 0 and total_cost > budget:
        errors.append(
            _error(
                "cost_summary.total_estimate",
                f"预计费用 {total_cost:.2f} 超出预算 {budget:.2f}",
                "BUDGET_EXCEEDED",
            )
        )
    _raise_invalid(errors)

    preferences = trip.preferences if isinstance(trip.preferences, dict) else {}
    constraints = trip.constraints if isinstance(trip.constraints, dict) else {}
    preference_items = preferences.get("items", [])
    special_constraints = constraints.get("items", [])
    return {
        "schema_version": "1.1",
        "trip_id": str(trip.agent_trip_id),
        "version": trip.version + 1,
        "city": {"name": trip.city, "adcode": None, "province": None},
        "meta": {
            "title": title.strip(),
            "date_start": trip.start_date.isoformat(),
            "date_end": trip.end_date.isoformat(),
            "traveler_count": trip.traveler_count or 1,
            "budget_total": {
                "amount": budget,
                "currency": "CNY",
                "price_type": "estimate",
                "source": "manual",
            },
            "preferences": _string_list(preference_items),
            "pace": normalize_pace(constraints.get("pace")),
            "party_type": constraints.get("party_type"),
            "special_constraints": _string_list(special_constraints),
        },
        "members": [],
        "permissions": {"collab_mode": "A2_poll", "edit_policy": "all_members"},
        "days": compiled_days,
        "cost_summary": {
            "total_estimate": {
                "amount": total_cost,
                "currency": "CNY",
                "price_type": "estimate",
                "source": "llm",
            },
            "by_day": [],
            "budget_status": "within" if budget <= 0 or total_cost <= budget else "over",
            "over_by": max(total_cost - budget, 0) if budget > 0 else 0,
        },
        "revisions": [],
        "candidates": [],
    }


def _check_keys(
    value: dict[str, Any], allowed: set[str], path: str, errors: list[dict[str, Any]]
) -> None:
    for key in sorted(set(value) - allowed):
        errors.append(
            _error(
                f"{path}.{key}".strip("."),
                f"不允许字段 {key}",
                "UNEXPECTED_FIELD",
            )
        )
    for key in sorted(allowed - set(value)):
        if key in {
            "theme",
            "note",
            "open_hours_hint",
            "poi_id",
            "journey_role",
            "transport_mode",
            "origin_city",
            "destination_city",
            "transport_service",
            "transport_status",
            "transport_source",
            "transport_queried_at",
        }:
            continue
        errors.append(
            _error(
                f"{path}.{key}".strip("."),
                f"缺少字段 {key}",
                "MISSING_FIELD",
            )
        )


def _error(path: str, message: str, code: str) -> dict[str, Any]:
    return {"path": path, "message": message, "code": code}


def _raise_invalid(errors: list[dict[str, Any]]) -> None:
    if errors:
        raise AppError(
            "AGENT_OUTPUT_INVALID",
            "行程规划草稿不符合契约",
            status_code=502,
            detail=errors,
        )


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in (None, ""):
        return []
    return [str(value)]
