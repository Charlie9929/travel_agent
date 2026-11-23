import asyncio
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Query

from app.api.dependencies import CurrentUser, DbSession
from app.core.config import get_settings
from app.db.session import AsyncSessionFactory
from app.integrations.amap import AmapClient
from app.schemas.common import ApiResponse
from app.schemas.map import RouteBatchRequest
from app.services.route_cache import load_cached_routes

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
    return await load_cached_routes(
        session=session,
        client=get_amap_client(),
        from_lat=from_lat,
        from_lng=from_lng,
        to_lat=to_lat,
        to_lng=to_lng,
        city_code=city_code,
        modes=modes,
    )


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
