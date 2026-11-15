import re
from copy import deepcopy
from datetime import UTC, datetime
from difflib import SequenceMatcher
from math import asin, cos, radians, sin, sqrt
from typing import Any

from app.integrations.amap import AmapClient

CLOSED_POI_RE = re.compile(
    r"暂停营业|暂停开放|暂停接待|暂停参观|暂停入园|临时闭园|暂时闭园|"
    r"临时关闭|永久关闭|已关闭|停止营业|停业|歇业|闭馆|闭店"
)


def poi_unavailable_reason(poi: dict[str, Any]) -> str | None:
    evidence = " ".join(
        str(poi.get(key) or "") for key in ("name", "business_status", "open_hours")
    )
    match = CLOSED_POI_RE.search(evidence)
    return match.group(0) if match else None


async def resolve_activity_poi(
    *,
    location_name: str,
    city: str,
    client: AmapClient,
    anchors: list[tuple[float, float]] | None = None,
    expected_type: str | None = None,
) -> dict[str, Any] | None:
    """Resolve one manually entered activity location to a reliable Amap POI."""
    keyword = _clean_poi_keyword(location_name)
    if not keyword:
        return None
    result = await client.search_poi(keyword=keyword, city=_search_city(city))
    return _pick_poi(
        result.get("items", []),
        keyword,
        city,
        anchors=anchors,
        expected_type=expected_type,
    )


async def enrich_itinerary_pois(
    data: dict[str, Any],
    *,
    city: str,
    client: AmapClient,
    origin_city: str | None = None,
    verified_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Replace LLM location guesses with POI data returned by Amap."""
    enriched = deepcopy(data)
    city_info = enriched.setdefault("city", {"name": city})
    city_info["adcode"] = None
    city_info["province"] = None
    destination_search_city = _search_city(city)
    verified_by_id = {
        str(item["poi_id"]): _candidate_as_poi(item)
        for item in (verified_candidates or [])
        if item.get("poi_id")
    }
    trip_anchors: list[tuple[float, float]] = []
    resolution_issues: list[dict[str, Any]] = []

    for day in enriched.get("days", []):
        day_anchors: list[tuple[float, float]] = []
        for activity in day.get("activities", []):
            location = activity.get("location")
            if not isinstance(location, dict):
                continue

            requested_name = str(location.get("name") or "").strip()
            requested_poi_id = str(location.get("poi_id") or "").strip() or None
            # An LLM is never trusted as the source of a provider POI identifier.
            location["poi_id"] = None
            location["poi_source"] = None
            location["lng"] = None
            location["lat"] = None
            location["address"] = None
            keyword = _clean_poi_keyword(requested_name or str(activity.get("title") or ""))
            if not keyword:
                continue
            location["name"] = requested_name or keyword
            target_area = _activity_search_area(
                activity,
                destination_city=city,
                origin_city=origin_city,
            )
            search_city = _search_city(target_area)
            is_destination_area = search_city == destination_search_city

            result: dict[str, Any] = {"items": []}
            poi = verified_by_id.get(requested_poi_id or "")
            if poi is None:
                result = await client.search_poi(keyword=str(keyword), city=search_city)
                poi = _pick_poi(
                    result.get("items", []),
                    str(keyword),
                    target_area,
                    anchors=day_anchors or trip_anchors,
                    requested_poi_id=requested_poi_id,
                    expected_type=str(activity.get("type") or "") or None,
                )
            if poi is None:
                resolution_issues.append(
                    {
                        "code": "POI_MATCH_UNCERTAIN",
                        "activity_id": activity.get("activity_id"),
                        "title": activity.get("title"),
                        "query": keyword,
                        "search_city": search_city,
                        "message": "没有找到兼顾名称、行政区和当前行程位置的可靠地点",
                        "candidates": _candidate_evidence(
                            result.get("items", []),
                            anchors=day_anchors or trip_anchors,
                        ),
                    }
                )
                continue

            unavailable_reason = poi_unavailable_reason(poi)
            if unavailable_reason:
                resolution_issues.append(
                    {
                        "code": "POI_UNAVAILABLE",
                        "activity_id": activity.get("activity_id"),
                        "title": activity.get("title"),
                        "query": keyword,
                        "matched_name": poi.get("name"),
                        "message": (
                            f"高德地点标记为“{unavailable_reason}”，"
                            "必须替换为正常营业的地点"
                        ),
                    }
                )
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
            coordinates = _coordinates(poi)
            # The departure station may be in another city. It should be verified, but it
            # must not pull destination POI matching toward the origin-city coordinate.
            if coordinates is not None and is_destination_area:
                day_anchors.append(coordinates)
                trip_anchors.append(coordinates)
            queried_at = result.get("queried_at")
            if isinstance(queried_at, datetime):
                queried_at = queried_at.astimezone(UTC).isoformat()
            if poi.get("open_hours") and activity.get("type") != "transport":
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
            if is_destination_area and city_info["adcode"] is None:
                city_info["adcode"] = poi.get("adcode")
            if is_destination_area and city_info["province"] is None:
                city_info["province"] = poi.get("province")

    enriched["_poi_resolution_issues"] = resolution_issues
    return enriched


def _pick_poi(
    items: list[dict[str, Any]],
    keyword: str,
    target_area: str,
    *,
    anchors: list[tuple[float, float]] | None = None,
    requested_poi_id: str | None = None,
    expected_type: str | None = None,
) -> dict[str, Any] | None:
    regional_items = [item for item in items if _is_in_target_area(item, target_area)]
    if not regional_items:
        return None
    if requested_poi_id:
        return next(
            (item for item in regional_items if str(item.get("poi_id") or "") == requested_poi_id),
            None,
        )
    normalized_keyword = _normalize_name(keyword)
    anchors = anchors or []

    def rank(item: dict[str, Any]) -> float:
        name_score = _name_score(normalized_keyword, _normalize_name(str(item.get("name") or "")))
        distance = _distance_to_anchors(item, anchors)
        proximity_bonus = 0.0 if distance is None else max(0.0, 0.2 - distance / 250.0)
        return name_score + proximity_bonus + _type_match_bonus(item, expected_type)

    ranked = sorted(
        regional_items,
        key=rank,
        reverse=True,
    )
    best = ranked[0]
    normalized_best = _normalize_name(str(best.get("name") or ""))
    best_score = _name_score(normalized_keyword, normalized_best)
    distance = _distance_to_anchors(best, anchors)
    if best_score < 0.55:
        return None
    # A non-exact shop/branch far outside the current itinerary cluster is more likely
    # to be a same-city administrative match than the place the user intended.
    if anchors and distance is not None and distance > 40 and normalized_keyword != normalized_best:
        return None
    return best


def _candidate_as_poi(item: dict[str, Any]) -> dict[str, Any]:
    return {
        **item,
        "longitude": item.get("longitude", item.get("lng")),
        "latitude": item.get("latitude", item.get("lat")),
    }


def _clean_poi_keyword(value: str) -> str:
    compact = re.sub(r"[（(].*?[）)]", "", value).strip()
    compact = re.sub(
        r"^(?:早餐|早午餐|午餐|下午茶|晚餐|夜宵|住宿|酒店|游览|参观|打卡)\s*[：:：\-—]?\s*",
        "",
        compact,
    )
    return compact.strip(" ，,、；;：:")


def _activity_search_area(
    activity: dict[str, Any], *, destination_city: str, origin_city: str | None
) -> str:
    """Use the trip origin for an explicitly origin-city transport endpoint."""
    if not origin_city or activity.get("type") != "transport":
        return destination_city
    location = activity.get("location") or {}
    location_name = str(location.get("name") or "") if isinstance(location, dict) else ""
    normalized_location = _normalize_name(location_name)
    normalized_origin = _normalize_name(_search_city(origin_city))
    normalized_destination = _normalize_name(_search_city(destination_city))
    if normalized_destination and normalized_destination in normalized_location:
        return destination_city
    if normalized_origin and normalized_origin in normalized_location:
        return origin_city
    return destination_city


def _normalize_name(value: str) -> str:
    def keep_meaningful_qualifier(match: re.Match[str]) -> str:
        qualifier = match.group(1)
        return qualifier if re.search(
            r"地铁站|火车站|高铁站|机场|航站楼|汽车站|客运站|公交站|码头", qualifier
        ) else ""

    value = re.sub(r"[（(](.*?)[）)]", keep_meaningful_qualifier, value)
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]", "", value).casefold()


def _type_match_bonus(item: dict[str, Any], expected_type: str | None) -> float:
    if expected_type != "transport":
        return 0.0
    evidence = f"{item.get('name') or ''} {item.get('type') or ''}"
    return 0.25 if re.search(
        r"交通设施|地铁站|火车站|高铁站|机场|航站楼|汽车站|客运站|公交站|码头",
        evidence,
    ) else -0.1


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


def _coordinates(item: dict[str, Any]) -> tuple[float, float] | None:
    try:
        longitude = float(item["longitude"])
        latitude = float(item["latitude"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        return None
    return longitude, latitude


def _distance_to_anchors(item: dict[str, Any], anchors: list[tuple[float, float]]) -> float | None:
    coordinates = _coordinates(item)
    if coordinates is None or not anchors:
        return None
    return min(_haversine_km(coordinates, anchor) for anchor in anchors)


def _candidate_evidence(
    items: list[dict[str, Any]], *, anchors: list[tuple[float, float]]
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for item in items[:5]:
        distance = _distance_to_anchors(item, anchors)
        evidence.append(
            {
                "poi_id": item.get("poi_id"),
                "name": item.get("name"),
                "address": item.get("address"),
                "city": item.get("city"),
                "district": item.get("district"),
                "longitude": item.get("longitude"),
                "latitude": item.get("latitude"),
                "distance_to_itinerary_km": round(distance, 1) if distance is not None else None,
            }
        )
    return evidence


def _haversine_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    first_lng, first_lat = map(radians, first)
    second_lng, second_lat = map(radians, second)
    delta_lng = second_lng - first_lng
    delta_lat = second_lat - first_lat
    value = sin(delta_lat / 2) ** 2 + cos(first_lat) * cos(second_lat) * sin(delta_lng / 2) ** 2
    return 2 * 6371.0088 * asin(sqrt(value))


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
