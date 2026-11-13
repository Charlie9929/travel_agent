from app.services.trip_validation import validate_trip_rules


def test_trip_rules_detect_time_overlap_and_budget_overrun() -> None:
    itinerary = {
        "meta": {"budget_total": {"amount": 100}},
        "days": [
            {
                "day_index": 1,
                "activities": [
                    {
                        "activity_id": "act-1",
                        "type": "poi",
                        "time_slot": {"start": "09:00", "end": "11:00"},
                        "location": {"name": "A"},
                        "cost": {"amount": 80},
                    },
                    {
                        "activity_id": "act-2",
                        "type": "poi",
                        "time_slot": {"start": "10:00", "end": "12:00"},
                        "location": {"name": "B"},
                        "cost": {"amount": 50},
                    },
                ],
            }
        ],
    }
    result = validate_trip_rules(itinerary)
    codes = {item["code"] for item in result["errors"]}
    assert result["valid"] is False
    assert {"TIME_OVERLAP", "BUDGET_EXCEEDED"} <= codes


def test_trip_rules_accept_adjacent_times() -> None:
    itinerary = {
        "meta": {"budget_total": {"amount": 100}},
        "days": [
            {
                "day_index": 1,
                "activities": [
                    {
                        "activity_id": "act-1",
                        "type": "free_time",
                        "time_slot": {"start": "09:00", "end": "10:00"},
                    },
                    {
                        "activity_id": "act-2",
                        "type": "free_time",
                        "time_slot": {"start": "10:00", "end": "11:00"},
                    },
                ],
            }
        ],
    }
    assert validate_trip_rules(itinerary)["valid"] is True


def test_trip_rules_check_queried_opening_hours_and_price_timestamp() -> None:
    itinerary = {
        "meta": {"budget_total": {"amount": 500}},
        "days": [
            {
                "day_index": 1,
                "activities": [
                    {
                        "activity_id": "act-1",
                        "type": "poi",
                        "time_slot": {"start": "08:30", "end": "09:30"},
                        "location": {"name": "博物馆"},
                        "open_hours_hint": "09:00-17:00",
                        "quoted_cost": {"amount": 50, "source": "amap"},
                    }
                ],
            }
        ],
    }
    result = validate_trip_rules(itinerary)
    codes = {item["code"] for item in result["errors"]}
    assert {"OUTSIDE_OPEN_HOURS", "QUOTED_PRICE_MISSING_TIMESTAMP"} <= codes
    assert result["checks"]["opening_hours"] is False
