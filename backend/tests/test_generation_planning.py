from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agent_contracts.loader import validate_itinerary
from app.core.errors import AppError
from app.services.generation_planning import compile_generation_draft


def _trip() -> SimpleNamespace:
    return SimpleNamespace(
        city="长沙",
        title="长沙寒假游",
        start_date=date(2027, 1, 2),
        end_date=date(2027, 1, 2),
        traveler_count=2,
        total_budget=4000,
        version=3,
        agent_trip_id=uuid4(),
        preferences={"items": ["美食"]},
        constraints={"pace": "relaxed", "items": []},
    )


def _valid_draft() -> dict:
    return {
        "city": "长沙",
        "title": "长沙一日文化美食游",
        "days": [
            {
                "date": "2027-01-02",
                "day_index": 1,
                "theme": "岳麓文化",
                "activities": [
                    {
                        "activity_id": "act-1",
                        "type": "poi",
                        "title": "游览岳麓书院",
                        "duration_minutes": 120,
                        "location": {"name": "岳麓书院", "poi_id": "B02DB05TQH"},
                        "cost": {"amount": 80},
                        "note": "提前预约",
                        "open_hours_hint": "09:00-17:00",
                    },
                    {
                        "activity_id": "act-2",
                        "type": "meal",
                        "title": "午餐",
                        "duration_minutes": 90,
                        "location": {"name": "老许家·鱼市主题餐厅", "poi_id": None},
                        "cost": {"amount": 180},
                        "note": None,
                        "open_hours_hint": None,
                    },
                ],
            }
        ],
    }


def test_generation_draft_compiles_to_exact_non_overlapping_times() -> None:
    itinerary = compile_generation_draft(_valid_draft(), _trip())  # type: ignore[arg-type]

    first, second = itinerary["days"][0]["activities"]
    assert first["time_slot"] == {"start": "09:00", "end": "11:00"}
    assert second["time_slot"] == {"start": "11:30", "end": "13:00"}
    assert first["location"]["poi_id"] == "B02DB05TQH"
    validate_itinerary(itinerary)


def test_explicit_transport_replaces_generic_inter_activity_gaps() -> None:
    draft = _valid_draft()
    draft["days"][0]["activities"].insert(
        1,
        {
            "activity_id": "act-3",
            "type": "transport",
            "title": "乘地铁前往餐厅",
            "duration_minutes": 60,
            "location": {"name": "溁湾镇地铁站", "poi_id": None},
            "cost": {"amount": 6},
            "note": None,
            "open_hours_hint": None,
        },
    )

    itinerary = compile_generation_draft(draft, _trip())  # type: ignore[arg-type]

    first, transport, meal = itinerary["days"][0]["activities"]
    assert first["time_slot"] == {"start": "09:00", "end": "11:00"}
    assert transport["time_slot"] == {"start": "11:00", "end": "12:00"}
    assert meal["time_slot"] == {"start": "12:00", "end": "13:30"}


def test_missing_budget_keeps_realistic_activity_costs_without_zero_budget() -> None:
    trip = _trip()
    trip.total_budget = None

    itinerary = compile_generation_draft(_valid_draft(), trip)  # type: ignore[arg-type]

    assert itinerary["meta"]["budget_total"] is None
    assert itinerary["cost_summary"]["total_estimate"]["amount"] == 260
    assert itinerary["cost_summary"]["budget_status"] is None
    assert itinerary["cost_summary"]["over_by"] is None
    validate_itinerary(itinerary)


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda draft: draft.update(
                {"type": "json_object", "itinerary": {"days": draft["days"]}}
            ),
            "UNEXPECTED_FIELD",
        ),
        (
            lambda draft: draft["days"][0]["activities"][0].update(
                {"time_slot": "morning"}
            ),
            "UNEXPECTED_FIELD",
        ),
        (
            lambda draft: draft["days"][0]["activities"][0]["location"].update(
                {"name": "具体门店现场选择"}
            ),
            "PLACEHOLDER_LOCATION",
        ),
    ],
)
def test_generation_draft_rejects_legacy_and_placeholder_shapes(mutate, expected_code) -> None:
    draft = _valid_draft()
    mutate(draft)

    with pytest.raises(AppError) as exc_info:
        compile_generation_draft(draft, _trip())  # type: ignore[arg-type]

    assert exc_info.value.code == "AGENT_OUTPUT_INVALID"
    assert expected_code in {item["code"] for item in exc_info.value.detail}
