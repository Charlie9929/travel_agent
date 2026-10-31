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
