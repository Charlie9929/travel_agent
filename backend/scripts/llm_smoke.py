import asyncio
import json
from uuid import uuid4

from app.agent_contracts.loader import load_itinerary_schema
from app.core.config import get_settings
from app.integrations.llm import DeepSeekClient


async def main() -> None:
    settings = get_settings()
    client = DeepSeekClient(
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
    )
    result = await client.generate_json(
        system_prompt='请只输出 JSON。输出形如 {"ok": true} 的对象。',
        user_prompt="返回一次连接测试结果。",
        schema=load_itinerary_schema(),
        model=settings.deepseek_model,
        prompt_version="smoke-v1",
        request_id=f"smoke-{uuid4().hex}",
        timeout_seconds=settings.deepseek_timeout_seconds,
    )
    print(json.dumps(result.parsed_data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
