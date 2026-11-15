import json

import pytest

from app.integrations.llm import FakeLLMClient


@pytest.mark.asyncio
async def test_fake_llm_returns_replan_candidate_for_replan_prompt() -> None:
    itinerary = {"days": []}
    client = FakeLLMClient()
    result = await client.generate_json(
        system_prompt="你是旅行行程的重排模块",
        user_prompt=json.dumps({"itinerary_json": itinerary}),
        schema={},
        model="test",
        prompt_version="v0.2",
        request_id="replan-1",
        timeout_seconds=1,
    )

    assert result.parsed_data["diff"] == {"ops": []}
    assert result.parsed_data["proposed_itinerary"] == itinerary


@pytest.mark.asyncio
async def test_fake_llm_returns_only_target_day_for_scoped_replan() -> None:
    target_day = {"day_index": 4, "date": "2027-05-04", "activities": []}
    client = FakeLLMClient()
    result = await client.generate_json(
        system_prompt="你是旅行行程的重排模块",
        user_prompt=json.dumps({"target_day": target_day, "trip_context": {"city": "上海"}}),
        schema={},
        model="test",
        prompt_version="v0.2",
        request_id="replan-scoped-1",
        timeout_seconds=1,
    )

    assert result.parsed_data["proposed_day"] == target_day
    assert "proposed_itinerary" not in result.parsed_data


@pytest.mark.asyncio
async def test_fake_llm_returns_structured_diff_explanation() -> None:
    client = FakeLLMClient()
    result = await client.generate_json(
        system_prompt="你是旅行行程的差异解说器",
        user_prompt=json.dumps({"mode": "conflict"}),
        schema={},
        model="test",
        prompt_version="v0.2",
        request_id="explain-1",
        timeout_seconds=1,
    )

    assert result.parsed_data["both_changed"] == []
    assert result.parsed_data["my_changes"] == []


@pytest.mark.asyncio
async def test_fake_preference_understanding_does_not_ask_for_optional_pace() -> None:
    client = FakeLLMClient()
    result = await client.generate_json(
        system_prompt="你是多人旅行助手的偏好理解模块",
        user_prompt=json.dumps(
            {
                "trip": {
                    "city": "苏州",
                    "start_date": "2027-05-01",
                    "end_date": "2027-05-05",
                    "traveler_count": 2,
                },
                "latest_user_message": "喜欢园林和苏帮菜",
            }
        ),
        schema={},
        model="test",
        prompt_version="preference-clarify-v0.1",
        request_id="clarify-optional-pace",
        timeout_seconds=1,
    )

    assert result.parsed_data["ready"] is True
    assert result.parsed_data["questions"] == []
    assert "pace" not in result.parsed_data["structured_constraints"]
