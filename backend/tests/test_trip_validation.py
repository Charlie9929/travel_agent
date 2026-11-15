import pytest

from app.services.trip_validation import enrich_route_checks, validate_trip_rules


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
                        "location": {
                            "name": "人民公园",
                            "poi_id": "B001",
                            "poi_source": "amap",
                            "lng": 104.05,
                            "lat": 30.66,
                        },
                    },
                    {
                        "activity_id": "act-2",
                        "type": "free_time",
                        "time_slot": {"start": "10:00", "end": "11:00"},
                        "location": {
                            "name": "宽窄巷子",
                            "poi_id": "B002",
                            "poi_source": "amap",
                            "lng": 104.06,
                            "lat": 30.67,
                        },
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


def test_trip_rules_do_not_apply_poi_opening_hours_to_transport() -> None:
    itinerary = {
        "meta": {"budget_total": {"amount": 500}},
        "days": [
            {
                "day_index": 1,
                "activities": [
                    {
                        "activity_id": "act-1",
                        "type": "transport",
                        "time_slot": {"start": "18:30", "end": "19:00"},
                        "location": {
                            "name": "静安寺(地铁站)",
                            "poi_id": "METRO",
                            "poi_source": "amap",
                            "lng": 121.446533,
                            "lat": 31.223231,
                        },
                        "open_hours_hint": "07:30-18:00",
                    }
                ],
            }
        ],
    }

    result = validate_trip_rules(itinerary)

    assert result["valid"] is True
    assert result["checks"]["opening_hours"] is True


def test_trip_rules_accept_amap_all_day_24_hour_format() -> None:
    itinerary = {
        "meta": {"budget_total": {"amount": 500}},
        "days": [
            {
                "day_index": 1,
                "activities": [
                    {
                        "activity_id": "act-1",
                        "type": "poi",
                        "time_slot": {"start": "09:00", "end": "11:00"},
                        "location": {
                            "name": "测试地点",
                            "poi_id": "B001",
                            "poi_source": "amap",
                            "lng": 120.6,
                            "lat": 31.3,
                        },
                        "open_hours_hint": "00:00-24:00 10:00-14:00",
                    }
                ],
            }
        ],
    }

    result = validate_trip_rules(itinerary)

    assert result["valid"] is True
    assert result["checks"]["opening_hours"] is True


@pytest.mark.asyncio
async def test_route_enrichment_reschedules_with_real_travel_time() -> None:
    class RouteClient:
        async def routes(self, **kwargs):
            del kwargs
            return {
                "queried_at": None,
                "routes": {
                    "transit": {
                        "available": True,
                        "distance_m": 8000,
                        "duration_min": 50,
                        "transit_count": 1,
                    }
                },
            }

    itinerary = {
        "city": {"adcode": "430100"},
        "days": [
            {
                "day_index": 1,
                "activities": [
                    {
                        "activity_id": "act-1",
                        "title": "岳麓书院",
                        "time_slot": {"start": "09:00", "end": "11:00"},
                        "location": {"lng": 112.9, "lat": 28.1},
                    },
                    {
                        "activity_id": "act-2",
                        "title": "长沙博物馆",
                        "time_slot": {"start": "11:30", "end": "13:00"},
                        "location": {"lng": 113.0, "lat": 28.2},
                    },
                ],
            }
        ],
    }

    scheduled, errors, _ = await enrich_route_checks(
        itinerary,
        client=RouteClient(),
        reschedule=True,  # type: ignore[arg-type]
    )

    second = scheduled["days"][0]["activities"][1]
    assert second["time_slot"] == {"start": "12:05", "end": "13:35"}
    assert errors == []


@pytest.mark.asyncio
async def test_reschedule_delays_first_activity_until_opening_time() -> None:
    class UnusedRouteClient:
        async def routes(self, **kwargs):
            raise AssertionError(f"single activity should not query routes: {kwargs}")

    itinerary = {
        "city": {"adcode": "320500"},
        "days": [
            {
                "day_index": 1,
                "activities": [
                    {
                        "activity_id": "act-1",
                        "title": "林屋洞探秘",
                        "time_slot": {"start": "09:00", "end": "11:00"},
                        "open_hours_hint": "10:00-14:00",
                        "location": {"lng": 120.3, "lat": 31.1},
                    }
                ],
            }
        ],
    }

    scheduled, errors, _ = await enrich_route_checks(
        itinerary,
        client=UnusedRouteClient(),
        reschedule=True,  # type: ignore[arg-type]
    )

    first = scheduled["days"][0]["activities"][0]
    assert first["time_slot"] == {"start": "10:00", "end": "12:00"}
    assert errors == []


@pytest.mark.asyncio
async def test_explicit_transport_is_not_counted_as_an_additional_route() -> None:
    class MustNotRouteClient:
        async def routes(self, **kwargs):
            raise AssertionError(f"explicit transport must own its duration: {kwargs}")

    itinerary = {
        "city": {"adcode": "440300"},
        "days": [
            {
                "day_index": 1,
                "activities": [
                    {
                        "activity_id": "act-1",
                        "type": "transport",
                        "title": "深圳北站打车前往酒店",
                        "time_slot": {"start": "09:00", "end": "10:00"},
                        "location": {"lng": 114.03, "lat": 22.61},
                    },
                    {
                        "activity_id": "act-2",
                        "type": "hotel",
                        "title": "办理入住",
                        "time_slot": {"start": "10:00", "end": "10:30"},
                        "location": {"lng": 113.85, "lat": 22.58},
                    },
                ],
            }
        ],
    }

    scheduled, errors, _ = await enrich_route_checks(
        itinerary,
        client=MustNotRouteClient(),  # type: ignore[arg-type]
        reschedule=True,
    )

    assert scheduled["days"][0]["activities"][1]["time_slot"] == {
        "start": "10:00",
        "end": "10:30",
    }
    assert scheduled["days"][0]["transfers"] == []
    assert errors == []


@pytest.mark.asyncio
async def test_failed_reschedule_restores_the_whole_day_schedule() -> None:
    class LongRouteClient:
        async def routes(self, **kwargs):
            del kwargs
            return {
                "routes": {
                    "drive": {
                        "available": True,
                        "distance_m": 200000,
                        "duration_min": 180,
                    }
                }
            }

    itinerary = {
        "city": {"adcode": "440300"},
        "days": [
            {
                "day_index": 1,
                "activities": [
                    {
                        "activity_id": "act-1",
                        "type": "poi",
                        "title": "夜间景点",
                        "time_slot": {"start": "09:00", "end": "11:00"},
                        "open_hours_hint": "20:00-23:00",
                        "location": {"lng": 114.0, "lat": 22.5},
                    },
                    {
                        "activity_id": "act-2",
                        "type": "meal",
                        "title": "晚餐",
                        "time_slot": {"start": "11:30", "end": "12:30"},
                        "location": {"lng": 113.0, "lat": 23.0},
                    },
                ],
            }
        ],
    }

    scheduled, errors, _ = await enrich_route_checks(
        itinerary,
        client=LongRouteClient(),  # type: ignore[arg-type]
        reschedule=True,
    )

    slots = [activity["time_slot"] for activity in scheduled["days"][0]["activities"]]
    assert slots == [
        {"start": "09:00", "end": "11:00"},
        {"start": "11:30", "end": "12:30"},
    ]
    assert [error["code"] for error in errors] == ["DAY_SCHEDULE_OVERFLOW"]
