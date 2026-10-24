import asyncio
import os
from uuid import uuid4

import httpx


async def main() -> None:
    base_url = os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:8000")
    username = f"smoke_{uuid4().hex[:10]}"
    async with httpx.AsyncClient(base_url=base_url, timeout=20) as client:
        health = await client.get("/health")
        health.raise_for_status()

        registered = await client.post(
            "/api/v1/auth/register",
            json={
                "username": username,
                "password": "smoke-test-password",
                "nickname": "Smoke Test",
            },
        )
        registered.raise_for_status()
        token = registered.json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}

        created = await client.post(
            "/api/v1/trips",
            headers=headers,
            json={
                "title": "成都测试行程",
                "city": "成都",
                "start_date": "2026-01-01",
                "end_date": "2026-01-01",
                "total_budget": 1000,
                "traveler_count": 2,
            },
        )
        created.raise_for_status()
        trip = created.json()["data"]

        updated = await client.put(
            f"/api/v1/trips/{trip['id']}",
            headers=headers,
            json={"title": "成都测试行程 v2", "version": trip["version"]},
        )
        updated.raise_for_status()
        new_version = updated.json()["data"]["version"]

        stale = await client.put(
            f"/api/v1/trips/{trip['id']}",
            headers=headers,
            json={"title": "这次提交应冲突", "version": trip["version"]},
        )
        assert stale.status_code == 409, stale.text

        activity = await client.post(
            f"/api/v1/trips/{trip['id']}/activities",
            headers=headers,
            json={
                "day_number": 1,
                "order_index": 1,
                "title": "宽窄巷子",
                "type": "sight",
                "trip_version": new_version,
            },
        )
        activity.raise_for_status()
        activity_version = activity.json()["data"]["trip_version"]

        generated = await client.post(
            "/api/v1/ai/generate",
            headers=headers,
            json={"trip_id": trip["id"], "additional_requirements": "Mock smoke test"},
        )
        generated.raise_for_status()
        result = generated.json()["data"]
        assert result["status"] == "applied"
        assert result["trip_version"] == activity_version + 1

        print(
            {
                "health": health.json()["data"],
                "trip_id": trip["id"],
                "optimistic_lock": "409 verified",
                "fake_ai_generate": "validated and applied directly",
            }
        )


if __name__ == "__main__":
    asyncio.run(main())
