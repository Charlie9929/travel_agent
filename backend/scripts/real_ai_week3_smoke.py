import asyncio
import os
from uuid import uuid4

import httpx


def _check(response: httpx.Response, label: str) -> dict:
    if response.is_error:
        raise RuntimeError(f"{label} failed: HTTP {response.status_code} {response.text[:1500]}")
    return response.json()["data"]


async def main() -> None:
    base_url = os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:8000")
    username = f"real_ai_week3_{uuid4().hex[:8]}"
    async with httpx.AsyncClient(base_url=base_url, timeout=180) as client:
        registered = _check(
            await client.post(
                "/api/v1/auth/register",
                json={
                    "username": username,
                    "password": "real-ai-week3-password",
                    "nickname": "Real AI Week3",
                },
            ),
            "register",
        )
        headers = {"Authorization": f"Bearer {registered['token']}"}
        trip = _check(
            await client.post(
                "/api/v1/trips",
                headers=headers,
                json={
                    "title": "成都真实 AI 第三周测试",
                    "city": "成都",
                    "start_date": "2026-11-08",
                    "end_date": "2026-11-09",
                    "total_budget": 2000,
                    "traveler_count": 2,
                    "preferences": {"items": ["轻松", "室内外结合"]},
                    "constraints": {"pace": "normal", "party_type": "friends"},
                },
            ),
            "create trip",
        )
        version = trip["version"]
        for payload in (
            {
                "agent_activity_id": "act-1",
                "day_number": 1,
                "order_index": 1,
                "title": "人民公园",
                "type": "sight",
                "start_time": "09:00:00",
                "duration_min": 120,
                "location_name": "人民公园",
                "price_estimated": 0,
            },
            {
                "agent_activity_id": "act-2",
                "day_number": 2,
                "order_index": 1,
                "title": "成都博物馆",
                "type": "sight",
                "start_time": "10:00:00",
                "duration_min": 120,
                "location_name": "成都博物馆",
                "price_estimated": 0,
            },
        ):
            created = _check(
                await client.post(
                    f"/api/v1/trips/{trip['id']}/activities",
                    headers=headers,
                    json={**payload, "trip_version": version},
                ),
                "create activity",
            )
            version = created["trip_version"]

        before = _check(
            await client.get(f"/api/v1/trips/{trip['id']}", headers=headers), "get trip"
        )
        replan = _check(
            await client.post(
                "/api/v1/ai/replan",
                headers=headers,
                json={
                    "trip_id": trip["id"],
                    "day_number": 1,
                    "adjustment_requirements": "只把人民公园开始时间从09:00调整为10:00，其余不变",
                    "trip_version": version,
                    "after_time": "08:00",
                    "trigger": {
                        "reason_type": "user_request",
                        "description": "用户希望晚一小时出发",
                        "target_activity_ids": ["act-1"],
                    },
                },
            ),
            "real replan",
        )
        replan_applied = _check(
            await client.post(
                f"/api/v1/trips/{trip['id']}/ai-runs/{replan['ai_run_id']}/apply",
                headers=headers,
                json={"trip_version": version},
            ),
            "apply replan",
        )
        version = replan_applied["trip_version"]

        revise = _check(
            await client.post(
                "/api/v1/ai/revise",
                headers=headers,
                json={
                    "trip_id": trip["id"],
                    "changed_constraints": {"updated": {"pace": "relaxed"}},
                    "user_instruction": "节奏改为轻松；当前活动已经很少，不需要删除或新增活动",
                    "trip_version": version,
                },
            ),
            "real revise",
        )
        revise_applied = _check(
            await client.post(
                f"/api/v1/trips/{trip['id']}/ai-runs/{revise['ai_run_id']}/apply",
                headers=headers,
                json={"trip_version": version},
            ),
            "apply revise",
        )
        version = revise_applied["trip_version"]

        explanation = _check(
            await client.post(
                "/api/v1/ai/explain-diff",
                headers=headers,
                json={
                    "trip_id": trip["id"],
                    "mode": "explain",
                    "old_itinerary": replan["candidate_itinerary"],
                    "new_itinerary": revise["candidate_itinerary"],
                },
            ),
            "real explain diff",
        )

        guide = _check(
            await client.post(
                "/api/v1/ai/import-guide",
                headers=headers,
                json={
                    "trip_id": trip["id"],
                    "text": "成都第二天下午去了宽窄巷子，免费开放，人很多，建议四点以后再去。",
                },
            ),
            "real import guide",
        )
        imported_count = 0
        if guide["candidates"]:
            selected = guide["candidates"][0]["candidate_id"]
            imported = _check(
                await client.post(
                    f"/api/v1/trips/{trip['id']}/ai-runs/{guide['ai_run_id']}/apply",
                    headers=headers,
                    json={
                        "trip_version": version,
                        "apply_mode": "append_selected",
                        "selected_candidate_ids": [selected],
                    },
                ),
                "apply guide candidate",
            )
            imported_count = len(imported["activities"])

        print(
            {
                "trip_id": trip["id"],
                "original_version": before["version"],
                "replan_retry_count": replan["retry_count"],
                "revise_retry_count": revise["retry_count"],
                "explain_retry_count": explanation["retry_count"],
                "guide_retry_count": guide["retry_count"],
                "guide_candidates": len(guide["candidates"]),
                "guide_activities_applied": imported_count,
            }
        )


if __name__ == "__main__":
    asyncio.run(main())
