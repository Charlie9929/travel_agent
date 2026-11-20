from decimal import Decimal

import pytest

from app.api.v1.endpoints.collaboration import _agent_adjustment_requested
from app.api.v1.endpoints.expenses import _equal_splits, _ratio_splits
from app.core.errors import AppError
from app.schemas.collaboration import ExpenseSplitInput
from app.services.collaboration import candidate_presentation, present_revision_diff


def test_agent_question_is_not_misclassified_as_itinerary_adjustment() -> None:
    assert not _agent_adjustment_requested("@Agent 西湖游船在第几天？")
    assert _agent_adjustment_requested("@Agent 把西湖游船安排到第二天")


def test_equal_split_keeps_cent_total() -> None:
    splits = _equal_splits(Decimal("100.00"), [1, 2, 3])
    assert sum((item[2] for item in splits), Decimal("0")) == Decimal("100.00")
    assert sum((item[1] for item in splits), Decimal("0")) == Decimal("1.0000")


def test_ratio_split_requires_complete_total() -> None:
    with pytest.raises(AppError) as exc_info:
        _ratio_splits(
            Decimal("100.00"),
            [
                ExpenseSplitInput(user_id=1, ratio=Decimal("0.4")),
                ExpenseSplitInput(user_id=2, ratio=Decimal("0.4")),
            ],
        )
    assert exc_info.value.code == "INVALID_EXPENSE_SPLIT"


def test_revision_presentation_exposes_stable_field_changes() -> None:
    result = present_revision_diff(
        {
            "before": {"title": "旧标题", "city": "杭州"},
            "after": {"title": "新标题", "city": "杭州"},
        }
    )
    assert result["summary"] == "修改了 1 个字段"
    assert result["changes"] == [{"field": "title", "before": "旧标题", "after": "新标题"}]


def test_revision_presentation_prefers_natural_language_summary() -> None:
    result = present_revision_diff(
        {
            "summary": "将返程航班顺延至最后一天",
            "before": {"day_number": 2},
            "after": {"day_number": 3},
        },
        resource_type="activity",
        action="update",
    )
    assert result["summary"] == "将返程航班顺延至最后一天"


def test_revision_presentation_names_activity_without_exposing_raw_diff() -> None:
    result = present_revision_diff(
        {"before": None, "after": {"title": "玉龙雪山"}},
        resource_type="activity",
        action="create",
    )
    assert result["summary"] == "新增活动“玉龙雪山”"


def test_candidate_presentation_separates_changed_and_kept_items() -> None:
    result = candidate_presentation(
        {
            "diff": {
                "ops": [
                    {
                        "op": "replace",
                        "activity_id": "act-1",
                        "day_index": 1,
                        "fields": ["time_slot"],
                    }
                ]
            },
            "proposed_itinerary": {
                "cost_summary": {"total_estimate": {"amount": 100}},
                "days": [
                    {
                        "day_index": 1,
                        "activities": [
                            {"activity_id": "act-1", "title": "已修改"},
                            {"activity_id": "act-2", "title": "未修改"},
                        ],
                    }
                ],
            },
        }
    )
    assert result["changed_items"][0]["activity_id"] == "act-1"
    assert result["kept_items"] == [{"activity_id": "act-2", "day_index": 1, "title": "未修改"}]
    assert result["cost_info"]["total_estimate"]["amount"] == 100
