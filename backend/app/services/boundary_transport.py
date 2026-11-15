from __future__ import annotations

import re
from copy import deepcopy
from datetime import date, timedelta
from typing import Any

from app.core.errors import AppError

BOUNDARY_ROLES = {"outbound", "return"}
JOURNEY_ROLES = {*BOUNDARY_ROLES, "intercity_transfer", "local_transfer"}
SUPPORTED_INTERCITY_MODES = {"flight", "high_speed_rail", "rail"}


def normalize_itinerary_dates(itinerary: dict[str, Any]) -> dict[str, Any]:
    """Use the ordered day dates as the source of truth for a revision's date range."""
    days = itinerary.get("days")
    if not isinstance(days, list) or not days:
        return itinerary
    parsed: list[tuple[date, dict[str, Any]]] = []
    for day in days:
        try:
            parsed.append((date.fromisoformat(str(day.get("date"))), day))
        except (TypeError, ValueError):
            return itinerary
    parsed.sort(key=lambda item: item[0])
    itinerary["days"] = [item[1] for item in parsed]
    for index, (_, day) in enumerate(parsed, start=1):
        day["day_index"] = index
    meta = itinerary.setdefault("meta", {})
    if isinstance(meta, dict):
        meta["date_start"] = parsed[0][0].isoformat()
        meta["date_end"] = parsed[-1][0].isoformat()
    return itinerary


def normalize_boundary_transports(
    candidate: dict[str, Any],
    *,
    old_itinerary: dict[str, Any] | None,
    origin_city: str | None,
    destination_city: str,
) -> dict[str, Any]:
    """Deduplicate and move trip-boundary transport while preserving old IDs."""
    proposed = candidate.get("proposed_itinerary")
    if not isinstance(proposed, dict):
        return candidate
    normalize_itinerary_dates(proposed)
    if old_itinerary:
        old_title = (old_itinerary.get("meta") or {}).get("title")
        if old_title:
            proposed.setdefault("meta", {})["title"] = old_title
    _infer_roles(proposed, origin_city=origin_city, destination_city=destination_city)
    if old_itinerary:
        _infer_roles(old_itinerary, origin_city=origin_city, destination_city=destination_city)

    discarded_ids: set[str] = set()
    for role in ("outbound", "return"):
        old_matches = _role_matches(old_itinerary, role) if old_itinerary else []
        proposed_matches = _role_matches(proposed, role)
        if not old_matches and len(proposed_matches) <= 1:
            continue

        old_activity = old_matches[0][2] if old_matches else None
        old_id = old_activity.get("activity_id") if old_activity else None
        target_day = proposed["days"][0] if role == "outbound" else proposed["days"][-1]
        target_matches = [item for item in proposed_matches if item[1] is target_day]
        same_id = [item for item in proposed_matches if item[2].get("activity_id") == old_id]
        chosen_entry = (target_matches or same_id or proposed_matches)[-1:] or None
        if chosen_entry:
            chosen = deepcopy(chosen_entry[0][2])
        elif old_activity:
            chosen = deepcopy(old_activity)
        else:
            continue

        for _, day, activity in proposed_matches:
            activity_id = activity.get("activity_id")
            if activity_id and activity_id != old_id:
                discarded_ids.add(str(activity_id))
            day["activities"].remove(activity)

        if old_id:
            chosen["activity_id"] = old_id
        chosen["journey_role"] = role
        chosen["origin_city"] = origin_city if role == "outbound" else destination_city
        chosen["destination_city"] = destination_city if role == "outbound" else origin_city
        if role == "outbound":
            target_day.setdefault("activities", []).insert(0, chosen)
        else:
            target_day.setdefault("activities", []).append(chosen)

    if discarded_ids:
        diff = candidate.get("diff")
        if isinstance(diff, dict) and isinstance(diff.get("ops"), list):
            diff["ops"] = [
                operation
                for operation in diff["ops"]
                if not discarded_ids
                & {
                    str(operation.get("activity_id") or ""),
                    str(operation.get("from_id") or ""),
                    str(operation.get("to_id") or ""),
                }
            ]
    return candidate


def validate_boundary_transports(
    itinerary: dict[str, Any],
    *,
    origin_city: str | None,
    destination_city: str,
    require_round_trip: bool = False,
) -> None:
    errors: list[dict[str, Any]] = []
    days = itinerary.get("days") or []
    if not isinstance(days, list) or not days:
        return

    errors.extend(_date_structure_errors(itinerary))
    _infer_roles(itinerary, origin_city=origin_city, destination_city=destination_city)
    outbound = _role_matches(itinerary, "outbound")
    returns = _role_matches(itinerary, "return")
    if require_round_trip and origin_city:
        if len(outbound) != 1:
            errors.append(_error("BOUNDARY_OUTBOUND_COUNT", "往返行程必须且只能有一条去程大交通"))
        if len(returns) != 1:
            errors.append(_error("BOUNDARY_RETURN_COUNT", "往返行程必须且只能有一条返程大交通"))
    if len(outbound) > 1:
        errors.append(_error("BOUNDARY_OUTBOUND_DUPLICATE", "检测到重复的去程大交通"))
    if len(returns) > 1:
        errors.append(_error("BOUNDARY_RETURN_DUPLICATE", "检测到重复的返程大交通"))

    for role, matches, expected_day, expected_position in (
        ("outbound", outbound, days[0], 0),
        ("return", returns, days[-1], -1),
    ):
        if len(matches) != 1:
            continue
        _, day, activity = matches[0]
        activities = day.get("activities") or []
        if day is not expected_day:
            errors.append(_error(f"BOUNDARY_{role.upper()}_DAY", f"{role} 必须位于行程边界日期"))
        elif activities and activity is not activities[expected_position]:
            errors.append(_error(f"BOUNDARY_{role.upper()}_ORDER", f"{role} 必须位于当天活动边界"))
        mode = activity.get("transport_mode")
        if mode not in SUPPORTED_INTERCITY_MODES:
            errors.append(_error("BOUNDARY_MODE_UNSUPPORTED", "大交通仅支持飞机、高铁和普通铁路"))
        expected_origin = origin_city if role == "outbound" else destination_city
        expected_destination = destination_city if role == "outbound" else origin_city
        if expected_origin and activity.get("origin_city") not in {None, expected_origin}:
            errors.append(_error("BOUNDARY_DIRECTION_INVALID", f"{role} 出发城市方向错误"))
        if expected_destination and activity.get("destination_city") not in {
            None,
            expected_destination,
        }:
            errors.append(_error("BOUNDARY_DIRECTION_INVALID", f"{role} 到达城市方向错误"))
        if activity.get("transport_status") in {"quoted", "confirmed"} and not activity.get(
            "transport_source"
        ):
            errors.append(_error("BOUNDARY_SOURCE_REQUIRED", "真实大交通信息必须包含来源"))
        if activity.get("transport_source") and not activity.get("transport_queried_at"):
            errors.append(_error("BOUNDARY_QUERY_TIME_REQUIRED", "真实大交通信息必须包含查询时间"))

    if errors:
        raise AppError(
            "AGENT_OUTPUT_INVALID",
            "行程边界交通或日期结构不符合规则",
            status_code=502,
            detail=errors,
        )


def _infer_roles(
    itinerary: dict[str, Any], *, origin_city: str | None, destination_city: str
) -> None:
    days = itinerary.get("days") or []
    for day_index, day in enumerate(days):
        activities = day.get("activities") or []
        for position, activity in enumerate(activities):
            if activity.get("type") != "transport":
                continue
            role = activity.get("journey_role")
            text = " ".join(
                str(activity.get(key) or "")
                for key in ("title", "note", "origin_city", "destination_city")
            )
            if role not in JOURNEY_ROLES:
                has_supported_mode = bool(
                    re.search(r"航班|飞机|机场|高铁|动车|火车|铁路|车次", text)
                )
                if not has_supported_mode or not origin_city:
                    activity["journey_role"] = "local_transfer"
                    continue
                mentions_origin = origin_city in text
                mentions_destination = destination_city in text
                if day_index == 0 and position == 0 and mentions_origin:
                    activity["journey_role"] = "outbound"
                elif day_index == len(days) - 1 and mentions_origin and re.search(
                    r"返程|返回|回家|回到|前往", text
                ):
                    activity["journey_role"] = "return"
                elif mentions_origin and mentions_destination:
                    if day_index == 0:
                        activity["journey_role"] = "outbound"
                    elif day_index == len(days) - 1:
                        activity["journey_role"] = "return"
                    else:
                        activity["journey_role"] = "intercity_transfer"
                else:
                    activity["journey_role"] = "local_transfer"

            if activity["journey_role"] in BOUNDARY_ROLES:
                activity.setdefault(
                    "origin_city",
                    origin_city
                    if activity["journey_role"] == "outbound"
                    else destination_city,
                )
                activity.setdefault(
                    "destination_city",
                    destination_city
                    if activity["journey_role"] == "outbound"
                    else origin_city,
                )
                activity.setdefault("transport_mode", _infer_mode(text))
                activity.setdefault("transport_status", "estimate")


def _infer_mode(text: str) -> str:
    if re.search(r"航班|飞机|机场", text):
        return "flight"
    if re.search(r"高铁|动车", text):
        return "high_speed_rail"
    return "rail"


def _role_matches(
    itinerary: dict[str, Any] | None, role: str
) -> list[tuple[int, dict[str, Any], dict[str, Any]]]:
    if not itinerary:
        return []
    result = []
    for day_index, day in enumerate(itinerary.get("days") or []):
        for activity in day.get("activities") or []:
            if activity.get("journey_role") == role:
                result.append((day_index, day, activity))
    return result


def _date_structure_errors(itinerary: dict[str, Any]) -> list[dict[str, Any]]:
    meta = itinerary.get("meta") or {}
    days = itinerary.get("days") or []
    try:
        start = date.fromisoformat(str(meta.get("date_start")))
        end = date.fromisoformat(str(meta.get("date_end")))
        actual_dates = [date.fromisoformat(str(day.get("date"))) for day in days]
    except (TypeError, ValueError):
        return [_error("DATE_STRUCTURE_INVALID", "行程日期必须使用有效的 YYYY-MM-DD")]
    expected_count = (end - start).days + 1
    errors = []
    if end < start or expected_count != len(days):
        errors.append(_error("DATE_RANGE_MISMATCH", "开始日期、结束日期与行程天数不一致"))
    for index, (day, actual_date) in enumerate(
        zip(days, actual_dates, strict=False), start=1
    ):
        if day.get("day_index") != index or actual_date != start + timedelta(days=index - 1):
            errors.append(_error("DATE_SEQUENCE_INVALID", "每日日期或 day_index 不连续"))
            break
    return errors


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}
