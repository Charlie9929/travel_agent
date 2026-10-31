from app.services.guide_import_service import _guide_candidate_errors


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
