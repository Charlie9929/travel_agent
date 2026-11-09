import os
from collections.abc import AsyncIterator
from datetime import date
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import engine, get_db_session
from app.main import app

pytestmark = [
    pytest.mark.external,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_EXTERNAL") != "1",
        reason="set RUN_LIVE_EXTERNAL=1 to spend real provider quota on a rollback-safe test",
    ),
]


@pytest.mark.asyncio
async def test_live_deepseek_amap_qweather_chain_persists_and_reloads() -> None:
    settings = get_settings()
    assert settings.llm_use_fake is False
    assert settings.deepseek_api_key
    assert settings.amap_api_key
    assert settings.qweather_api_host
    assert settings.qweather_api_key or settings.qweather_jwt_token

    connection = await engine.connect()
    outer_transaction = await connection.begin()
    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            timeout=settings.deepseek_timeout_seconds + 60,
        ) as client:
            username = f"live_e2e_{uuid4().hex[:10]}"
            registered = await client.post(
                "/api/v1/auth/register",
                json={
                    "username": username,
                    "password": "LiveIntegration123!",
                    "nickname": "真实链路测试",
                },
            )
            assert registered.status_code == 201, registered.text
            token = registered.json()["data"]["token"]
            headers = {"Authorization": f"Bearer {token}"}
            today = date.today().isoformat()
            created = await client.post(
                "/api/v1/trips",
                headers=headers,
                json={
                    "title": "成都真实 API 当日行程",
                    "city": "成都",
                    "start_date": today,
                    "end_date": today,
                    "total_budget": 800,
                    "traveler_count": 1,
                    "preferences": {"items": ["室内优先", "少走路"]},
                },
            )
            assert created.status_code == 201, created.text
            trip = created.json()["data"]

            generated = await client.post(
                "/api/v1/ai/generate",
                headers=headers,
                json={
                    "trip_id": trip["id"],
                    "additional_requirements": "生成精简的一日行程，安排 1 至 2 个真实地点。",
                },
            )
            assert generated.status_code == 200, generated.text
            result = generated.json()["data"]
            assert result["status"] == "applied"
            assert not str(result["model"]).startswith("fake:")
            activities = result["itinerary"]["days"][0]["activities"]
            assert activities
            assert any(
                (item.get("location") or {}).get("poi_source") == "amap"
                for item in activities
            )
            assert result["itinerary"]["days"][0]["weather"] is not None

            loaded = await client.get(f"/api/v1/trips/{trip['id']}", headers=headers)
            assert loaded.status_code == 200
            assert loaded.json()["data"]["version"] == result["trip_version"]
            assert loaded.json()["data"]["days"][0]["activities"]
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await session.close()
        await outer_transaction.rollback()
        await connection.close()
