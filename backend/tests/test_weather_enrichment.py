from datetime import UTC, date, datetime

import pytest

from app.core.errors import AppError
from app.services.weather_enrichment import enrich_itinerary_weather


class SuccessfulWeatherClient:
    async def weather_for_date(self, *, city_code: str, target_date: date) -> dict:
        assert city_code == "成都"
        assert target_date == date(2026, 11, 5)
        return {
            "condition_day": "小雨",
            "condition_night": "阴",
            "precipitation_probability": "60",
            "queried_at": datetime(2026, 11, 5, tzinfo=UTC),
            "stale": False,
        }


class FailingWeatherClient:
    async def weather_for_date(self, *, city_code: str, target_date: date) -> dict:
        del city_code, target_date
        raise AppError("QWEATHER_TIMEOUT", "天气查询超时", status_code=502)


@pytest.mark.asyncio
async def test_weather_is_attached_to_each_day() -> None:
    itinerary = {"days": [{"date": "2026-11-05", "day_index": 1, "activities": []}]}
    enriched, warnings = await enrich_itinerary_weather(
        itinerary,
        city_code="成都",
        client=SuccessfulWeatherClient(),  # type: ignore[arg-type]
    )
    assert warnings == []
    assert enriched["days"][0]["weather"] == {
        "summary": "小雨",
        "rain_prob": 0.6,
        "source": "qweather",
        "fetched_at": "2026-11-05T00:00:00+00:00",
    }
    assert "weather" not in itinerary["days"][0]


@pytest.mark.asyncio
async def test_weather_failure_degrades_without_losing_itinerary() -> None:
    itinerary = {
        "days": [
            {
                "date": "2026-11-05",
                "day_index": 1,
                "activities": [{"activity_id": "act-1", "title": "人民公园"}],
            }
        ]
    }
    enriched, warnings = await enrich_itinerary_weather(
        itinerary,
        city_code="成都",
        client=FailingWeatherClient(),  # type: ignore[arg-type]
    )
    assert enriched["days"][0]["weather"] is None
    assert enriched["days"][0]["activities"][0]["activity_id"] == "act-1"
    assert warnings[0]["code"] == "QWEATHER_TIMEOUT"
