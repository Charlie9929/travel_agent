from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_contracts.loader import load_shared_prompt
from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.models import AiRunLog, DayActivity, Trip, TripRevision
from app.integrations.llm import LLMResult
from app.services.ai_service import get_amap_client, get_llm_client
from app.services.poi_enrichment import _pick_poi, normalize_poi_search_city, poi_unavailable_reason
from app.services.trip_validation import _next_open_start, _opening_ranges
from app.services.versioning import bump_trip_version

MAX_REPAIR_RETRIES = 2
GUIDE_REPAIR_INSTRUCTION = """

# JSON 修复模式
上一次攻略抽取结果未通过结构校验。请根据 validation_errors 修复 invalid_output。
只输出包含 candidates 和 warnings 的完整 JSON，不要 Markdown 或额外说明。
每个候选必须保留原文 excerpt；不要编造原文没有的信息。
""".strip()
DB_TYPE_BY_AGENT_TYPE = {
    "poi": "sight",
    "meal": "food",
    "hotel": "hotel",
    "transport": "transport",
    "free_time": "other",
}


async def generate_guide_candidates(
    *, session: AsyncSession, trip_id: int, user_id: int, text: str
) -> tuple[AiRunLog, LLMResult]:
    settings = get_settings()
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")
    source_text = text[:8000]
    prompt_version = "v0.1"
    input_snapshot = {
        "base_version": trip.version,
        "city": trip.city,
        "text": source_text,
        "text_truncated": len(text) > len(source_text),
    }
    run = AiRunLog(
        trip_id=trip_id,
        requested_by=user_id,
        run_type="import_guide",
        prompt_version=prompt_version,
        input_snapshot=input_snapshot,
        status="running",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    run_id = int(run.id)
    system_prompt = load_shared_prompt("import-guide", prompt_version).replace(
        "{{city}}", trip.city
    )
    user_prompt = json.dumps(
        {"city": trip.city, "text": source_text}, ensure_ascii=False, default=str
    )
    request_id = f"ai-{run_id}-{uuid4().hex[:12]}"
    retry_count = 0
    failed_candidate: dict[str, Any] | None = None
    client = get_llm_client()
    try:
        result = await client.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema={},
            model=settings.deepseek_model,
            prompt_version=prompt_version,
            request_id=request_id,
            timeout_seconds=settings.deepseek_timeout_seconds,
            temperature=0.5,
        )
        while True:
            failed_candidate = result.parsed_data
            errors = _guide_candidate_errors(result.parsed_data)
            if not errors:
                break
            if retry_count >= MAX_REPAIR_RETRIES:
                raise AppError(
                    "AGENT_OUTPUT_INVALID",
                    "攻略候选不符合契约",
                    status_code=502,
                    detail=errors,
                )
            retry_count += 1
            result = await client.generate_json(
                system_prompt=f"{system_prompt}\n\n{GUIDE_REPAIR_INSTRUCTION}",
                user_prompt=json.dumps(
                    {
                        "original_request": input_snapshot,
                        "validation_errors": errors,
                        "invalid_output": failed_candidate,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                schema={},
                model=settings.deepseek_model,
                prompt_version=prompt_version,
                request_id=f"{request_id}-repair-{retry_count}",
                timeout_seconds=settings.deepseek_timeout_seconds,
                temperature=0.3,
            )
        run.candidate_output = result.parsed_data
        run.status = "succeeded"
        run.retry_count = retry_count
        await session.commit()
        return run, result
    except AppError as exc:
        await session.rollback()
        failed_run = await session.get(AiRunLog, run_id)
        if failed_run is not None:
            failed_run.status = "failed"
            failed_run.error_code = exc.code
            failed_run.retry_count = retry_count
            failed_run.candidate_output = {
                "invalid_output": failed_candidate,
                "validation_errors": exc.detail,
            }
            await session.commit()
        raise


async def apply_guide_candidates(
    *,
    session: AsyncSession,
    run: AiRunLog,
    user_id: int,
    trip_version: int,
    placements: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    if run.run_type != "import_guide" or run.status != "succeeded":
        raise ConflictError(
            "该 AI 运行没有可应用的攻略候选",
            {"ai_run_id": run.id, "status": run.status, "run_type": run.run_type},
        )
    base_version = int(run.input_snapshot["base_version"])
    if trip_version != base_version:
        raise ConflictError(
            "候选方案基于旧版本生成，请刷新后重新抽取",
            {"candidate_version": base_version, "submitted_version": trip_version},
        )
    output = run.candidate_output or {}
    candidates = output.get("candidates", [])
    by_id = {item.get("candidate_id"): item for item in candidates}
    normalized_placements = _normalize_placements(placements)
    selected_ids = [item["candidate_id"] for item in normalized_placements]
    if not normalized_placements:
        raise AppError("NO_CANDIDATES_SELECTED", "请至少选择一个候选条目", status_code=422)
    missing = [candidate_id for candidate_id in selected_ids if candidate_id not in by_id]
    if missing:
        raise AppError(
            "CANDIDATE_NOT_FOUND",
            "部分候选条目不存在",
            status_code=422,
            detail={"candidate_ids": missing},
        )
    if normalized_placements != output.get("verified_placements"):
        raise ConflictError("候选的位置已经改变，请重新进行高德校验后再应用")
    unverified = [
        item["title"]
        for item in (by_id[candidate_id] for candidate_id in selected_ids)
        if not _is_verified_candidate(item)
    ]
    if unverified:
        raise AppError(
            "GUIDE_POI_UNVERIFIED",
            "攻略候选尚未完成地点校验",
            status_code=422,
            detail={"titles": unverified},
        )
    trip = await session.get(Trip, run.trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")
    new_version = await bump_trip_version(
        session,
        trip_id=trip.id,
        expected_version=base_version,
        user_id=user_id,
        resource_type="activity",
        resource_id=None,
        submitted_content={
            "source": "ai_import_guide",
            "ai_run_id": run.id,
            "candidate_ids": selected_ids,
        },
    )
    existing_ids = list(
        (
            await session.scalars(
                select(DayActivity.agent_activity_id).where(DayActivity.trip_id == trip.id)
            )
        ).all()
    )
    numeric_activity_ids = [
        int(match.group(1))
        for value in existing_ids
        if (match := re.fullmatch(r"act-(\d+)", value))
    ]
    next_activity_number = max(numeric_activity_ids, default=0)
    day_count = (trip.end_date - trip.start_date).days + 1
    created: list[DayActivity] = []
    placement_by_id = {item["candidate_id"]: item for item in normalized_placements}
    for offset, candidate_id in enumerate(selected_ids, start=1):
        item = by_id[candidate_id]
        day_number = placement_by_id[candidate_id]["day_number"]
        order_index = placement_by_id[candidate_id]["order_index"]
        if not 1 <= day_number <= day_count:
            raise AppError("INVALID_DAY", "候选活动日期不在行程范围内", status_code=422)
        await session.execute(
            update(DayActivity)
            .where(
                DayActivity.trip_id == trip.id,
                DayActivity.day_number == day_number,
                DayActivity.order_index >= order_index,
            )
            .values(order_index=DayActivity.order_index + 1)
        )
        slot = item.get("time_slot") or {}
        start = slot.get("start")
        end = slot.get("end")
        location = item.get("location") or {}
        cost = item.get("cost") or {}
        activity = DayActivity(
            trip_id=trip.id,
            agent_activity_id=f"act-{next_activity_number + offset}",
            day_number=day_number,
            order_index=order_index,
            title=item["title"],
            type=DB_TYPE_BY_AGENT_TYPE.get(item.get("type"), "other"),
            start_time=datetime.strptime(start, "%H:%M").time() if start else None,
            duration_min=_duration_minutes(start, end) or _default_duration(item.get("type")),
            location_name=location.get("name") or item["title"],
            latitude=location.get("lat"),
            longitude=location.get("lng"),
            price_estimated=(item.get("quoted_cost") or cost).get("amount"),
            price_source=(item.get("quoted_cost") or cost).get("source", "llm"),
            price_queried_at=_parse_queried_at((item.get("quoted_cost") or cost).get("fetched_at")),
            description=item.get("note"),
            poi_provider=location.get("poi_source"),
            poi_id=location.get("poi_id"),
            extra={
                "guide_excerpt": item.get("excerpt"),
                "candidate_id": candidate_id,
                "address": location.get("address"),
                "open_hours_hint": item.get("open_hours_hint"),
            },
        )
        session.add(activity)
        await session.flush()
        created.append(activity)
    await _reschedule_days(session, trip.id, {item["day_number"] for item in normalized_placements})
    applied_output = {
        **output,
        "candidates": [
            {**item, "selected": item.get("candidate_id") in selected_ids} for item in candidates
        ],
    }
    run.candidate_output = applied_output
    run.status = "applied"
    run.applied_at = datetime.now(UTC)
    session.add(
        TripRevision(
            trip_id=trip.id,
            user_id=user_id,
            version=new_version,
            action="guide_import",
            resource_type="activity",
            resource_id=None,
            diff_content={
                "source": "ai_import_guide",
                "ai_run_id": run.id,
                "placements": normalized_placements,
                "created_activity_ids": [item.agent_activity_id for item in created],
            },
        )
    )
    await session.commit()
    return [
        {
            "id": item.id,
            "agent_activity_id": item.agent_activity_id,
            "day_number": item.day_number,
            "title": item.title,
        }
        for item in created
    ], new_version


async def verify_guide_candidates(
    *,
    session: AsyncSession,
    run: AiRunLog,
    trip_version: int,
    placements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if run.run_type != "import_guide" or run.status != "succeeded":
        raise ConflictError("该 AI 运行没有可校验的攻略候选")
    base_version = int(run.input_snapshot["base_version"])
    trip = await session.get(Trip, run.trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")
    if trip_version != base_version or trip.version != base_version:
        raise ConflictError("行程已发生变化，请刷新后重新导入攻略")
    normalized = _normalize_placements(placements)
    if not normalized:
        raise AppError("NO_CANDIDATES_SELECTED", "请至少选择一个候选条目", status_code=422)
    day_count = (trip.end_date - trip.start_date).days + 1
    if any(item["day_number"] > day_count for item in normalized):
        raise AppError("INVALID_DAY", "候选活动日期不在行程范围内", status_code=422)
    output = dict(run.candidate_output or {})
    candidates = [dict(item) for item in output.get("candidates", [])]
    by_id = {item.get("candidate_id"): item for item in candidates}
    missing = [item["candidate_id"] for item in normalized if item["candidate_id"] not in by_id]
    if missing:
        raise AppError("CANDIDATE_NOT_FOUND", "部分候选条目不存在", status_code=422, detail=missing)
    client = get_amap_client()
    failures: list[dict[str, str]] = []
    verified: list[dict[str, Any]] = []
    for placement in normalized:
        candidate = by_id[placement["candidate_id"]]
        query = str(
            (candidate.get("location") or {}).get("name") or candidate.get("title") or ""
        ).strip()
        result = await client.search_poi(keyword=query, city=normalize_poi_search_city(trip.city))
        poi = _pick_poi(
            result.get("items", []),
            query,
            trip.city,
            expected_type=str(candidate.get("type") or "") or None,
        )
        reason = poi_unavailable_reason(poi or {})
        poi_has_identity = bool(
            poi
            and poi.get("poi_id")
            and poi.get("longitude") is not None
            and poi.get("latitude") is not None
        )
        if not poi_has_identity or reason:
            failures.append(
                {
                    "candidate_id": placement["candidate_id"],
                    "title": str(candidate.get("title") or query),
                    "message": f"地点已标记为“{reason}”"
                    if reason
                    else "未找到名称和行政区都可靠的高德地点",
                }
            )
            continue
        queried_at = result.get("queried_at")
        if isinstance(queried_at, datetime):
            queried_at = queried_at.astimezone(UTC).isoformat()
        candidate["location"] = {
            "name": poi.get("name") or query,
            "address": poi.get("address"),
            "lng": poi.get("longitude"),
            "lat": poi.get("latitude"),
            "poi_id": poi.get("poi_id"),
            "poi_source": "amap",
        }
        if poi.get("open_hours") and candidate.get("type") != "transport":
            candidate["open_hours_hint"] = str(poi["open_hours"])
        if poi.get("average_cost") is not None:
            candidate["quoted_cost"] = {
                "amount": poi["average_cost"],
                "source": "amap",
                "fetched_at": queried_at,
                "note": "高德商户参考人均，非购票价格",
            }
        verified.append(candidate)
    if failures:
        raise AppError(
            "GUIDE_POI_UNVERIFIED",
            "部分攻略地点无法通过高德校验，请取消选择或修改攻略文字",
            status_code=422,
            detail=failures,
        )
    verified_by_id = {item["candidate_id"]: item for item in verified}
    output["candidates"] = [
        verified_by_id.get(item.get("candidate_id"), item) for item in candidates
    ]
    output["verified_placements"] = normalized
    output["verified_at"] = datetime.now(UTC).isoformat()
    run.candidate_output = output
    await session.commit()
    return verified


def _normalize_placements(placements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_slots: set[tuple[int, int]] = set()
    for item in placements:
        candidate_id = str(item.get("candidate_id") or "").strip()
        day_number = item.get("day_number")
        order_index = item.get("order_index")
        if not candidate_id or not isinstance(day_number, int) or not isinstance(order_index, int):
            raise AppError("INVALID_GUIDE_PLACEMENT", "攻略候选的日期或序号无效", status_code=422)
        if candidate_id in seen_ids or (day_number, order_index) in seen_slots:
            raise AppError(
                "DUPLICATE_GUIDE_PLACEMENT", "同一候选或同一插入位置不能重复", status_code=422
            )
        seen_ids.add(candidate_id)
        seen_slots.add((day_number, order_index))
        normalized.append(
            {"candidate_id": candidate_id, "day_number": day_number, "order_index": order_index}
        )
    return sorted(
        normalized, key=lambda item: (item["day_number"], item["order_index"], item["candidate_id"])
    )


def _is_verified_candidate(item: dict[str, Any]) -> bool:
    location = item.get("location") or {}
    return bool(
        location.get("poi_source") == "amap"
        and location.get("poi_id")
        and location.get("lng") is not None
        and location.get("lat") is not None
    )


def _default_duration(agent_type: Any) -> int:
    return {"poi": 120, "meal": 90, "hotel": 60, "transport": 45, "free_time": 90}.get(
        str(agent_type), 90
    )


def _parse_queried_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _reschedule_days(session: AsyncSession, trip_id: int, day_numbers: set[int]) -> None:
    trip = await session.get(Trip, trip_id)
    client = get_amap_client()
    for day_number in day_numbers:
        activities = list(
            (
                await session.scalars(
                    select(DayActivity)
                    .where(DayActivity.trip_id == trip_id, DayActivity.day_number == day_number)
                    .order_by(DayActivity.order_index, DayActivity.id)
                )
            ).all()
        )
        cursor = 9 * 60
        if activities and activities[0].start_time:
            cursor = activities[0].start_time.hour * 60 + activities[0].start_time.minute
        previous: DayActivity | None = None
        for index, activity in enumerate(activities, start=1):
            if previous is not None:
                gap = 30
                explicit_transport = previous.type == "transport" or activity.type == "transport"
                if explicit_transport:
                    gap = 0
                elif None not in (
                    previous.longitude,
                    previous.latitude,
                    activity.longitude,
                    activity.latitude,
                ):
                    try:
                        routes = await client.routes(
                            from_lng=float(previous.longitude),
                            from_lat=float(previous.latitude),
                            to_lng=float(activity.longitude),
                            to_lat=float(activity.latitude),
                            city_code=trip.city_adcode if trip else None,
                        )
                        durations = [
                            int(item.get("duration_min") or 0)
                            for item in (routes.get("routes") or {}).values()
                            if item.get("available") and int(item.get("duration_min") or 0) > 0
                        ]
                        if durations:
                            gap = min(durations) + 15
                    except AppError:
                        pass
                cursor += gap
            duration = activity.duration_min or 90
            open_hours = (activity.extra or {}).get("open_hours_hint")
            ranges = (
                _opening_ranges(open_hours)
                if activity.type != "transport" and isinstance(open_hours, str)
                else []
            )
            scheduled_start = _next_open_start(cursor, duration, ranges)
            if scheduled_start is None:
                raise AppError(
                    "GUIDE_OPEN_HOURS_NO_FIT",
                    f"第 {day_number} 天的“{activity.title}”无法在营业时间内排完，请调整插入位置",
                    status_code=422,
                )
            cursor = scheduled_start
            if cursor + duration >= 24 * 60:
                raise AppError(
                    "GUIDE_DAY_OVERFLOW",
                    f"第 {day_number} 天加入候选后无法在当天排完，请调整日期或减少候选",
                    status_code=422,
                )
            activity.order_index = index
            activity.start_time = datetime.strptime(
                f"{cursor // 60:02d}:{cursor % 60:02d}", "%H:%M"
            ).time()
            cursor += duration
            previous = activity


def _guide_candidate_errors(output: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    candidates = output.get("candidates")
    warnings = output.get("warnings")
    if not isinstance(candidates, list):
        return [{"field": "candidates", "message": "candidates 必须是数组"}]
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        errors.append({"field": "warnings", "message": "warnings 必须是字符串数组"})
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    for index, item in enumerate(candidates):
        if not isinstance(item, dict):
            errors.append({"index": index, "message": "候选必须是对象"})
            continue
        for field in ("candidate_id", "title", "excerpt"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append({"index": index, "field": field, "message": f"{field} 不能为空"})
        candidate_id = item.get("candidate_id")
        title = item.get("title")
        if candidate_id in seen_ids:
            errors.append({"index": index, "field": "candidate_id", "message": "候选 ID 重复"})
        if title in seen_titles:
            errors.append({"index": index, "field": "title", "message": "候选标题重复"})
        if isinstance(candidate_id, str):
            seen_ids.add(candidate_id)
        if isinstance(title, str):
            seen_titles.add(title)
    return errors


def _duration_minutes(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    start_dt = datetime.strptime(start, "%H:%M")
    end_dt = datetime.strptime(end, "%H:%M")
    minutes = int((end_dt - start_dt).total_seconds() // 60)
    return minutes if minutes > 0 else None
