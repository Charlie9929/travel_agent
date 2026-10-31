from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_contracts.loader import load_shared_prompt
from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.models import AiRunLog, DayActivity, Trip, TripRevision
from app.integrations.llm import LLMResult
from app.services.ai_service import get_llm_client
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
    selected_candidate_ids: list[str],
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
    candidates = (run.candidate_output or {}).get("candidates", [])
    by_id = {item.get("candidate_id"): item for item in candidates}
    selected_ids = list(dict.fromkeys(selected_candidate_ids))
    if not selected_ids:
        raise AppError("NO_CANDIDATES_SELECTED", "请至少选择一个候选条目", status_code=422)
    missing = [candidate_id for candidate_id in selected_ids if candidate_id not in by_id]
    if missing:
        raise AppError(
            "CANDIDATE_NOT_FOUND",
            "部分候选条目不存在",
            status_code=422,
            detail={"candidate_ids": missing},
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
    for offset, candidate_id in enumerate(selected_ids, start=1):
        item = by_id[candidate_id]
        day_number = item.get("suggested_day_index") or 1
        if not isinstance(day_number, int) or not 1 <= day_number <= day_count:
            day_number = 1
        max_order = await session.scalar(
            select(func.max(DayActivity.order_index)).where(
                DayActivity.trip_id == trip.id, DayActivity.day_number == day_number
            )
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
            order_index=(max_order or 0) + 1,
            title=item["title"],
            type=DB_TYPE_BY_AGENT_TYPE.get(item.get("type"), "other"),
            start_time=datetime.strptime(start, "%H:%M").time() if start else None,
            duration_min=_duration_minutes(start, end),
            location_name=location.get("name") or item["title"],
            latitude=location.get("lat"),
            longitude=location.get("lng"),
            price_estimated=cost.get("amount"),
            price_source=cost.get("source", "llm"),
            description=item.get("note"),
            poi_provider=location.get("poi_source"),
            poi_id=location.get("poi_id"),
            extra={"guide_excerpt": item.get("excerpt"), "candidate_id": candidate_id},
        )
        session.add(activity)
        await session.flush()
        created.append(activity)
    applied_output = {
        **(run.candidate_output or {}),
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
                "candidate_ids": selected_ids,
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
