import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.errors import AppError


class AmapClient:
    RATE_LIMIT_INFOCODES = {"10004", "10014", "10015", "10019", "10020", "10021"}

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 10.0,
        min_interval_seconds: float = 1.1,
        rate_limit_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.min_interval_seconds = min_interval_seconds
        self.rate_limit_retries = rate_limit_retries
        self._last_request_at = 0.0
        self._rate_lock = asyncio.Lock()
        self._poi_cache: dict[tuple[str, str], dict[str, Any]] = {}

    def _require_key(self) -> None:
        if not self.api_key:
            raise AppError("AMAP_NOT_CONFIGURED", "未配置高德 Web 服务 API Key", status_code=503)

    async def search_poi(self, *, keyword: str, city: str) -> dict[str, Any]:
        self._require_key()
        cache_key = (city.strip().casefold(), keyword.strip().casefold())
        if cache_key in self._poi_cache:
            return self._poi_cache[cache_key]

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            body = await self._search_poi_with_retry(client=client, keyword=keyword, city=city)
        pois = []
        for poi in body.get("pois", []):
            lng, lat = (poi.get("location") or ",").split(",", maxsplit=1)
            pois.append(
                {
                    "poi_id": poi.get("id"),
                    "name": poi.get("name"),
                    "address": poi.get("address") or None,
                    "type": poi.get("type") or None,
                    "adcode": poi.get("adcode") or None,
                    "province": poi.get("pname") or None,
                    "longitude": float(lng) if lng else None,
                    "latitude": float(lat) if lat else None,
                }
            )
        result = {"items": pois, "provider": "amap", "queried_at": datetime.now(UTC)}
        self._poi_cache[cache_key] = result
        return result

    async def _search_poi_with_retry(
        self, *, client: httpx.AsyncClient, keyword: str, city: str
    ) -> dict[str, Any]:
        params = {
            "key": self.api_key,
            "keywords": keyword,
            "city": city,
            "citylimit": "true",
            "offset": 20,
            "page": 1,
            "extensions": "all",
            "output": "JSON",
        }
        for attempt in range(self.rate_limit_retries + 1):
            await self._wait_for_rate_slot()
            try:
                response = await client.get(f"{self.base_url}/v3/place/text", params=params)
                response.raise_for_status()
            except httpx.TimeoutException as exc:
                raise AppError("AMAP_TIMEOUT", "高德地图查询超时", status_code=502) from exc
            except httpx.HTTPError as exc:
                raise AppError("AMAP_UNAVAILABLE", "高德地图服务不可用", status_code=502) from exc

            body = response.json()
            if body.get("status") == "1":
                return body

            infocode = str(body.get("infocode") or "")
            if infocode in self.RATE_LIMIT_INFOCODES and attempt < self.rate_limit_retries:
                await asyncio.sleep(2**attempt)
                continue
            if infocode in self.RATE_LIMIT_INFOCODES:
                raise AppError(
                    "AMAP_RATE_LIMIT",
                    "高德地图调用频率超限，请稍后重试",
                    status_code=429,
                    detail={"infocode": infocode},
                )
            raise AppError(
                "AMAP_ERROR",
                body.get("info", "高德地图查询失败"),
                status_code=502,
                detail={"infocode": infocode},
            )
        raise RuntimeError("unreachable")

    async def _wait_for_rate_slot(self) -> None:
        async with self._rate_lock:
            elapsed = time.monotonic() - self._last_request_at
            wait_seconds = self.min_interval_seconds - elapsed
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            self._last_request_at = time.monotonic()

    async def routes(
        self,
        *,
        from_lng: float,
        from_lat: float,
        to_lng: float,
        to_lat: float,
        city_code: str | None = None,
    ) -> dict[str, Any]:
        self._require_key()
        origin = f"{from_lng:.6f},{from_lat:.6f}"
        destination = f"{to_lng:.6f},{to_lat:.6f}"
        specs = {
            "walk": ("/v5/direction/walking", {"show_fields": "cost"}),
            "bike": ("/v5/direction/bicycling", {"show_fields": "cost"}),
            "drive": ("/v5/direction/driving", {"show_fields": "cost", "strategy": 32}),
        }
        results: dict[str, Any] = {}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for mode, (path, extra) in specs.items():
                params = {
                    "key": self.api_key,
                    "origin": origin,
                    "destination": destination,
                    **extra,
                }
                try:
                    response = await client.get(f"{self.base_url}{path}", params=params)
                    response.raise_for_status()
                    results[mode] = self._normalize_route(response.json())
                except httpx.HTTPError:
                    results[mode] = {"available": False}

            if city_code:
                try:
                    response = await client.get(
                        f"{self.base_url}/v5/direction/transit/integrated",
                        params={
                            "key": self.api_key,
                            "origin": origin,
                            "destination": destination,
                            "city1": city_code,
                            "city2": city_code,
                            "show_fields": "cost",
                        },
                    )
                    response.raise_for_status()
                    results["transit"] = self._normalize_route(response.json(), transit=True)
                except httpx.HTTPError:
                    results["transit"] = {"available": False}
            else:
                results["transit"] = {"available": False, "reason": "city_code_required"}
        return {"routes": results, "provider": "amap", "queried_at": datetime.now(UTC)}

    @staticmethod
    def _normalize_route(body: dict[str, Any], *, transit: bool = False) -> dict[str, Any]:
        if body.get("status") != "1":
            return {"available": False, "provider_code": body.get("infocode")}
        route = body.get("route") or {}
        candidates = route.get("transits" if transit else "paths") or []
        if not candidates:
            return {"available": False}
        first = candidates[0]
        cost = first.get("cost") or {}
        duration = cost.get("duration") or first.get("duration")
        return {
            "available": True,
            "distance_m": int(float(first.get("distance", 0))),
            "duration_min": round(float(duration) / 60) if duration else None,
        }
