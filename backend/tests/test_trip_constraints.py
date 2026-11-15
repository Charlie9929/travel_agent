from app.services.trip_constraints import normalize_constraints, normalize_pace


def test_pace_is_optional() -> None:
    assert normalize_constraints({"items": ["喜欢园林"]}) == {"items": ["喜欢园林"]}
    assert normalize_pace(None) is None
    assert normalize_pace("") is None


def test_pace_aliases_are_canonicalized() -> None:
    assert normalize_pace("轻松") == "relaxed"
    assert normalize_pace("想休闲一点，不要太赶") == "relaxed"
    assert normalize_pace("适中") == "normal"
    assert normalize_pace("高强度打卡") == "intense"
    assert normalize_constraints({"pace": "休闲"}) == {"pace": "relaxed"}


def test_unknown_pace_does_not_pollute_schema_enum() -> None:
    assert normalize_constraints({"pace": "看情况", "items": ["喜欢园林"]}) == {
        "items": ["喜欢园林"]
    }
