from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.city_scope import canonical_city_adcode, canonical_city_selection
from app.integrations.amap import AmapClient
from app.schemas.trip import TripCreate
from app.services.trip_location import requires_intercity_transport


def test_intercity_decision_uses_city_adcodes_only() -> None:
    same_city = SimpleNamespace(
        city="广州市",
        origin_city="广州市番禺区",
        city_adcode="440100",
        origin_city_adcode="440100",
    )
    cross_city = SimpleNamespace(
        city="深圳市",
        origin_city="广州市",
        city_adcode="440300",
        origin_city_adcode="440100",
    )

    assert requires_intercity_transport(same_city) is False  # type: ignore[arg-type]
    assert requires_intercity_transport(cross_city) is True  # type: ignore[arg-type]

    legacy_cross_city = SimpleNamespace(
        city="深圳", origin_city="广州", city_adcode=None, origin_city_adcode=None
    )
    assert requires_intercity_transport(legacy_cross_city) is True  # type: ignore[arg-type]


def test_new_trip_requires_canonical_origin_and_destination_codes() -> None:
    with pytest.raises(ValidationError):
        TripCreate.model_validate(
            {
                "title": "广州一日游",
                "city": "广州市",
                "start_date": "2026-12-01",
                "end_date": "2026-12-01",
            }
        )

    created = TripCreate.model_validate(
        {
            "title": "广州一日游",
            "city": "广州市",
            "city_adcode": "440100",
            "origin_city": "广州市",
            "origin_city_adcode": "440100",
            "start_date": "2026-12-01",
            "end_date": "2026-12-01",
        }
    )
    assert created.city_adcode == created.origin_city_adcode == "440100"


def test_amap_district_tree_normalizes_cities_and_municipalities() -> None:
    body = {
        "districts": [
            {
                "name": "中国",
                "districts": [
                    {
                        "name": "广东省",
                        "adcode": "440000",
                        "districts": [
                            {"name": "广州市", "adcode": "440100", "level": "city"},
                            {"name": "深圳市", "adcode": "440300", "level": "city"},
                        ],
                    },
                    {
                        "name": "北京市",
                        "adcode": "110000",
                        "districts": [
                            {"name": "北京城区", "adcode": "110100", "level": "city"},
                            {"name": "东城区", "adcode": "110101", "level": "district"}
                        ],
                    },
                ],
            }
        ]
    }

    result = AmapClient._normalize_district_tree(body)
    by_adcode = {province["adcode"]: province for province in result}

    assert by_adcode["440000"]["cities"] == [
        {"name": "广州市", "adcode": "440100"},
        {"name": "深圳市", "adcode": "440300"},
    ]
    assert by_adcode["110000"]["cities"] == [
        {"name": "北京市", "adcode": "110000"}
    ]


@pytest.mark.parametrize(
    ("name", "adcode", "expected"),
    [
        ("北京城区", "110100", ("北京市", "110000")),
        ("天津城区", "120100", ("天津市", "120000")),
        ("上海城区", "310100", ("上海市", "310000")),
        ("重庆郊县", "500200", ("重庆市", "500000")),
    ],
)
def test_legacy_municipality_selections_are_canonicalized(
    name: str, adcode: str, expected: tuple[str, str]
) -> None:
    assert canonical_city_selection(name, adcode) == expected
    assert canonical_city_adcode(adcode) == expected[1]
