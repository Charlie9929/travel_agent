"""Audit and repair verified POIs for the four product itineraries.

Run without --apply to print fresh Amap candidates. ``--apply`` uses only the
reviewed POI snapshot below, so a provider quota error can never cause a partial
or guessed database update.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import DayActivity, Trip, TripRevision
from app.db.session import AsyncSessionFactory
from app.integrations.amap import AmapClient
from app.services.poi_enrichment import _is_in_target_area
from app.services.versioning import bump_trip_version

TARGET_TRIP_IDS = (4, 30, 31, 32)

# Generic activities need a concrete search intent before candidate discovery.
SEARCH_QUERIES: dict[int, str] = {
    9: "成都火锅",
    11: "担担面 钟水饺 锦里",
    48: "长春站",
    49: "真不同百年吉菜老店长春总店",
    50: "长春市动植物公园",
    51: "状元阁烧烤新华路总店",
    52: "长春市中心酒店",
    53: "长影旧址博物馆",
    54: "餐谋家特色餐厅桂林路店",
    55: "桂林路商圈",
    56: "南湖公园",
    57: "鼎原力量吊炉烧烤临河街店",
    58: "长春市中心酒店",
    59: "农安县人民政府",
    60: "农安辽塔",
    61: "农安农家菜",
    62: "辽金时代文化园",
    63: "长春市中心酒店",
    64: "董鲁烤鸭工农大路店",
    65: "长春市中心酒店",
    66: "太平池国家湿地公园",
    67: "吉林农安太平池国家湿地公园",
    68: "太平池农家菜",
    69: "吉林农安太平池国家湿地公园",
    70: "长春市中心酒店",
    71: "小天厨民间菜馆深圳街店",
    72: "长春市中心酒店",
    73: "吉林省博物院",
    74: "长春净月潭益田喜来登酒店",
    75: "长影世纪城",
    76: "长春站",
    85: "黄但记陈村粉老店",
    93: "禄运茶居手工点心体育西店",
    99: "禄运茶居手工点心体育西店",
    105: "天河湿地公园",
    114: "龙的酒楼大良",
}

VERIFIED_SELECTIONS: dict[int, str] = {
    9: "B001C00AD4",
    11: "B0LRCZF51X",
    48: "B01AF0ZDGL",
    49: "B01AF05F6A",
    50: "B01AF0CMBW",
    51: "B01AF0AIUJ",
    52: "B0M1095QAI",
    53: "B0FFFDRU1K",
    54: "B0FFHJQW5L",
    55: "B0FFFDS1JJ",
    56: "B01AF07OT6",
    57: "B0FFH58GY5",
    58: "B0M1095QAI",
    59: "B01AF08AFJ",
    60: "B01AF02521",
    61: "B01AF107TA",
    62: "B0FFG8PX6K",
    63: "B0M1095QAI",
    64: "B0FFFQ1Q3V",
    65: "B0M1095QAI",
    66: "B0GUO75TSR",
    67: "B0GUO75TSR",
    68: "B0MDT5C9JX",
    69: "B0GUO75TSR",
    70: "B0M1095QAI",
    71: "B0FFHIQUJN",
    72: "B0M1095QAI",
    73: "B01AF0ZUPL",
    74: "B01AF0ZZPS",
    75: "B01AF0C3KB",
    76: "B01AF0ZDGL",
    85: "B0FFGGZ1MX",
    93: "B0FFHE5R5J",
    99: "B0FFHE5R5J",
    105: "B0FFGY9GBR",
    114: "B0FFG9TBD0",
}

# All values came from Amap Web Service responses or public Amap POI detail pages.
# Coordinates are stored as longitude/latitude, matching the application model.
VERIFIED_POIS: dict[str, dict] = {
    "B001C00AD4": {"name": "龙森园火锅(琴台路店)", "longitude": 104.045396, "latitude": 30.658815},
    "B0LRCZF51X": {"name": "钟水饺(文化公园店)", "longitude": 104.041225, "latitude": 30.659125},
    "B01AF0ZDGL": {"name": "长春站", "longitude": 125.324627, "latitude": 43.911282},
    "B01AF05F6A": {
        "name": "真不同·百年吉菜老店(长春总店)",
        "longitude": 125.337224,
        "latitude": 43.894921,
    },
    "B01AF0CMBW": {"name": "长春市动植物公园", "longitude": 125.335289, "latitude": 43.868108},
    "B01AF0AIUJ": {"name": "状元阁烧烤(新华路总店)", "longitude": 125.30358, "latitude": 43.892263},
    "B0M1095QAI": {"name": "长春万达中心酒店", "longitude": 125.291675, "latitude": 43.865975},
    "B0FFFDRU1K": {"name": "长影旧址博物馆", "longitude": 125.292355, "latitude": 43.86364},
    "B0FFHJQW5L": {
        "name": "餐谋家特色餐厅(桂林路店)",
        "longitude": 125.315979,
        "latitude": 43.866798,
    },
    "B0FFFDS1JJ": {"name": "桂林路", "longitude": 125.31833, "latitude": 43.867452},
    "B01AF07OT6": {"name": "南湖公园", "longitude": 125.306789, "latitude": 43.856452},
    "B0FFH58GY5": {
        "name": "鼎原力量吊炉烧烤主题餐厅(临河街店)",
        "longitude": 125.366011,
        "latitude": 43.819547,
    },
    "B01AF08AFJ": {"name": "农安县人民政府", "longitude": 125.184031, "latitude": 44.432386},
    "B01AF02521": {"name": "农安辽塔", "longitude": 125.175216, "latitude": 44.428565},
    "B01AF107TA": {"name": "野猪岭农家菜馆", "longitude": 125.180501, "latitude": 44.438732},
    "B0FFG8PX6K": {"name": "辽金时代文化园", "longitude": 125.285234, "latitude": 44.23181},
    "B0FFFQ1Q3V": {"name": "董鲁烤鸭(工农大路店)", "longitude": 125.313379, "latitude": 43.860446},
    "B0GUO75TSR": {
        "name": "吉林农安太平池国家湿地公园",
        "longitude": 124.895125,
        "latitude": 44.05198,
    },
    "B0MDT5C9JX": {"name": "太平岛农家小院", "longitude": 124.947873, "latitude": 44.067652},
    "B0FFHIQUJN": {
        "name": "小天厨民间菜馆(深圳街店)",
        "longitude": 125.373291,
        "latitude": 43.858711,
    },
    "B01AF0C3KB": {"name": "长影世纪城", "longitude": 125.446222, "latitude": 43.772507},
    "B01AF0ZUPL": {"name": "吉林省博物院", "longitude": 125.432521, "latitude": 43.768588},
    "B01AF0ZZPS": {
        "name": "长春净月潭益田喜来登酒店",
        "longitude": 125.433791,
        "latitude": 43.770836,
    },
    "B0FFGGZ1MX": {
        "name": "黄但记知味食府(陈村店)",
        "longitude": 113.238366,
        "latitude": 22.953228,
    },
    "B0FFHE5R5J": {
        "name": "禄运茶居·手工点心(体育西店)",
        "longitude": 113.32341,
        "latitude": 23.129805,
    },
    "B0FFGY9GBR": {"name": "天河湿地公园", "longitude": 113.418519, "latitude": 23.174828},
    "B0FFG9TBD0": {"name": "龙的酒楼", "longitude": 113.262942, "latitude": 22.820061},
}

TITLE_REPLACEMENTS = {
    9: "晚餐：龙森园火锅（琴台路店，可选鸳鸯锅）",
    11: "午餐：钟水饺（文化公园店）",
    61: "午餐：野猪岭农家菜馆",
    64: "晚餐：董鲁烤鸭（工农大路店）",
    68: "午餐：太平岛农家小院",
    71: "晚餐：小天厨民间菜馆（深圳街店）",
    74: "午餐：采悦轩中餐厅（长春净月潭益田喜来登酒店）",
    85: "黄但记知味食府（陈村店）",
    114: "龙的酒楼（大良）",
}


def _client() -> AmapClient:
    settings = get_settings()
    return AmapClient(
        base_url=settings.amap_base_url,
        api_key=settings.amap_api_key,
        timeout_seconds=settings.amap_timeout_seconds,
        min_interval_seconds=settings.amap_min_interval_seconds,
        rate_limit_retries=settings.amap_rate_limit_retries,
    )


async def main(*, apply: bool) -> None:
    client = _client()
    async with AsyncSessionFactory() as session:
        trips = {
            trip.id: trip
            for trip in (
                await session.scalars(select(Trip).where(Trip.id.in_(TARGET_TRIP_IDS)))
            ).all()
        }
        activities = (
            await session.scalars(
                select(DayActivity)
                .where(DayActivity.id.in_(SEARCH_QUERIES))
                .order_by(DayActivity.trip_id, DayActivity.day_number, DayActivity.order_index)
            )
        ).all()
        if not apply:
            for activity in activities:
                trip = trips[activity.trip_id]
                query = SEARCH_QUERIES[activity.id]
                result = await client.search_poi(keyword=query, city=trip.city)
                candidates = [
                    item for item in result.get("items", []) if _is_in_target_area(item, trip.city)
                ][:5]
                print(
                    f"\nactivity={activity.id} trip={trip.id} city={trip.city} "
                    f"title={activity.title!r} query={query!r}"
                )
                for item in candidates:
                    print(
                        "  ",
                        item.get("poi_id"),
                        item.get("name"),
                        item.get("district"),
                        item.get("address"),
                        item.get("longitude"),
                        item.get("latitude"),
                    )
            return
        missing = sorted(set(SEARCH_QUERIES) - set(VERIFIED_SELECTIONS))
        if missing:
            raise RuntimeError(f"未完成人工复核的活动：{missing}")

        changes_by_trip: dict[int, list[dict]] = {}
        for activity in activities:
            selected_id = VERIFIED_SELECTIONS[activity.id]
            selected = VERIFIED_POIS.get(selected_id)
            if selected is None:
                raise RuntimeError(f"活动 {activity.id} 的 POI {selected_id} 未保存复核快照")
            desired_title = TITLE_REPLACEMENTS.get(activity.id, activity.title)
            current_latitude = float(activity.latitude) if activity.latitude is not None else None
            current_longitude = (
                float(activity.longitude) if activity.longitude is not None else None
            )
            if (
                activity.title == desired_title
                and activity.location_name == selected["name"]
                and current_latitude == selected["latitude"]
                and current_longitude == selected["longitude"]
                and activity.poi_provider == "amap"
                and activity.poi_id == selected_id
            ):
                continue
            before = {
                "title": activity.title,
                "location_name": activity.location_name,
                "latitude": float(activity.latitude) if activity.latitude is not None else None,
                "longitude": float(activity.longitude) if activity.longitude is not None else None,
                "poi_provider": activity.poi_provider,
                "poi_id": activity.poi_id,
            }
            activity.title = desired_title
            activity.location_name = selected["name"]
            activity.latitude = selected["latitude"]
            activity.longitude = selected["longitude"]
            activity.poi_provider = "amap"
            activity.poi_id = selected_id
            activity.extra = {
                **(activity.extra or {}),
                "poi_verified_at": datetime.now(UTC).isoformat(),
                "poi_verification_query": SEARCH_QUERIES[activity.id],
                "poi_verification_source": "amap",
            }
            changes_by_trip.setdefault(activity.trip_id, []).append(
                {
                    "activity_id": activity.id,
                    "before": before,
                    "after": {
                        "title": activity.title,
                        "location_name": activity.location_name,
                        "latitude": activity.latitude,
                        "longitude": activity.longitude,
                        "poi_provider": activity.poi_provider,
                        "poi_id": activity.poi_id,
                    },
                }
            )

        for trip_id, changes in changes_by_trip.items():
            trip = trips[trip_id]
            new_version = await bump_trip_version(
                session,
                trip_id=trip_id,
                expected_version=trip.version,
                user_id=trip.creator_id,
                resource_type="activity",
                resource_id=None,
                submitted_content={"source": "verified_poi_repair", "changes": changes},
            )
            session.add(
                TripRevision(
                    trip_id=trip_id,
                    user_id=trip.creator_id,
                    version=new_version,
                    action="update",
                    resource_type="activity",
                    resource_id=None,
                    diff_content={"source": "verified_poi_repair", "changes": changes},
                )
            )
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv))
