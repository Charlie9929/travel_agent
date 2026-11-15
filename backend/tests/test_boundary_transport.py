from copy import deepcopy

import pytest

from app.core.errors import AppError
from app.services.boundary_transport import (
    normalize_boundary_transports,
    validate_boundary_transports,
)


def _activity(activity_id: str, role: str, title: str) -> dict:
    outbound = role == "outbound"
    return {
        "activity_id": activity_id,
        "type": "transport",
        "title": title,
        "journey_role": role,
        "transport_mode": "flight" if "航班" in title else "high_speed_rail",
        "origin_city": "广州" if outbound else "深圳",
        "destination_city": "深圳" if outbound else "广州",
        "transport_status": "estimate",
        "time_slot": {"start": "09:00", "end": "11:00"},
        "location": {"name": "深圳北站"},
        "cost": {"amount": 0},
        "status": "planned",
    }


def _local(activity_id: str, title: str) -> dict:
    return {
        "activity_id": activity_id,
        "type": "poi",
        "title": title,
        "time_slot": {"start": "12:00", "end": "14:00"},
        "location": {"name": title},
        "cost": {"amount": 0},
        "status": "planned",
    }


def _itinerary(end: str = "2026-12-02") -> dict:
    return {
        "meta": {
            "title": "用户手动输入的标题",
            "date_start": "2026-11-30",
            "date_end": end,
        },
        "days": [
            {
                "date": "2026-11-30",
                "day_index": 1,
                "activities": [
                    _activity("outbound-old", "outbound", "从广州乘高铁前往深圳"),
                    _local("local-1", "深圳湾公园"),
                ],
            },
            {
                "date": "2026-12-01",
                "day_index": 2,
                "activities": [_local("local-2", "莲花山公园")],
            },
            {
                "date": "2026-12-02",
                "day_index": 3,
                "activities": [
                    _local("local-3", "世界之窗"),
                    _activity("return-new", "return", "从深圳乘高铁返回广州"),
                ],
            },
        ],
    }


def test_append_day_moves_old_return_and_deduplicates() -> None:
    old = _itinerary(end="2026-12-01")
    old["days"] = old["days"][:2]
    old["days"][-1]["activities"].append(
        _activity("return-old", "return", "从深圳乘高铁返回广州")
    )
    proposed = _itinerary()
    proposed["meta"]["title"] = "AI 自动改名"
    proposed["days"][1]["activities"].append(deepcopy(old["days"][1]["activities"][-1]))

    candidate = normalize_boundary_transports(
        {"diff": {"ops": []}, "proposed_itinerary": proposed},
        old_itinerary=old,
        origin_city="广州",
        destination_city="深圳",
    )
    result = candidate["proposed_itinerary"]
    returns = [
        (day, activity)
        for day in result["days"]
        for activity in day["activities"]
        if activity.get("journey_role") == "return"
    ]

    assert len(returns) == 1
    assert returns[0][0]["date"] == "2026-12-02"
    assert returns[0][1]["activity_id"] == "return-old"
    assert returns[0][0]["activities"][-1] is returns[0][1]
    assert result["meta"]["title"] == "用户手动输入的标题"
    validate_boundary_transports(
        result,
        origin_city="广州",
        destination_city="深圳",
        require_round_trip=True,
    )


def test_prepend_day_moves_old_outbound_and_preserves_id() -> None:
    old = _itinerary()
    proposed = deepcopy(old)
    proposed["days"].insert(
        0,
        {
            "date": "2026-11-29",
            "day_index": 1,
            "activities": [_local("local-new", "深圳博物馆")],
        },
    )

    result = normalize_boundary_transports(
        {"diff": {"ops": []}, "proposed_itinerary": proposed},
        old_itinerary=old,
        origin_city="广州",
        destination_city="深圳",
    )["proposed_itinerary"]

    assert result["meta"]["date_start"] == "2026-11-29"
    assert result["days"][0]["activities"][0]["activity_id"] == "outbound-old"
    assert result["days"][0]["activities"][0]["journey_role"] == "outbound"
    validate_boundary_transports(
        result,
        origin_city="广州",
        destination_city="深圳",
        require_round_trip=True,
    )


def test_rejects_long_distance_coach() -> None:
    itinerary = _itinerary()
    itinerary["days"][0]["activities"][0]["transport_mode"] = "coach"

    with pytest.raises(AppError) as exc_info:
        validate_boundary_transports(
            itinerary,
            origin_city="广州",
            destination_city="深圳",
            require_round_trip=True,
        )

    assert "BOUNDARY_MODE_UNSUPPORTED" in {
        error["code"] for error in exc_info.value.detail
    }


def test_confirmed_flight_requires_source_and_query_time() -> None:
    itinerary = _itinerary()
    outbound = itinerary["days"][0]["activities"][0]
    outbound["transport_mode"] = "flight"
    outbound["transport_status"] = "confirmed"

    with pytest.raises(AppError) as exc_info:
        validate_boundary_transports(
            itinerary,
            origin_city="广州",
            destination_city="深圳",
            require_round_trip=True,
        )

    assert "BOUNDARY_SOURCE_REQUIRED" in {
        error["code"] for error in exc_info.value.detail
    }
