from datetime import date

from fastapi import APIRouter, Query

from app.api.dependencies import CurrentUser
from app.core.config import get_settings
from app.integrations.qweather import QWeatherClient
from app.schemas.common import ApiResponse

router = APIRouter(tags=["weather"])


def get_qweather_client() -> QWeatherClient:
    settings = get_settings()
    return QWeatherClient(
        api_host=settings.qweather_api_host,
        auth_type=settings.qweather_auth_type,
        api_key=settings.qweather_api_key,
        jwt_token=settings.qweather_jwt_token,
        timeout_seconds=settings.qweather_timeout_seconds,
    )


@router.get("/weather", response_model=ApiResponse[dict])
async def weather(
    current_user: CurrentUser,
    city_code: str = Query(min_length=1, max_length=30),
    target_date: date = Query(alias="date"),
) -> ApiResponse[dict]:
    del current_user
    return ApiResponse(
        data=await get_qweather_client().weather_for_date(
            city_code=city_code, target_date=target_date
        )
    )
