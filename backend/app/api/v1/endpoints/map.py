import asyncio
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DbSession
from app.core.city_scope import canonical_city_adcode
from app.core.config import get_settings
from app.db.models import RouteCache
from app.db.session import AsyncSessionFactory
from app.integrations.amap import AmapClient
from app.schemas.common import ApiResponse
from app.schemas.map import RouteBatchRequest

router = APIRouter(prefix="/map", tags=["map"])


@lru_cache
def get_amap_client() -> AmapClient:
    settings = get_settings()
    return AmapClient(
        base_url=settings.amap_base_url,
        api_key=settings.amap_api_key,
        timeout_seconds=settings.amap_timeout_seconds,
        min_interval_seconds=settings.amap_min_interval_seconds,
        route_min_interval_seconds=settings.amap_route_min_interval_seconds,
        rate_limit_retries=settings.amap_rate_limit_retries,
    )


@router.get("/poi", response_model=ApiResponse[dict])
async def search_poi(
    current_user: CurrentUser,
    keyword: str = Query(min_length=1, max_length=100),
    city: str = Query(min_length=1, max_length=50),
) -> ApiResponse[dict]:
    del current_user
    return ApiResponse(data=await get_amap_client().search_poi(keyword=keyword, city=city))


@router.get("/districts", response_model=ApiResponse[dict])
async def districts(current_user: CurrentUser) -> ApiResponse[dict]:
    del current_user
    return ApiResponse(data=await get_amap_client().districts())


@router.get("/route", response_model=ApiResponse[dict])
async def route(
    current_user: CurrentUser,
    session: DbSession,
    from_lat: float = Query(ge=-90, le=90),
    from_lng: float = Query(ge=-180, le=180),
    to_lat: float = Query(ge=-90, le=90),
    to_lng: float = Query(ge=-180, le=180),
    city_code: str | None = Query(default=None),
    mode: Literal["walk", "bike", "drive", "transit"] | None = Query(default=None),
) -> ApiResponse[dict]:
    del current_user
    requested_modes = {mode} if mode else {"walk", "bike", "drive", "transit"}
    result = await _load_cached_routes(
        session=session,
        from_lat=from_lat,
        from_lng=from_lng,
        to_lat=to_lat,
        to_lng=to_lng,
        city_code=city_code,
        modes=requested_modes,
    )
    return ApiResponse(data={"routes": result})


async def _load_cached_routes(
    *,
    session: DbSession,
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
    city_code: str | None,
    modes: set[str],
) -> dict[str, dict]:
    settings = get_settings()
    origin_lat = f"{from_lat:.6f}"
    origin_lng = f"{from_lng:.6f}"
    destination_lat = f"{to_lat:.6f}"
    destination_lng = f"{to_lng:.6f}"
    normalized_city = canonical_city_adcode(city_code) if city_code else None
    now = datetime.now(UTC)
    routes: dict[str, dict] = {}
    missing: set[str] = set()
    for current_mode in modes:
        cached = await session.scalar(
            select(RouteCache).where(
                RouteCache.origin_lat_key == origin_lat,
                RouteCache.origin_lng_key == origin_lng,
                RouteCache.destination_lat_key == destination_lat,
                RouteCache.destination_lng_key == destination_lng,
                RouteCache.mode == current_mode,
                RouteCache.city_code == normalized_city,
                RouteCache.strategy == "default",
                RouteCache.expires_at > now,
            )
        )
        if cached is None:
            missing.add(current_mode)
        else:
            routes[current_mode] = {**cached.result, "cache_hit": True}

    if missing:
        fetched = await get_amap_client().routes(
            from_lng=from_lng,
            from_lat=from_lat,
            to_lng=to_lng,
            to_lat=to_lat,
            city_code=normalized_city,
            modes=missing,
        )
        for current_mode in missing:
            value = fetched.get("routes", {}).get(current_mode, {"available": False})
            routes[current_mode] = value
            existing = await session.scalar(
                select(RouteCache).where(
                    RouteCache.origin_lat_key == origin_lat,
                    RouteCache.origin_lng_key == origin_lng,
                    RouteCache.destination_lat_key == destination_lat,
                    RouteCache.destination_lng_key == destination_lng,
                    RouteCache.mode == current_mode,
                    RouteCache.city_code == normalized_city,
                    RouteCache.strategy == "default",
                )
            )
            if existing is None:
                session.add(
                    RouteCache(
                        origin_lat_key=origin_lat,
                        origin_lng_key=origin_lng,
                        destination_lat_key=destination_lat,
                        destination_lng_key=destination_lng,
                        mode=current_mode,
                        city_code=normalized_city,
                        strategy="default",
                        result=value,
                        expires_at=now + timedelta(seconds=settings.route_cache_ttl_seconds),
                    )
                )
            else:
                existing.result = value
                existing.fetched_at = now
                existing.expires_at = now + timedelta(seconds=settings.route_cache_ttl_seconds)
        await session.commit()
    return routes


@router.post("/routes/batch", response_model=ApiResponse[dict])
async def route_batch(
    payload: RouteBatchRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[dict]:
    del current_user, session
    settings = get_settings()
    semaphore = asyncio.Semaphore(max(1, settings.amap_route_max_concurrency))

    async def load_item(item):
        async with semaphore:
            async with AsyncSessionFactory() as item_session:
                routes = await _load_cached_routes(
                    session=item_session,
                    from_lat=item.from_lat,
                    from_lng=item.from_lng,
                    to_lat=item.to_lat,
                    to_lng=item.to_lng,
                    city_code=item.city_code,
                    modes=set(item.modes),
                )
            return {"key": item.key, "routes": routes}

    # RouteCache writes are committed by each item; network calls themselves
    # are still bounded by the semaphore and independently rate limited per mode.
    items = await asyncio.gather(*(load_item(item) for item in payload.segments))
    return ApiResponse(
        data={
            "total": len(items),
            "completed": len(items),
            "items": items,
            "status": "completed",
        }
    )
