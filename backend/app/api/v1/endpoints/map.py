from fastapi import APIRouter, Query

from app.api.dependencies import CurrentUser
from app.core.config import get_settings
from app.integrations.amap import AmapClient
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/map", tags=["map"])


def get_amap_client() -> AmapClient:
    settings = get_settings()
    return AmapClient(
        base_url=settings.amap_base_url,
        api_key=settings.amap_api_key,
        timeout_seconds=settings.amap_timeout_seconds,
        min_interval_seconds=settings.amap_min_interval_seconds,
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


@router.get("/route", response_model=ApiResponse[dict])
async def route(
    current_user: CurrentUser,
    from_lat: float = Query(ge=-90, le=90),
    from_lng: float = Query(ge=-180, le=180),
    to_lat: float = Query(ge=-90, le=90),
    to_lng: float = Query(ge=-180, le=180),
    city_code: str | None = Query(default=None),
) -> ApiResponse[dict]:
    del current_user
    return ApiResponse(
        data=await get_amap_client().routes(
            from_lng=from_lng,
            from_lat=from_lat,
            to_lng=to_lng,
            to_lat=to_lat,
            city_code=city_code,
        )
    )
