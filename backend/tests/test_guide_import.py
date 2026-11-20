import pytest

from app.core.errors import AppError
from app.services.guide_import_service import (
    _guide_candidate_errors,
    _is_verified_candidate,
    _normalize_placements,
)


def test_guide_candidates_require_traceable_unique_entries() -> None:
    valid = {
        "candidates": [
            {
                "candidate_id": "cand-1",
                "title": "宽窄巷子",
                "excerpt": "上午去了宽窄巷子，免费。",
            }
        ],
        "warnings": [],
    }
    assert _guide_candidate_errors(valid) == []

    duplicate = {
        "candidates": [valid["candidates"][0], valid["candidates"][0]],
        "warnings": [],
    }
    codes = [item.get("field") for item in _guide_candidate_errors(duplicate)]
    assert "candidate_id" in codes
    assert "title" in codes


def test_guide_placements_are_normalized_and_must_not_collide() -> None:
    assert _normalize_placements(
        [
            {"candidate_id": "cand-2", "day_number": 2, "order_index": 3},
            {"candidate_id": "cand-1", "day_number": 1, "order_index": 2},
        ]
    ) == [
        {"candidate_id": "cand-1", "day_number": 1, "order_index": 2},
        {"candidate_id": "cand-2", "day_number": 2, "order_index": 3},
    ]

    with pytest.raises(AppError, match="同一候选或同一插入位置不能重复"):
        _normalize_placements(
            [
                {"candidate_id": "cand-1", "day_number": 1, "order_index": 2},
                {"candidate_id": "cand-2", "day_number": 1, "order_index": 2},
            ]
        )


def test_guide_candidate_requires_complete_amap_identity() -> None:
    assert _is_verified_candidate(
        {
            "location": {
                "poi_source": "amap",
                "poi_id": "B001",
                "lng": 121.4,
                "lat": 31.2,
            }
        }
    )
    assert not _is_verified_candidate(
        {"location": {"poi_source": "amap", "poi_id": "B001", "lng": None, "lat": 31.2}}
    )
