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

        replan = await client.post(
            "/api/v1/ai/replan",
            headers=headers,
            json={
                "trip_id": trip["id"],
                "day_number": 1,
                "adjustment_requirements": "下午下雨，改成室内活动",
                "trip_version": result["trip_version"],
                "after_time": "12:00",
            },
        )
        replan.raise_for_status()
        replan_result = replan.json()["data"]
        assert replan_result["status"] == "succeeded"
        assert replan_result["base_version"] == result["trip_version"]

        applied = await client.post(
            f"/api/v1/trips/{trip['id']}/ai-runs/{replan_result['ai_run_id']}/apply",
            headers=headers,
            json={"trip_version": result["trip_version"]},
        )
        applied.raise_for_status()
        applied_result = applied.json()["data"]
        assert applied_result["status"] == "applied"
        assert applied_result["trip_version"] == result["trip_version"] + 1

        duplicate_apply = await client.post(
            f"/api/v1/trips/{trip['id']}/ai-runs/{replan_result['ai_run_id']}/apply",
            headers=headers,
            json={"trip_version": result["trip_version"]},
        )
        assert duplicate_apply.status_code == 409, duplicate_apply.text

        revised = await client.post(
            "/api/v1/ai/revise",
            headers=headers,
            json={
                "trip_id": trip["id"],
                "changed_constraints": {"updated": {"pace": "relaxed"}},
                "user_instruction": "节奏放松一点",
                "trip_version": applied_result["trip_version"],
            },
        )
        revised.raise_for_status()
        revised_result = revised.json()["data"]
        assert revised_result["status"] == "succeeded"

        revision_applied = await client.post(
            f"/api/v1/trips/{trip['id']}/ai-runs/{revised_result['ai_run_id']}/apply",
            headers=headers,
            json={"trip_version": applied_result["trip_version"]},
        )
        revision_applied.raise_for_status()

        explained = await client.post(
            "/api/v1/ai/explain-diff",
            headers=headers,
            json={
                "trip_id": trip["id"],
                "mode": "explain",
                "old_itinerary": applied_result["itinerary"],
                "new_itinerary": revision_applied.json()["data"]["itinerary"],
            },
        )
        explained.raise_for_status()
        assert explained.json()["data"]["explanation"]["by_day"] == []

        imported = await client.post(
            "/api/v1/ai/import-guide",
            headers=headers,
            json={"trip_id": trip["id"], "text": "上午去了宽窄巷子，免费。"},
        )
        imported.raise_for_status()
        imported_result = imported.json()["data"]
        assert imported_result["candidates"][0]["candidate_id"] == "cand-1"

        guide_applied = await client.post(
            f"/api/v1/trips/{trip['id']}/ai-runs/{imported_result['ai_run_id']}/apply",
            headers=headers,
            json={
                "trip_version": revision_applied.json()["data"]["trip_version"],
                "apply_mode": "append_selected",
                "selected_candidate_ids": ["cand-1"],
            },
        )
        guide_applied.raise_for_status()
        assert guide_applied.json()["data"]["activities"][0]["title"] == "宽窄巷子"

        validated = await client.post(
            f"/api/v1/trips/{trip['id']}/validate",
            headers=headers,
            json={"candidate_activities": []},
        )
        validated.raise_for_status()
        assert "valid" in validated.json()["data"]

        print(
            {
                "health": health.json()["data"],
                "trip_id": trip["id"],
                "optimistic_lock": "409 verified",
                "fake_ai_generate": "validated and applied directly",
                "fake_ai_replan": "candidate validated then applied once",
                "fake_ai_revise": "candidate validated then applied",
                "fake_ai_explain_diff": "structured explanation validated",
                "fake_ai_import_guide": "candidate selected and applied",
                "trip_business_validation": "verified",
            }
        )


if __name__ == "__main__":
    asyncio.run(main())
