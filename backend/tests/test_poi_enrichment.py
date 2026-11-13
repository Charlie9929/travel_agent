import pytest

from app.services.poi_enrichment import _pick_poi, _search_city, enrich_itinerary_pois


class StubAmapClient:
    async def search_poi(self, *, keyword: str, city: str) -> dict:
        assert keyword == "宽窄巷子"
        assert city == "成都"
        return {
            "items": [
                {
                    "poi_id": "B001",
                    "name": "宽窄巷子",
                    "address": "青羊区长顺上街",
                    "longitude": 104.055,
                    "latitude": 30.67,
                    "adcode": "510105",
                    "province": "四川省",
                }
            ]
        }


@pytest.mark.asyncio
async def test_poi_fields_are_replaced_with_amap_result() -> None:
    source = {
        "city": {"name": "成都", "adcode": "invented"},
        "days": [
            {
                "activities": [
                    {
                        "title": "宽窄巷子",
                        "location": {
                            "name": "宽窄巷子",
                            "poi_id": "llm-invented",
                            "poi_source": "llm",
                        },
                    }
                ]
            }
        ],
    }

    enriched = await enrich_itinerary_pois(
        source,
        city="成都",
        client=StubAmapClient(),  # type: ignore[arg-type]
    )

    location = enriched["days"][0]["activities"][0]["location"]
    assert location["poi_id"] == "B001"
    assert location["poi_source"] == "amap"
    assert location["lng"] == 104.055
    assert enriched["city"]["adcode"] == "510105"
    assert source["city"]["adcode"] == "invented"


def test_poi_matching_rejects_cross_city_and_unrelated_names() -> None:
    items = [
        {
            "poi_id": "wrong-city",
            "name": "逢简水乡",
            "city": "济宁市",
            "district": "邹城市",
            "adcode": "370883",
        },
        {
            "poi_id": "wrong-name",
            "name": "杏坛小区东区",
            "city": "佛山市",
            "district": "顺德区",
            "adcode": "440606",
        },
    ]
    assert _pick_poi(items, "逢简水乡", "佛山市顺德区") is None


def test_poi_matching_uses_foshan_scope_for_full_district_name() -> None:
    item = {
        "poi_id": "correct",
        "name": "逢简水乡",
        "city": "佛山市",
        "district": "顺德区",
        "adcode": "440606",
    }
    assert _search_city("广东省佛山市顺德区") == "佛山"
    assert _pick_poi([item], "逢简水乡", "广东省佛山市顺德区") == item
