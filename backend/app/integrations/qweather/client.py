from datetime import UTC, date, datetime
from typing import Any

import httpx

from app.core.errors import AppError, NotFoundError


class QWeatherClient:
    def __init__(
        self,
        *,
        api_host: str,
        auth_type: str,
        api_key: str,
        jwt_token: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.api_host = api_host.removeprefix("https://").rstrip("/")
        self.auth_type = auth_type
        self.api_key = api_key
        self.jwt_token = jwt_token
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        if not self.api_host:
            raise AppError("QWEATHER_NOT_CONFIGURED", "未配置和风天气 API Host", status_code=503)
        if self.auth_type == "jwt":
            if not self.jwt_token:
                raise AppError("QWEATHER_NOT_CONFIGURED", "未配置和风天气 JWT", status_code=503)
            return {"Authorization": f"Bearer {self.jwt_token}"}
        if not self.api_key:
            raise AppError("QWEATHER_NOT_CONFIGURED", "未配置和风天气 API Key", status_code=503)
        return {"X-QW-Api-Key": self.api_key}

    async def weather_for_date(self, *, city_code: str, target_date: date) -> dict[str, Any]:
        headers = self._headers()
        base_url = f"https://{self.api_host}"
        async with httpx.AsyncClient(timeout=self.timeout_seconds, headers=headers) as client:
            try:
                location_response = await client.get(
                    f"{base_url}/geo/v2/city/lookup",
                    params={"location": city_code, "range": "cn", "number": 1, "lang": "zh"},
                )
                location_response.raise_for_status()
                location_body = location_response.json()
                locations = location_body.get("location") or []
                if not locations:
                    raise NotFoundError("和风天气未找到该城市")
                location = locations[0]
                forecast_response = await client.get(
                    f"{base_url}/weather/v1/daily/{float(location['lat']):.2f}/{float(location['lon']):.2f}",
                    params={"days": 10, "localTime": "true", "lang": "zh"},
                )
                forecast_response.raise_for_status()
            except httpx.TimeoutException as exc:
                raise AppError("QWEATHER_TIMEOUT", "和风天气查询超时", status_code=502) from exc
            except httpx.HTTPError as exc:
                raise AppError(
                    "QWEATHER_UNAVAILABLE", "和风天气服务不可用", status_code=502
                ) from exc

        forecast_body = forecast_response.json()
        matched = None
        for item in forecast_body.get("days", []):
            start = item.get("forecastStartTime", "")
            if start[:10] == target_date.isoformat():
                matched = item
                break
        if matched is None:
            raise NotFoundError("该日期不在和风天气当前可查询的预报范围内")
        precipitation = (matched.get("daytime") or {}).get("precipitation") or {}
        return {
            "city": location.get("name"),
            "city_code": location.get("id"),
            "date": target_date,
            "condition_day": ((matched.get("daytime") or {}).get("condition") or {}).get("text"),
            "condition_night": ((matched.get("nighttime") or {}).get("condition") or {}).get(
                "text"
            ),
            "temperature_min": (matched.get("temperatureMin") or {}).get("value"),
            "temperature_max": (matched.get("temperatureMax") or {}).get("value"),
            "precipitation_probability": precipitation.get("probability"),
            "provider": "qweather",
            "queried_at": datetime.now(UTC),
            "attributions": (forecast_body.get("metadata") or {}).get("attributions", []),
        }
