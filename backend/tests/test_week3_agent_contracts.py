from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.agent_contracts.business_validation import (
    validate_replan_candidate,
    validate_revision_candidate,
)
from app.agent_contracts.loader import load_shared_prompt, validate_itinerary
from app.core.errors import AppError
from app.services.ai_service import (
    _apply_changed_constraints_to_trip,
    _collect_revision_days,
    _complete_replan_candidate,
    _rebase_replan_candidate,
)


def _itinerary() -> dict:
    return {
        "schema_version": "1.0",
        "trip_id": "00000000-0000-0000-0000-000000000001",
        "version": 2,
        "city": {"name": "成都"},
        "meta": {
            "title": "测试行程",
            "date_start": "2026-10-31",
            "date_end": "2026-10-31",
            "traveler_count": 2,
            "budget_total": {
                "amount": 1000,
                "currency": "CNY",
                "price_type": "estimate",
                "source": "manual",
            },
        },
        "days": [
            {
                "date": "2026-10-31",
                "day_index": 1,
                "activities": [
                    {
                        "activity_id": "act-1",
                        "type": "poi",
                        "title": "人民公园",
                        "time_slot": {"start": "09:00", "end": "11:00"},
                        "status": "planned",
                    }
                ],
                "transfers": [],
            }
        ],
        "cost_summary": {
            "total_estimate": {
                "amount": 0,
                "currency": "CNY",
                "price_type": "estimate",
                "source": "manual",
            }
        },
        "members": [],
        "permissions": {"collab_mode": "A2_poll"},
        "revisions": [],
        "candidates": [],
    }


def test_shared_replan_prompt_is_loaded_from_tech_one_document() -> None:
    generation_prompt = load_shared_prompt("itinerary-generation", "v0.2")
    prompt = load_shared_prompt("replan-day", "v0.2")
    assert "国内城市自由行的行程规划器" in generation_prompt
    assert "重排模块" in prompt
    assert "activity_id" in prompt


def test_replan_candidate_passes_schema_and_business_validation() -> None:
    original = _itinerary()
    proposed = deepcopy(original)
    proposed["days"][0]["activities"][0]["time_slot"] = {
        "start": "10:00",
        "end": "12:00",
    }
    candidate = {
        "summary": "把人民公园改到十点",
        "diff": {
            "ops": [
                {
                    "op": "replace",
                    "activity_id": "act-1",
                    "day_index": 1,
                    "fields": ["time_slot"],
                    "reason": "用户要求",
                }
            ]
        },
        "proposed_itinerary": proposed,
    }

    completed = _complete_replan_candidate(candidate, original)
    validate_itinerary(completed["proposed_itinerary"])
    validate_replan_candidate(
        original,
        completed,
        day_number=1,
        after_time="09:00",
    )


def test_replan_candidate_rejects_cross_day_diff() -> None:
    original = _itinerary()
    candidate = {
        "summary": "错误越界",
        "diff": {
            "ops": [
                {
                    "op": "replace",
                    "activity_id": "act-1",
                    "day_index": 2,
                    "fields": ["time_slot"],
                }
            ]
        },
        "proposed_itinerary": deepcopy(original),
    }

    with pytest.raises(AppError) as exc_info:
        validate_replan_candidate(original, candidate, day_number=1, after_time="09:00")
    assert exc_info.value.code == "AGENT_OUTPUT_INVALID"
    assert exc_info.value.detail[0]["code"] == "OP_OUTSIDE_SCOPE_DAY"


def test_revision_candidate_preserves_activity_ids() -> None:
    original = _itinerary()
    candidate = {
        "summary": "不需要修改",
        "diff": {"ops": []},
        "proposed_itinerary": deepcopy(original),
    }
    validate_revision_candidate(original, candidate)


def test_revision_days_allow_rebase_only_for_different_day() -> None:
    revisions = [
        SimpleNamespace(resource_type="member", diff_content={}),
        SimpleNamespace(
            resource_type="activity",
            diff_content={"before": {"day_number": 2}, "after": {"day_number": 2}},
        ),
    ]
    assert _collect_revision_days(revisions) == {2}  # type: ignore[arg-type]

    unknown = [SimpleNamespace(resource_type="activity", diff_content={"source": "legacy"})]
    assert _collect_revision_days(unknown) is None  # type: ignore[arg-type]


def test_replan_candidate_rebases_target_day_onto_latest_snapshot() -> None:
    current = _itinerary()
    current["days"].append(
        {
            "date": "2026-11-01",
            "day_index": 2,
            "activities": [],
            "transfers": [],
        }
    )
    proposed = deepcopy(current)
    proposed["days"][0]["activities"][0]["title"] = "成都博物馆"
    candidate = {
        "summary": "改为室内活动",
        "diff": {"ops": []},
        "proposed_itinerary": proposed,
    }
    latest = deepcopy(current)
    latest["days"][1]["theme"] = "队友刚更新的第二天"

    rebased = _rebase_replan_candidate(candidate, latest, 1)

    assert rebased["proposed_itinerary"]["days"][0]["activities"][0]["title"] == "成都博物馆"
    assert rebased["proposed_itinerary"]["days"][1]["theme"] == "队友刚更新的第二天"


def test_revision_updates_stable_trip_business_fields() -> None:
    trip = SimpleNamespace(
        total_budget=2000,
        traveler_count=2,
        preferences={},
        constraints={"pace": "normal"},
    )
    _apply_changed_constraints_to_trip(
        trip,  # type: ignore[arg-type]
        {
            "updated": {
                "budget_total": {"amount": 1500},
                "traveler_count": 3,
                "preferences": ["美食"],
                "pace": "relaxed",
            }
        },
    )
    assert trip.total_budget == 1500
    assert trip.traveler_count == 3
    assert trip.preferences == {"items": ["美食"]}
    assert trip.constraints["pace"] == "relaxed"
