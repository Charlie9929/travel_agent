import os
from collections.abc import AsyncIterator
from copy import deepcopy

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import collaboration as collaboration_endpoint
from app.core.errors import AppError
from app.db.session import engine, get_db_session
from app.integrations.llm import FakeLLMClient
from app.main import app
from app.services import ai_service
from app.services.itinerary_snapshot import build_itinerary_snapshot

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_DB_INTEGRATION") != "1",
        reason="set RUN_DB_INTEGRATION=1 to run rollback-safe PostgreSQL integration tests",
    ),
]


class StubAmapClient:
    async def search_poi(self, *, keyword: str, city: str) -> dict:
        return {
            "items": [
                {
                    "poi_id": "B001",
                    "name": keyword,
                    "address": f"{city}测试地址",
                    "longitude": 104.066,
                    "latitude": 30.572,
                    "adcode": "510100",
                    "province": "四川省",
                }
            ]
        }


class StubWeatherClient:
    async def weather_for_date(self, *, city_code: str, target_date) -> dict:
        assert city_code == "成都"
        return {
            "condition_day": "多云",
            "condition_night": "晴",
            "precipitation_probability": "20",
            "queried_at": f"{target_date.isoformat()}T00:00:00+00:00",
            "stale": False,
        }


class FailingAmapClient:
    async def search_poi(self, *, keyword: str, city: str) -> dict:
        del keyword, city
        raise AppError("AMAP_TIMEOUT", "地图查询超时", status_code=502)


class FailingWeatherClient:
    async def weather_for_date(self, *, city_code: str, target_date) -> dict:
        del city_code, target_date
        raise AppError("QWEATHER_TIMEOUT", "天气查询超时", status_code=502)


async def _register(
    client: httpx.AsyncClient, username: str, nickname: str
) -> tuple[int, dict[str, str]]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "Integration123!", "nickname": nickname},
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    return data["user_info"]["id"], {"Authorization": f"Bearer {data['token']}"}


@pytest.mark.asyncio
async def test_full_backend_chain_permissions_polling_and_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    itinerary_fixture = {
        "schema_version": "1.0",
        "trip_id": "",
        "version": 1,
        "city": {"name": "成都"},
        "meta": {
            "title": "成都联调行程",
            "date_start": "2026-11-05",
            "date_end": "2026-11-05",
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
                "date": "2026-11-05",
                "day_index": 1,
                "activities": [
                    {
                        "activity_id": "act-e2e-1",
                        "type": "poi",
                        "title": "人民公园",
                        "time_slot": {"start": "09:00", "end": "11:00"},
                        "location": {"name": "人民公园", "poi_source": "llm"},
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
    monkeypatch.setattr(
        ai_service,
        "get_llm_client",
        lambda: FakeLLMClient(deepcopy(itinerary_fixture)),
    )
    monkeypatch.setattr(ai_service, "get_amap_client", lambda: StubAmapClient())
    monkeypatch.setattr(ai_service, "get_qweather_client", lambda: StubWeatherClient())

    async def fake_chat_reply(*args, **kwargs) -> str:
        del args, kwargs
        return "请优先保留室内活动，并关注当天多云天气。"

    monkeypatch.setattr(collaboration_endpoint, "generate_chat_reply", fake_chat_reply)
    app.dependency_overrides[get_db_session] = override_session
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", timeout=30
        ) as client:
            owner_id, owner_headers = await _register(client, "e2e_owner", "联调 Owner")
            editor_id, editor_headers = await _register(client, "e2e_editor", "联调 Editor")

            created = await client.post(
                "/api/v1/trips",
                headers=owner_headers,
                json={
                    "title": "端到端测试",
                    "city": "成都",
                    "start_date": "2026-11-05",
                    "end_date": "2026-11-05",
                    "total_budget": 1000,
                    "traveler_count": 2,
                },
            )
            assert created.status_code == 201, created.text
            trip = created.json()["data"]
            trip_id = trip["id"]

            invited = await client.post(
                f"/api/v1/trips/{trip_id}/members/invite",
                headers=owner_headers,
                json={"user_id": editor_id, "role": "editor"},
            )
            assert invited.status_code == 201, invited.text

            before_generation = await client.get(
                f"/api/v1/trips/{trip_id}", headers=owner_headers
            )
            version = before_generation.json()["data"]["version"]
            generated = await client.post(
                "/api/v1/ai/generate",
                headers=owner_headers,
                json={"trip_id": trip_id, "additional_requirements": "优先室内活动"},
            )
            assert generated.status_code == 200, generated.text
            generated_data = generated.json()["data"]
            assert generated_data["trip_version"] == version + 1
            assert generated_data["integration_warnings"] == []
            assert generated_data["itinerary"]["days"][0]["weather"]["source"] == "qweather"
            assert (
                generated_data["itinerary"]["days"][0]["activities"][0]["location"][
                    "poi_source"
                ]
                == "amap"
            )

            loaded = await client.get(f"/api/v1/trips/{trip_id}", headers=owner_headers)
            assert loaded.status_code == 200
            assert loaded.json()["data"]["days"][0]["activities"][0]["title"] == "人民公园"
            snapshot = await build_itinerary_snapshot(session, trip_id)
            assert snapshot["days"][0]["weather"]["summary"] == "多云"

            degraded_trip_response = await client.post(
                "/api/v1/trips",
                headers=owner_headers,
                json={
                    "title": "外部服务降级测试",
                    "city": "成都",
                    "start_date": "2026-11-05",
                    "end_date": "2026-11-05",
                    "total_budget": 1000,
                    "traveler_count": 1,
                },
            )
            degraded_trip = degraded_trip_response.json()["data"]
            monkeypatch.setattr(ai_service, "get_amap_client", lambda: FailingAmapClient())
            monkeypatch.setattr(
                ai_service, "get_qweather_client", lambda: FailingWeatherClient()
            )
            degraded_generation = await client.post(
                "/api/v1/ai/generate",
                headers=owner_headers,
                json={"trip_id": degraded_trip["id"]},
            )
            assert degraded_generation.status_code == 200, degraded_generation.text
            degraded_data = degraded_generation.json()["data"]
            warning_codes = {
                item["code"] for item in degraded_data["integration_warnings"]
            }
            assert {"AMAP_TIMEOUT", "QWEATHER_TIMEOUT"} <= warning_codes
            assert degraded_data["itinerary"]["days"][0]["weather"] is None
            assert degraded_data["itinerary"]["days"][0]["activities"]

            monkeypatch.setattr(ai_service, "get_amap_client", lambda: StubAmapClient())
            monkeypatch.setattr(ai_service, "get_qweather_client", lambda: StubWeatherClient())

            owner_update = await client.put(
                f"/api/v1/trips/{trip_id}",
                headers=owner_headers,
                json={"title": "Owner 已更新", "version": generated_data["trip_version"]},
            )
            assert owner_update.status_code == 200
            stale_update = await client.put(
                f"/api/v1/trips/{trip_id}",
                headers=editor_headers,
                json={"title": "过期更新", "version": generated_data["trip_version"]},
            )
            assert stale_update.status_code == 409

            sent = await client.post(
                f"/api/v1/trips/{trip_id}/messages",
                headers=owner_headers,
                json={"content": "@Agent 下雨时怎么办？"},
            )
            assert sent.status_code == 201
            sent_items = sent.json()["data"]
            assert [item["kind"] for item in sent_items] == ["user", "agent"]
            last_message_id = sent_items[-1]["id"]
            polled = await client.get(
                f"/api/v1/trips/{trip_id}/messages?after_id=0",
                headers=editor_headers,
            )
            assert polled.status_code == 200
            assert polled.json()["data"]["unread_count"] >= 1
            marked = await client.post(
                f"/api/v1/trips/{trip_id}/messages/read",
                headers=editor_headers,
                json={"last_read_message_id": last_message_id},
            )
            assert marked.status_code == 200
            after_read = await client.get(
                f"/api/v1/trips/{trip_id}/messages?after_id={last_message_id}",
                headers=editor_headers,
            )
            assert after_read.json()["data"]["items"] == []
            assert after_read.json()["data"]["unread_count"] == 0

            saved_requirement = await client.put(
                f"/api/v1/trips/{trip_id}/requirements/me",
                headers=owner_headers,
                json={"content": {"pace": "relaxed"}, "status": "completed"},
            )
            assert saved_requirement.status_code == 200
            shared = await client.post(
                f"/api/v1/trips/{trip_id}/requirements/me/share",
                headers=owner_headers,
                json={"summary": "节奏轻松"},
            )
            assert shared.status_code == 200
            editor_requirements = await client.get(
                f"/api/v1/trips/{trip_id}/requirements",
                headers=editor_headers,
            )
            owner_requirement = next(
                item
                for item in editor_requirements.json()["data"]
                if item["user_id"] == owner_id
            )
            assert owner_requirement["shared_summary"] == "节奏轻松"
            assert owner_requirement["content"] is None

            expense = await client.post(
                f"/api/v1/trips/{trip_id}/expenses",
                headers=owner_headers,
                json={
                    "title": "午餐",
                    "amount": 100,
                    "payer_id": owner_id,
                    "split_type": "equal",
                    "participant_ids": [owner_id, editor_id],
                },
            )
            assert expense.status_code == 201, expense.text
            settlement = await client.get(
                f"/api/v1/trips/{trip_id}/expenses/settlement",
                headers=editor_headers,
            )
            assert settlement.status_code == 200
            assert settlement.json()["data"][0]["amount"] == "50.00"

            memory = await client.post(
                "/api/v1/memories",
                headers=owner_headers,
                json={"title": "偏好", "content": "喜欢慢节奏"},
            )
            assert memory.status_code == 201
            highlight = await client.post(
                f"/api/v1/trips/{trip_id}/highlights",
                headers=editor_headers,
                json={"title": "人民公园喝茶"},
            )
            assert highlight.status_code == 201

            demoted = await client.put(
                f"/api/v1/trips/{trip_id}/members/{editor_id}",
                headers=owner_headers,
                json={"role": "viewer"},
            )
            assert demoted.status_code == 200
            viewer_write = await client.put(
                f"/api/v1/trips/{trip_id}",
                headers=editor_headers,
                json={
                    "title": "Viewer 不可编辑",
                    "version": owner_update.json()["data"]["version"] + 1,
                },
            )
            assert viewer_write.status_code == 403
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await session.close()
        await outer_transaction.rollback()
        await connection.close()
