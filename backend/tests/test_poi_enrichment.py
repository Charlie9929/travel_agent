import pytest

from app.services.poi_enrichment import (
    _clean_poi_keyword,
    _pick_poi,
    _search_city,
    enrich_itinerary_pois,
    resolve_activity_poi,
)


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


class ManualActivityStubAmapClient:
    async def search_poi(self, *, keyword: str, city: str) -> dict:
        assert keyword == "上海动物园游览"
        assert city == "上海"
        return {
            "items": [
                {
                    "poi_id": "B00155M7QZ",
                    "name": "上海动物园",
                    "city": "上海市",
                    "district": "长宁区",
                    "adcode": "310105",
                    "longitude": 121.364071,
                    "latitude": 31.194676,
                }
            ]
        }


@pytest.mark.asyncio
async def test_manual_activity_location_is_resolved_to_verified_amap_poi() -> None:
    poi = await resolve_activity_poi(
        location_name="上海动物园游览",
        city="上海",
        client=ManualActivityStubAmapClient(),  # type: ignore[arg-type]
        anchors=[(121.45, 31.20)],
        expected_type="sight",
    )

    assert poi is not None
    assert poi["poi_id"] == "B00155M7QZ"
    assert poi["name"] == "上海动物园"


class CleanKeywordStubAmapClient:
    def __init__(self) -> None:
        self.keywords: list[str] = []

    async def search_poi(self, *, keyword: str, city: str) -> dict:
        self.keywords.append(keyword)
        assert city == "成都"
        return {"items": []}


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


@pytest.mark.asyncio
async def test_enrichment_prefers_clean_location_name_over_activity_description() -> None:
    client = CleanKeywordStubAmapClient()
    source = {
        "city": {"name": "成都"},
        "days": [
            {
                "activities": [
                    {
                        "title": "晚餐：老码头火锅（鸳鸯锅，可选清汤）",
                        "location": {"name": "老码头火锅", "poi_source": "llm"},
                    }
                ]
            }
        ],
    }

    enriched = await enrich_itinerary_pois(source, city="成都", client=client)  # type: ignore[arg-type]

    assert client.keywords == ["老码头火锅"]
    assert enriched["days"][0]["activities"][0]["location"]["name"] == "老码头火锅"
    assert enriched["days"][0]["activities"][0]["location"]["lng"] is None


@pytest.mark.asyncio
async def test_transport_poi_uses_origin_city_only_for_origin_endpoint() -> None:
    class CrossCityStubAmapClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def search_poi(self, *, keyword: str, city: str) -> dict:
            self.calls.append((keyword, city))
            if (keyword, city) == ("广州南站", "广州"):
                return {
                    "items": [
                        {
                            "poi_id": "GZ-SOUTH",
                            "name": "广州南站",
                            "city": "广州市",
                            "district": "番禺区",
                            "longitude": 113.269,
                            "latitude": 22.989,
                        }
                    ]
                }
            if (keyword, city) == ("肇庆站", "肇庆"):
                return {
                    "items": [
                        {
                            "poi_id": "ZQ-STATION",
                            "name": "肇庆站",
                            "city": "肇庆市",
                            "district": "端州区",
                            "longitude": 112.465,
                            "latitude": 23.078,
                            "adcode": "441202",
                            "province": "广东省",
                        }
                    ]
                }
            return {"items": []}

    client = CrossCityStubAmapClient()
    source = {
        "city": {"name": "肇庆"},
        "days": [
            {
                "activities": [
                    {
                        "activity_id": "a1",
                        "type": "transport",
                        "title": "广州南站乘城际前往肇庆站",
                        "location": {"name": "广州南站"},
                    }
                ]
            },
            {
                "activities": [
                    {
                        "activity_id": "a2",
                        "type": "transport",
                        "title": "肇庆站乘城际返回广州南站",
                        "location": {"name": "肇庆站"},
                    }
                ]
            },
        ],
    }

    enriched = await enrich_itinerary_pois(
        source,
        city="肇庆",
        origin_city="广州",
        client=client,  # type: ignore[arg-type]
    )

    assert client.calls == [("广州南站", "广州"), ("肇庆站", "肇庆")]
    first = enriched["days"][0]["activities"][0]["location"]
    last = enriched["days"][1]["activities"][0]["location"]
    assert first["poi_id"] == "GZ-SOUTH"
    assert last["poi_id"] == "ZQ-STATION"
    assert enriched["city"]["adcode"] == "441202"
    assert enriched["_poi_resolution_issues"] == []


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


def test_transport_matching_distinguishes_metro_station_from_temple() -> None:
    temple = {
        "poi_id": "TEMPLE",
        "name": "静安寺",
        "type": "风景名胜;寺庙道观",
        "city": "上海市",
        "district": "静安区",
    }
    metro = {
        "poi_id": "METRO",
        "name": "静安寺(地铁站)",
        "type": "交通设施服务;地铁站;地铁站",
        "city": "上海市",
        "district": "静安区",
    }

    assert (
        _pick_poi(
            [temple, metro],
            "静安寺地铁站",
            "上海",
            expected_type="transport",
        )
        == metro
    )


def test_poi_keyword_removes_meal_prefix_and_description() -> None:
    assert _clean_poi_keyword("晚餐：老码头火锅（鸳鸯锅，清汤给不太能吃辣的人）") == "老码头火锅"


def test_poi_matching_prefers_nearby_branch_within_itinerary_cluster() -> None:
    nearby = {
        "poi_id": "nearby",
        "name": "老码头火锅(玉林店)",
        "city": "成都市",
        "district": "武侯区",
        "adcode": "510107",
        "longitude": 104.055,
        "latitude": 30.64,
    }
    remote = {
        "poi_id": "remote",
        "name": "重庆老码头火锅(云西街店)",
        "city": "成都市",
        "district": "简阳市",
        "adcode": "510185",
        "longitude": 104.807251,
        "latitude": 30.417519,
    }
    assert (
        _pick_poi(
            [remote, nearby],
            "老码头火锅",
            "成都",
            anchors=[(104.063749, 30.657297)],
        )
        == nearby
    )


def test_poi_matching_rejects_remote_non_exact_branch() -> None:
    remote = {
        "poi_id": "remote",
        "name": "重庆老码头火锅(云西街店)",
        "city": "成都市",
        "district": "简阳市",
        "adcode": "510185",
        "longitude": 104.807251,
        "latitude": 30.417519,
    }
    assert (
        _pick_poi(
            [remote],
            "老码头火锅",
            "成都",
            anchors=[(104.063749, 30.657297)],
        )
        is None
    )


def test_poi_matching_keeps_explicit_remote_destination() -> None:
    dujiangyan = {
        "poi_id": "dujiangyan",
        "name": "都江堰景区",
        "city": "成都市",
        "district": "都江堰市",
        "adcode": "510181",
        "longitude": 103.6168,
        "latitude": 31.0017,
    }
    assert (
        _pick_poi(
            [dujiangyan],
            "都江堰景区",
            "成都",
            anchors=[(104.063749, 30.657297)],
        )
        == dujiangyan
    )


def test_poi_matching_uses_only_verified_requested_poi_id() -> None:
    nearby = {
        "poi_id": "nearby",
        "name": "老码头火锅(玉林店)",
        "city": "成都市",
        "district": "武侯区",
        "adcode": "510107",
        "longitude": 104.055,
        "latitude": 30.64,
    }
    remote = {
        "poi_id": "remote",
        "name": "重庆老码头火锅(云西街店)",
        "city": "成都市",
        "district": "简阳市",
        "adcode": "510185",
        "longitude": 104.807251,
        "latitude": 30.417519,
    }
    assert (
        _pick_poi(
            [remote, nearby],
            "老码头火锅",
            "成都",
            anchors=[(104.063749, 30.657297)],
            requested_poi_id="nearby",
        )
        == nearby
    )
    assert (
        _pick_poi(
            [remote, nearby],
            "老码头火锅",
            "成都",
            requested_poi_id="invented",
        )
        is None
    )


@pytest.mark.asyncio
async def test_uncertain_remote_branch_returns_evidence_for_agent_repair() -> None:
    anchor = {
        "poi_id": "anchor",
        "name": "宽窄巷子",
        "city": "成都市",
        "district": "青羊区",
        "adcode": "510105",
        "longitude": 104.055,
        "latitude": 30.67,
    }
    remote = {
        "poi_id": "remote",
        "name": "重庆老码头火锅(云西街店)",
        "address": "云西街",
        "city": "成都市",
        "district": "简阳市",
        "adcode": "510185",
        "longitude": 104.807251,
        "latitude": 30.417519,
    }

    class EvidenceStubAmapClient:
        async def search_poi(self, *, keyword: str, city: str) -> dict:
            assert city == "成都"
            return {"items": [anchor] if keyword == "宽窄巷子" else [remote]}

    source = {
        "city": {"name": "成都"},
        "days": [
            {
                "activities": [
                    {"activity_id": "a1", "title": "宽窄巷子", "location": {"name": "宽窄巷子"}},
                    {
                        "activity_id": "a2",
                        "title": "晚餐：老码头火锅",
                        "location": {"name": "老码头火锅"},
                    },
                ]
            }
        ],
    }

    enriched = await enrich_itinerary_pois(
        source,
        city="成都",
        client=EvidenceStubAmapClient(),  # type: ignore[arg-type]
    )

    issue = enriched["_poi_resolution_issues"][0]
    assert issue["activity_id"] == "a2"
    assert issue["candidates"][0]["district"] == "简阳市"
    assert issue["candidates"][0]["distance_to_itinerary_km"] > 40
    assert enriched["days"][0]["activities"][1]["location"]["lng"] is None


@pytest.mark.asyncio
async def test_enrichment_reuses_preverified_candidate_without_searching_again() -> None:
    class MustNotSearchClient:
        async def search_poi(self, *, keyword: str, city: str) -> dict:
            del keyword, city
            raise AssertionError("verified candidate should not be searched again")

    source = {
        "city": {"name": "长沙"},
        "days": [
            {
                "activities": [
                    {
                        "activity_id": "act-1",
                        "title": "岳麓书院",
                        "location": {"name": "岳麓书院", "poi_id": "B001"},
                    }
                ]
            }
        ],
    }
    candidate = {
        "poi_id": "B001",
        "name": "岳麓书院",
        "address": "麓山路",
        "lng": 112.944,
        "lat": 28.18,
        "adcode": "430104",
        "province": "湖南省",
    }

    enriched = await enrich_itinerary_pois(
        source,
        city="长沙",
        client=MustNotSearchClient(),  # type: ignore[arg-type]
        verified_candidates=[candidate],
    )

    location = enriched["days"][0]["activities"][0]["location"]
    assert location["poi_id"] == "B001"
    assert location["lng"] == 112.944
    assert enriched["_poi_resolution_issues"] == []
