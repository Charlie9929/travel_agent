import re
from copy import deepcopy
from datetime import UTC, datetime
from difflib import SequenceMatcher
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
    search_city = _search_city(city)

    for day in enriched.get("days", []):
        for activity in day.get("activities", []):
            location = activity.get("location")
            if not isinstance(location, dict):
                continue

            # An LLM is never trusted as the source of a provider POI identifier.
            location["poi_id"] = None
            location["poi_source"] = None
            location["lng"] = None
            location["lat"] = None
            location["address"] = None
            if activity.get("title"):
                location["name"] = activity["title"]
            keyword = activity.get("title") or location.get("name")
            if not keyword:
                continue

            result = await client.search_poi(keyword=str(keyword), city=search_city)
            poi = _pick_poi(result.get("items", []), str(keyword), city)
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
            queried_at = result.get("queried_at")
            if isinstance(queried_at, datetime):
                queried_at = queried_at.astimezone(UTC).isoformat()
            if poi.get("open_hours"):
                activity["open_hours_hint"] = str(poi["open_hours"])
                activity["open_hours_source"] = "amap"
                activity["open_hours_fetched_at"] = queried_at
            if poi.get("average_cost") is not None:
                activity["quoted_cost"] = {
                    "amount": poi["average_cost"],
                    "currency": "CNY",
                    "price_type": "quoted",
                    "source": "amap",
                    "fetched_at": queried_at,
                    "note": "高德商户参考人均，非购票价格",
                }
            if city_info["adcode"] is None:
                city_info["adcode"] = poi.get("adcode")
            if city_info["province"] is None:
                city_info["province"] = poi.get("province")

    return enriched


def _pick_poi(items: list[dict[str, Any]], keyword: str, target_area: str) -> dict[str, Any] | None:
    regional_items = [item for item in items if _is_in_target_area(item, target_area)]
    if not regional_items:
        return None
    normalized_keyword = _normalize_name(keyword)
    ranked = sorted(
        regional_items,
        key=lambda item: _name_score(
            normalized_keyword, _normalize_name(str(item.get("name") or ""))
        ),
        reverse=True,
    )
    best = ranked[0]
    best_score = _name_score(normalized_keyword, _normalize_name(str(best.get("name") or "")))
    return best if best_score >= 0.48 else None


def _normalize_name(value: str) -> str:
    value = re.sub(r"[（(].*?[）)]", "", value)
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]", "", value).casefold()


def _name_score(keyword: str, candidate: str) -> float:
    if not keyword or not candidate:
        return 0.0
    if keyword == candidate:
        return 1.0
    if keyword in candidate or candidate in keyword:
        shorter = min(len(keyword), len(candidate))
        longer = max(len(keyword), len(candidate))
        return 0.75 + 0.25 * shorter / longer
    return SequenceMatcher(None, keyword, candidate).ratio()


def _search_city(value: str) -> str:
    compact = "".join(value.split())
    if compact.isdigit():
        return compact
    city_matches = re.findall(r"([^省自治区特别行政区]+市)", compact)
    if city_matches:
        return city_matches[-1].removesuffix("市")
    return compact


def _is_in_target_area(item: dict[str, Any], target_area: str) -> bool:
    target = "".join(target_area.split())
    target_city = _search_city(target).removesuffix("市")
    item_city = str(item.get("city") or "").removesuffix("市")
    if target_city and item_city and target_city != item_city:
        return False
    district_matches = re.findall(r"([^市省]+(?:区|县|旗))", target)
    target_district = district_matches[-1] if district_matches else ""
    item_district = str(item.get("district") or "")
    if target_district and item_district and target_district != item_district:
        return False
    return bool(item_city or item.get("adcode"))
