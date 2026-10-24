from copy import deepcopy
from typing import Any

from app.integrations.amap import AmapClient


async def enrich_itinerary_pois(
    data: dict[str, Any], *, city: str, client: AmapClient
) -> dict[str, Any]:
    """Replace LLM location guesses with POI data returned by Amap."""
    enriched = deepcopy(data)
    city_info = enriched.setdefault("city", {"name": city})
    city_info["adcode"] = None
    city_info["province"] = None

    for day in enriched.get("days", []):
        for activity in day.get("activities", []):
            location = activity.get("location")
            if not isinstance(location, dict):
                continue

            # An LLM is never trusted as the source of a provider POI identifier.
            location["poi_id"] = None
            location["poi_source"] = None
            keyword = location.get("name") or activity.get("title")
            if not keyword:
                continue

            result = await client.search_poi(keyword=str(keyword), city=city)
            poi = _pick_poi(result.get("items", []), str(keyword))
            if poi is None:
                continue

            location.update(
                {
                    "name": poi.get("name") or keyword,
                    "address": poi.get("address"),
                    "lng": poi.get("longitude"),
                    "lat": poi.get("latitude"),
                    "poi_id": poi.get("poi_id"),
                    "poi_source": "amap",
                }
            )
            if city_info["adcode"] is None:
                city_info["adcode"] = poi.get("adcode")
            if city_info["province"] is None:
                city_info["province"] = poi.get("province")

    return enriched


def _pick_poi(items: list[dict[str, Any]], keyword: str) -> dict[str, Any] | None:
    if not items:
        return None
    normalized_keyword = _normalize_name(keyword)
    return next(
        (
            item
            for item in items
            if _normalize_name(str(item.get("name") or "")) == normalized_keyword
        ),
        items[0],
    )


def _normalize_name(value: str) -> str:
    return "".join(value.split()).casefold()
