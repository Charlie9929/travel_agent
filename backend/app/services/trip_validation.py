from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any


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
        },
        "cost": {"total_estimate": total_amount, "by_day": by_day_amount},
    }


def _valid_time(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError:
        return False
    return True
