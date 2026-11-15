from unittest.mock import AsyncMock

import pytest

from app.integrations.amap import AmapClient


class FakeResponse:
    def __init__(self, body: dict) -> None:
        self.body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.body


class FakeHttpClient:
    def __init__(self) -> None:
        self.responses = [
            FakeResponse(
                {"status": "0", "info": "CUQPS_HAS_EXCEEDED_THE_LIMIT", "infocode": "10021"}
            ),
            FakeResponse(
                {
                    "status": "1",
                    "pois": [
                        {
                            "id": "B001",
                            "name": "宽窄巷子",
                            "location": "104.055,30.670",
                        }
                    ],
                }
            ),
        ]
        self.calls = 0

    async def __aenter__(self) -> "FakeHttpClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, *args: object, **kwargs: object) -> FakeResponse:
        del args, kwargs
        response = self.responses[self.calls]
        self.calls += 1
        return response


@pytest.mark.asyncio
async def test_poi_search_retries_account_qps_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_http = FakeHttpClient()
    monkeypatch.setattr(
        "app.integrations.amap.client.httpx.AsyncClient", lambda **kwargs: fake_http
    )
    sleep = AsyncMock()
    monkeypatch.setattr("app.integrations.amap.client.asyncio.sleep", sleep)
    client = AmapClient(
        base_url="https://restapi.amap.com",
        api_key="test-key",
        min_interval_seconds=0,
        rate_limit_retries=2,
    )

    result = await client.search_poi(keyword="宽窄巷子", city="成都")

    assert fake_http.calls == 2
    assert result["items"][0]["poi_id"] == "B001"
    sleep.assert_awaited_once_with(1)


def test_normalize_route_includes_polyline_geometry() -> None:
    result = AmapClient._normalize_route(
        {
            "status": "1",
            "route": {
                "paths": [
                    {
                        "distance": "1250",
                        "cost": {"duration": "600"},
                        "steps": [
                            {"polyline": "113.100000,23.100000;113.200000,23.200000"},
                            {"polyline": "113.200000,23.200000;113.300000,23.300000"},
                        ],
                    }
                ]
            },
        }
    )

    assert result["available"] is True
    assert result["duration_min"] == 10
    assert result["path"] == [
        [113.1, 23.1],
        [113.2, 23.2],
        [113.3, 23.3],
    ]


def test_normalize_transit_route_collects_nested_polylines() -> None:
    result = AmapClient._normalize_route(
        {
            "status": "1",
            "route": {
                "transits": [
                    {
                        "distance": "3000",
                        "cost": {"duration": "1200"},
                        "segments": [
                            {"walking": {"steps": [{"polyline": "1,2;3,4"}]}},
                            {"bus": {"buslines": [{"polyline": "3,4;5,6"}]}},
                        ],
                    }
                ]
            },
        },
        transit=True,
    )

    assert result["path"] == [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]
