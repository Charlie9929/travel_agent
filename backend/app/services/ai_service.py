import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_contracts.loader import load_itinerary_schema, load_prompt, validate_itinerary
from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.models import AiRunLog, DayActivity, Trip, TripRevision
from app.integrations.amap import AmapClient
from app.integrations.llm import DeepSeekClient, FakeLLMClient, LLMClient, LLMResult
from app.services.poi_enrichment import enrich_itinerary_pois
from app.services.versioning import bump_trip_version

TYPE_MAP = {
    "poi": "sight",
    "meal": "food",
    "hotel": "hotel",
    "transport": "transport",
    "free_time": "other",
}
MAX_SCHEMA_REPAIR_RETRIES = 2
REPAIR_INSTRUCTION = """

# JSON 修复模式
上一次输出未通过 JSON Schema 校验。请根据用户原始需求和 validation_errors 修复 invalid_output。
必须返回修复后的完整行程 JSON；只输出 JSON，不要说明、不要 Markdown 代码块。
保持已经正确的活动、日期、时间和金额，只修复违反契约的部分。
""".strip()


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_use_fake:
        return FakeLLMClient()
    return DeepSeekClient(
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
    )


def get_amap_client() -> AmapClient:
    settings = get_settings()
    return AmapClient(
        base_url=settings.amap_base_url,
        api_key=settings.amap_api_key,
        timeout_seconds=settings.amap_timeout_seconds,
        min_interval_seconds=settings.amap_min_interval_seconds,
        rate_limit_retries=settings.amap_rate_limit_retries,
    )


async def generate_initial_itinerary(
    *,
    session: AsyncSession,
    trip_id: int,
    user_id: int,
    additional_requirements: str | None,
) -> tuple[AiRunLog, LLMResult, int]:
    settings = get_settings()
    trip = await session.scalar(select(Trip).where(Trip.id == trip_id))
    if trip is None:
        raise NotFoundError("行程不存在")

    prompt_version = "v0.1"
    run = AiRunLog(
        trip_id=trip_id,
        requested_by=user_id,
        run_type="generate",
        prompt_version=prompt_version,
        input_snapshot={
            "trip": {
                "city": trip.city,
                "start_date": trip.start_date.isoformat(),
                "end_date": trip.end_date.isoformat(),
                "total_budget": float(trip.total_budget) if trip.total_budget is not None else None,
                "traveler_count": trip.traveler_count,
                "preferences": trip.preferences,
                "constraints": trip.constraints,
                "version": trip.version,
            },
            "additional_requirements": additional_requirements,
        },
        status="running",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    run_id = int(run.id)
    base_version = int(run.input_snapshot["trip"]["version"])
    run_input_snapshot = run.input_snapshot
    retry_count = 0
    failed_candidate: dict | None = None

    system_prompt = load_prompt("itinerary-generation", prompt_version)
    user_prompt = json.dumps(run_input_snapshot, ensure_ascii=False, default=str)
    request_id = f"ai-{run_id}-{uuid4().hex[:12]}"
    try:
        llm_client = get_llm_client()
        schema = load_itinerary_schema()
        result = await llm_client.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=schema,
            model=settings.deepseek_model,
            prompt_version=prompt_version,
            request_id=request_id,
            timeout_seconds=settings.deepseek_timeout_seconds,
        )

        while True:
            data = _complete_system_fields(result.parsed_data, trip)
            failed_candidate = data
            try:
                validate_itinerary(data)
                break
            except AppError as exc:
                if exc.code != "AGENT_OUTPUT_INVALID" or retry_count >= MAX_SCHEMA_REPAIR_RETRIES:
                    raise
                retry_count += 1
                repair_payload = {
                    "original_request": run_input_snapshot,
                    "validation_errors": exc.detail,
                    "invalid_output": data,
                }
                result = await llm_client.generate_json(
                    system_prompt=f"{system_prompt}\n\n{REPAIR_INSTRUCTION}",
                    user_prompt=json.dumps(repair_payload, ensure_ascii=False, default=str),
                    schema=schema,
                    model=settings.deepseek_model,
                    prompt_version=prompt_version,
                    request_id=f"{request_id}-repair-{retry_count}",
                    timeout_seconds=settings.deepseek_timeout_seconds,
                    temperature=0.3,
                )

        if _has_locations_to_enrich(data):
            data = await enrich_itinerary_pois(data, city=trip.city, client=get_amap_client())
            validate_itinerary(data)

        new_version = await bump_trip_version(
            session,
            trip_id=trip.id,
            expected_version=base_version,
            user_id=user_id,
            resource_type="activity",
            resource_id=None,
            submitted_content={"source": "ai_generate", "ai_run_id": run.id},
        )
        data["version"] = new_version
        validate_itinerary(data)
        await _replace_activities(session, trip, data)
        result.parsed_data = data
        run.candidate_output = data
        run.status = "applied"
        run.retry_count = retry_count
        run.applied_at = datetime.now(UTC)
        session.add(
            TripRevision(
                trip_id=trip.id,
                user_id=user_id,
                version=new_version,
                action="create",
                resource_type="activity",
                resource_id=None,
                diff_content={"source": "ai_generate", "ai_run_id": run.id},
            )
        )
        await session.commit()
        return run, result, new_version
    except AppError as exc:
        original_detail = exc.detail
        await _mark_run_failed(
            session,
            run_id=run_id,
            error_code=exc.code,
            retry_count=retry_count,
            candidate=failed_candidate,
            validation_errors=original_detail if exc.code == "AGENT_OUTPUT_INVALID" else None,
        )
        exc.detail = {
            "ai_run_id": run_id,
            "retry_count": retry_count,
            "validation_errors": original_detail if exc.code == "AGENT_OUTPUT_INVALID" else None,
            "provider_detail": original_detail if exc.code != "AGENT_OUTPUT_INVALID" else None,
        }
        raise
    except Exception:
        await _mark_run_failed(
            session,
            run_id=run_id,
            error_code="INTERNAL_ERROR",
            retry_count=retry_count,
            candidate=failed_candidate,
        )
        raise


async def _mark_run_failed(
    session: AsyncSession,
    *,
    run_id: int,
    error_code: str,
    retry_count: int,
    candidate: dict | None,
    validation_errors: object | None = None,
) -> None:
    await session.rollback()
    failed_run = await session.get(AiRunLog, run_id)
    if failed_run is None:
        return
    failed_run.status = "failed"
    failed_run.error_code = error_code
    failed_run.retry_count = retry_count
    if candidate is not None:
        failed_run.candidate_output = {
            "invalid_output": candidate,
            "validation_errors": validation_errors,
        }
    await session.commit()


async def retry_failed_ai_run(
    *, session: AsyncSession, run: AiRunLog, user_id: int
) -> tuple[dict, int]:
    resumable_errors = {"AMAP_ERROR", "AMAP_RATE_LIMIT", "AMAP_TIMEOUT", "AMAP_UNAVAILABLE"}
    saved = run.candidate_output or {}
    candidate = saved.get("invalid_output") if isinstance(saved, dict) else None
    if run.status != "failed" or run.error_code not in resumable_errors or not candidate:
        raise ConflictError(
            "该 AI 运行不能从 POI 阶段恢复",
            {"ai_run_id": run.id, "status": run.status, "error_code": run.error_code},
        )

    run_id = int(run.id)
    base_version = int(run.input_snapshot["trip"]["version"])
    retry_count = int(run.retry_count)
    validate_itinerary(candidate)
    trip = await session.get(Trip, run.trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")

    try:
        data = await enrich_itinerary_pois(candidate, city=trip.city, client=get_amap_client())
        validate_itinerary(data)
        new_version = await bump_trip_version(
            session,
            trip_id=trip.id,
            expected_version=base_version,
            user_id=user_id,
            resource_type="activity",
            resource_id=None,
            submitted_content={"source": "ai_generate_resume", "ai_run_id": run_id},
        )
        data["version"] = new_version
        validate_itinerary(data)
        await _replace_activities(session, trip, data)
        run.candidate_output = data
        run.status = "applied"
        run.error_code = None
        run.applied_at = datetime.now(UTC)
        session.add(
            TripRevision(
                trip_id=trip.id,
                user_id=user_id,
                version=new_version,
                action="create",
                resource_type="activity",
                resource_id=None,
                diff_content={"source": "ai_generate_resume", "ai_run_id": run_id},
            )
        )
        await session.commit()
        return data, new_version
    except AppError as exc:
        await _mark_run_failed(
            session,
            run_id=run_id,
            error_code=exc.code,
            retry_count=retry_count,
            candidate=candidate,
        )
        exc.detail = {
            "ai_run_id": run_id,
            "retry_count": retry_count,
            "provider_detail": exc.detail,
        }
        raise


def _has_locations_to_enrich(data: dict) -> bool:
    return any(
        isinstance(activity.get("location"), dict)
        for day in data.get("days", [])
        for activity in day.get("activities", [])
    )


def _complete_system_fields(data: dict, trip: Trip) -> dict:
    completed = dict(data)
    completed["schema_version"] = completed.get("schema_version") or "1.0"
    completed["trip_id"] = str(trip.agent_trip_id)
    completed["version"] = trip.version + 1
    completed["city"] = {**(completed.get("city") or {}), "name": trip.city}
    meta = completed.setdefault("meta", {})
    meta["date_start"] = trip.start_date.isoformat()
    meta["date_end"] = trip.end_date.isoformat()
    meta["traveler_count"] = trip.traveler_count or 1
    meta["budget_total"] = {
        "amount": float(trip.total_budget or 0),
        "currency": "CNY",
        "price_type": "estimate",
        "source": "manual",
    }
    if isinstance(meta.get("budget_total"), (int, float)):
        meta["budget_total"] = {
            "amount": meta["budget_total"],
            "currency": "CNY",
            "price_type": "estimate",
            "source": "llm",
        }
    completed.setdefault("days", [])
    completed.setdefault(
        "cost_summary",
        {
            "total_estimate": {
                "amount": 0,
                "currency": "CNY",
                "price_type": "estimate",
                "source": "rule",
            }
        },
    )
    completed.setdefault("members", [])
    completed.setdefault("permissions", {"collab_mode": "A2_poll", "edit_policy": "all_members"})
    completed.setdefault("revisions", [])
    completed.setdefault("candidates", [])
    return completed


async def _replace_activities(session: AsyncSession, trip: Trip, data: dict) -> None:
    await session.execute(delete(DayActivity).where(DayActivity.trip_id == trip.id))
    for day in data.get("days", []):
        for index, item in enumerate(day.get("activities", []), start=1):
            slot = item.get("time_slot") or {}
            start = slot.get("start")
            end = slot.get("end")
            duration = _duration_minutes(start, end)
            location = item.get("location") or {}
            cost = item.get("cost") or {}
            session.add(
                DayActivity(
                    trip_id=trip.id,
                    agent_activity_id=item["activity_id"],
                    day_number=day["day_index"],
                    order_index=index,
                    title=item["title"],
                    type=TYPE_MAP.get(item["type"], "other"),
                    start_time=datetime.strptime(start, "%H:%M").time() if start else None,
                    duration_min=duration,
                    location_name=location.get("name"),
                    latitude=location.get("lat"),
                    longitude=location.get("lng"),
                    price_estimated=cost.get("amount"),
                    price_source=cost.get("source", "llm"),
                    description=item.get("note"),
                    poi_provider=location.get("poi_source"),
                    poi_id=location.get("poi_id"),
                    extra={"open_hours_hint": item.get("open_hours_hint")},
                )
            )


def _duration_minutes(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    start_dt = datetime.strptime(start, "%H:%M")
    end_dt = datetime.strptime(end, "%H:%M")
    minutes = int((end_dt - start_dt).total_seconds() // 60)
    return minutes if minutes > 0 else None
