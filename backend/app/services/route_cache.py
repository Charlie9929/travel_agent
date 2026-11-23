from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.city_scope import canonical_city_adcode
from app.core.config import get_settings
from app.db.models import RouteCache
from app.integrations.amap import AmapClient


async def load_cached_routes(
    *,
    session: AsyncSession,
    client: AmapClient,
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
    city_code: str | None,
    modes: Iterable[str],
) -> dict[str, dict]:
    """Load routes from PostgreSQL and query AMap only for missing modes."""
    settings = get_settings()
    requested_modes = set(modes)
    origin_lat = f"{from_lat:.6f}"
    origin_lng = f"{from_lng:.6f}"
    destination_lat = f"{to_lat:.6f}"
    destination_lng = f"{to_lng:.6f}"
    normalized_city = canonical_city_adcode(city_code) if city_code else None
    now = datetime.now(UTC)
    routes: dict[str, dict] = {}
    missing: set[str] = set()
    for current_mode in requested_modes:
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

    if not missing:
        return routes

    fetched = await client.routes(
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
