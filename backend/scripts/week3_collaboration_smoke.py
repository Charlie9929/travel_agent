import asyncio
import os
from uuid import uuid4

import httpx


async def _register(client: httpx.AsyncClient, label: str) -> tuple[int, dict[str, str]]:
    username = f"week3_{label.lower().replace(' ', '_')}_{uuid4().hex[:8]}"
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "week3-test-password", "nickname": label},
    )
    response.raise_for_status()
    data = response.json()["data"]
    return data["user_info"]["id"], {"Authorization": f"Bearer {data['token']}"}


async def main() -> None:
    base_url = os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:8000")
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        owner_id, owner_headers = await _register(client, "Week3 Owner")
        editor_id, editor_headers = await _register(client, "Week3 Editor")

        created = await client.post(
            "/api/v1/trips",
            headers=owner_headers,
            json={
                "title": "第三周多人冲突测试",
                "city": "成都",
                "start_date": "2026-11-01",
                "end_date": "2026-11-02",
                "total_budget": 2000,
                "traveler_count": 2,
            },
        )
        created.raise_for_status()
        trip_id = created.json()["data"]["id"]

        invited = await client.post(
            f"/api/v1/trips/{trip_id}/members/invite",
            headers=owner_headers,
            json={"user_id": editor_id, "role": "editor"},
        )
        invited.raise_for_status()

        trip = await client.get(f"/api/v1/trips/{trip_id}", headers=owner_headers)
        trip.raise_for_status()
        version = trip.json()["data"]["version"]

        day1 = await client.post(
            f"/api/v1/trips/{trip_id}/activities",
            headers=owner_headers,
            json={
                "day_number": 1,
                "order_index": 1,
                "title": "人民公园",
                "type": "sight",
                "start_time": "09:00:00",
                "duration_min": 120,
                "trip_version": version,
            },
        )
        day1.raise_for_status()
        day1_data = day1.json()["data"]
        day1_id = day1_data["activity"]["id"]
        version = day1_data["trip_version"]

        day2 = await client.post(
            f"/api/v1/trips/{trip_id}/activities",
            headers=owner_headers,
            json={
                "day_number": 2,
                "order_index": 1,
                "title": "成都博物馆",
                "type": "sight",
                "start_time": "10:00:00",
                "duration_min": 120,
                "trip_version": version,
            },
        )
        day2.raise_for_status()
        day2_data = day2.json()["data"]
        day2_id = day2_data["activity"]["id"]
        version = day2_data["trip_version"]

        replan_different_day = await client.post(
            "/api/v1/ai/replan",
            headers=owner_headers,
            json={
                "trip_id": trip_id,
                "day_number": 1,
                "adjustment_requirements": "把第一天改为室内活动",
                "trip_version": version,
                "after_time": "08:00",
            },
        )
        replan_different_day.raise_for_status()
        run_id = replan_different_day.json()["data"]["ai_run_id"]
        candidate_version = version

        teammate_day2_edit = await client.put(
            f"/api/v1/trips/{trip_id}/activities/{day2_id}",
            headers=editor_headers,
            json={"title": "队友更新的成都博物馆", "trip_version": version},
        )
        teammate_day2_edit.raise_for_status()
        version = teammate_day2_edit.json()["data"]["trip_version"]

        rebased_apply = await client.post(
            f"/api/v1/trips/{trip_id}/ai-runs/{run_id}/apply",
            headers=owner_headers,
            json={"trip_version": candidate_version},
        )
        rebased_apply.raise_for_status()
        version = rebased_apply.json()["data"]["trip_version"]

        replan_same_day = await client.post(
            "/api/v1/ai/replan",
            headers=owner_headers,
            json={
                "trip_id": trip_id,
                "day_number": 1,
                "adjustment_requirements": "再次调整第一天",
                "trip_version": version,
                "after_time": "08:00",
            },
        )
        replan_same_day.raise_for_status()
        conflict_run_id = replan_same_day.json()["data"]["ai_run_id"]
        conflict_base_version = version

        teammate_day1_edit = await client.put(
            f"/api/v1/trips/{trip_id}/activities/{day1_id}",
            headers=editor_headers,
            json={"title": "队友刚改过的人民公园", "trip_version": version},
        )
        teammate_day1_edit.raise_for_status()
        version = teammate_day1_edit.json()["data"]["trip_version"]

        conflict_apply = await client.post(
            f"/api/v1/trips/{trip_id}/ai-runs/{conflict_run_id}/apply",
            headers=owner_headers,
            json={"trip_version": conflict_base_version},
        )
        assert conflict_apply.status_code == 409, conflict_apply.text

        revisions = await client.get(
            f"/api/v1/trips/{trip_id}/revisions", headers=owner_headers
        )
        revisions.raise_for_status()
        revision_items = revisions.json()["data"]
        assert revision_items
        revision_detail = await client.get(
            f"/api/v1/trips/{trip_id}/revisions/{revision_items[0]['id']}",
            headers=owner_headers,
        )
        revision_detail.raise_for_status()

        role_update = await client.put(
            f"/api/v1/trips/{trip_id}/members/{editor_id}",
            headers=owner_headers,
            json={"role": "viewer"},
        )
        role_update.raise_for_status()
        viewer_edit = await client.put(
            f"/api/v1/trips/{trip_id}/activities/{day2_id}",
            headers=editor_headers,
            json={"title": "viewer 不应成功", "trip_version": version + 1},
        )
        assert viewer_edit.status_code == 403, viewer_edit.text

        print(
            {
                "trip_id": trip_id,
                "owner_id": owner_id,
                "different_day_rebase": "verified",
                "same_day_conflict": "409 verified",
                "revision_queries": "verified",
                "viewer_write": "403 verified",
            }
        )


if __name__ == "__main__":
    asyncio.run(main())
