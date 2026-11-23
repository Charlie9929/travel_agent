import asyncio
from copy import deepcopy
from datetime import date, datetime
from typing import Any

from app.core.errors import AppError
from app.integrations.qweather import QWeatherClient


def _rain_probability(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 1:
        number /= 100
    return max(0.0, min(number, 1.0))


async def enrich_itinerary_weather(
    data: dict[str, Any],
    *,
    city_code: str,
    client: QWeatherClient,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Attach daily weather without making weather availability block the itinerary."""
    enriched = deepcopy(data)
    async def enrich_day(day: dict[str, Any]) -> dict[str, Any] | None:
        raw_date = day.get("date")
        try:
            target_date = date.fromisoformat(str(raw_date))
        except (TypeError, ValueError):
            day["weather"] = None
            return {
                "service": "qweather",
                "code": "INVALID_DAY_DATE",
                "date": raw_date,
                "message": "行程日期无效，未回填天气",
            }
        try:
            weather = await client.weather_for_date(
                city_code=city_code,
                target_date=target_date,
            )
        except AppError as exc:
            day["weather"] = None
            return {
                "service": "qweather",
                "code": exc.code,
                "date": target_date.isoformat(),
                "message": exc.message,
            }
        queried_at = weather.get("queried_at")
        if isinstance(queried_at, datetime):
            queried_at = queried_at.isoformat()
        summary = weather.get("condition_day") or weather.get("condition_night") or "未知"
        day["weather"] = {
            "summary": summary,
            "rain_prob": _rain_probability(weather.get("precipitation_probability")),
            "source": "qweather_stale" if weather.get("stale") else "qweather",
            "fetched_at": queried_at,
        }
        return None

    warnings = [
        warning
        for warning in await asyncio.gather(
            *(enrich_day(day) for day in enriched.get("days", []))
        )
        if warning is not None
    ]
    return enriched, warnings
