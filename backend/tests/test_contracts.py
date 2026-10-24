import pytest

from app.agent_contracts.loader import validate_itinerary
from app.integrations.llm import FakeLLMClient


@pytest.mark.asyncio
async def test_fake_llm_returns_valid_contract() -> None:
    client = FakeLLMClient()
    result = await client.generate_json(
        system_prompt="json",
        user_prompt="test",
        schema={},
        model="test",
        prompt_version="v0.1",
        request_id="request-1",
        timeout_seconds=1,
    )
    validate_itinerary(result.parsed_data)
    assert result.request_id == "request-1"
