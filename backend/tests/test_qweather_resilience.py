from datetime import date

import httpx
import pytest

from app.integrations.qweather import QWeatherClient


class FakeResponse:
    def __init__(self, body: dict) -> None:
        self.body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.body


class FakeHttpClient:
    def __init__(self) -> None:
        self.calls = 0

    async def __aenter__(self) -> "FakeHttpClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, url: str, **kwargs: object) -> FakeResponse:
        del kwargs
        self.calls += 1
        if self.calls == 1:
            raise httpx.TimeoutException("timeout")
        if "city/lookup" in url:
            return FakeResponse(
                {"location": [{"id": "101270101", "name": "成都", "lat": "30.67", "lon": "104.06"}]}
            )
        return FakeResponse(
            {
                "days": [
                    {
                        "forecastStartTime": "2026-11-05T00:00:00+08:00",
                        "daytime": {
                            "condition": {"text": "多云"},
                            "precipitation": {"probability": "20"},
                        },
                        "nighttime": {"condition": {"text": "晴"}},
                        "temperatureMin": {"value": "12"},
                        "temperatureMax": {"value": "20"},
                    },
                    {
                        "forecastStartTime": "2026-11-06T00:00:00+08:00",
                        "daytime": {
                            "condition": {"text": "小雨"},
                            "precipitation": {"probability": "60"},
                        },
                        "nighttime": {"condition": {"text": "阴"}},
                        "temperatureMin": {"value": "11"},
                        "temperatureMax": {"value": "18"},
                    },
                ],
                "metadata": {"attributions": []},
            }
        )


@pytest.mark.asyncio
async def test_qweather_retries_and_reuses_forecast_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_http = FakeHttpClient()
    monkeypatch.setattr(
        "app.integrations.qweather.client.httpx.AsyncClient",
        lambda **kwargs: fake_http,
    )
    async def no_sleep(seconds: float) -> None:
        del seconds

    monkeypatch.setattr("app.integrations.qweather.client.asyncio.sleep", no_sleep)
    client = QWeatherClient(
        api_host="example.qweatherapi.com",
        auth_type="api_key",
        api_key="test-key",
        jwt_token="",
        retries=1,
        cache_ttl_seconds=600,
    )

    first = await client.weather_for_date(
        city_code="成都", target_date=date(2026, 11, 5)
    )
    second = await client.weather_for_date(
        city_code="成都", target_date=date(2026, 11, 6)
    )

    assert first["condition_day"] == "多云"
    assert second["condition_day"] == "小雨"
    assert fake_http.calls == 3
