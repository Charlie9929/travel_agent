import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_contracts.business_validation import (
    validate_replan_candidate,
    validate_revision_candidate,
)
from app.agent_contracts.loader import (
    load_itinerary_schema,
    load_shared_prompt,
    validate_itinerary,
)
from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.models import AiRunLog, DayActivity, Trip, TripRevision
from app.integrations.amap import AmapClient
from app.integrations.llm import DeepSeekClient, FakeLLMClient, LLMClient, LLMResult
from app.integrations.qweather import QWeatherClient
from app.services.itinerary_snapshot import build_itinerary_snapshot
from app.services.poi_enrichment import enrich_itinerary_pois
from app.services.trip_validation import enrich_route_checks, validate_trip_rules
from app.services.versioning import bump_trip_version
from app.services.weather_enrichment import enrich_itinerary_weather

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
REPLAN_REPAIR_INSTRUCTION = """

# JSON 修复模式
上一次重排候选未通过契约或业务校验。请根据 validation_errors 修复 invalid_output。
必须返回完整的候选 JSON，包含 summary、diff.ops 和 proposed_itinerary；只输出 JSON。
只修复报错部分，不得扩大重排范围，不得更改未涉及活动的 activity_id。
""".strip()
REVISION_REPAIR_INSTRUCTION = """

# JSON 修复模式
上一次修订候选未通过契约或业务校验。请根据 validation_errors 修复 invalid_output。
必须返回完整候选 JSON，包含 summary、diff.ops 和 proposed_itinerary；只输出 JSON。
只修复报错部分，保持未修改活动的 activity_id 和内容不变。
""".strip()
EXPLANATION_REPAIR_INSTRUCTION = """

# JSON 修复模式
上一次差异说明缺少必需字段。请根据 validation_errors 修复 invalid_output。
只输出符合当前模式输出骨架的 JSON，不要 Markdown 或额外文字。
""".strip()


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_use_fake:
        return FakeLLMClient()
    return DeepSeekClient(
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
    )


@lru_cache
def get_amap_client() -> AmapClient:
    settings = get_settings()
    return AmapClient(
        base_url=settings.amap_base_url,
        api_key=settings.amap_api_key,
        timeout_seconds=settings.amap_timeout_seconds,
        min_interval_seconds=settings.amap_min_interval_seconds,
        rate_limit_retries=settings.amap_rate_limit_retries,
    )


@lru_cache
def get_qweather_client() -> QWeatherClient:
    settings = get_settings()
    return QWeatherClient(
        api_host=settings.qweather_api_host,
        auth_type=settings.qweather_auth_type,
        api_key=settings.qweather_api_key,
        jwt_token=settings.qweather_jwt_token,
        timeout_seconds=settings.qweather_timeout_seconds,
        retries=settings.qweather_retries,
        cache_ttl_seconds=settings.qweather_cache_ttl_seconds,
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

    amap_client = get_amap_client()
    poi_candidates, pre_generation_warnings = await _prequery_poi_candidates(
        city=trip.city,
        client=amap_client,
    )
    constraints = _generation_constraints(trip)

    prompt_version = "v0.2"
    run = AiRunLog(
        trip_id=trip_id,
        requested_by=user_id,
        run_type="generate",
        prompt_version=prompt_version,
        input_snapshot={
            "trip": {"id": trip.id, "version": trip.version},
            "constraints": constraints,
            "poi_candidates": poi_candidates,
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

    system_prompt = load_shared_prompt("itinerary-generation", prompt_version)
    user_prompt = json.dumps(
        {
            "constraints": constraints,
            "poi_candidates": poi_candidates,
            "additional_requirements": additional_requirements,
            "fallback_instruction": (
                "若 poi_candidates 为空，不得编造 poi；可以安排 meal、transport、"
                "hotel 或 free_time，且每天至少一个活动。"
            ),
        },
        ensure_ascii=False,
        default=str,
    )
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
                _validate_initial_generation_content(data)
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

        integration_warnings: list[dict] = list(pre_generation_warnings)
        if _has_locations_to_enrich(data):
            try:
                data = await enrich_itinerary_pois(data, city=trip.city, client=amap_client)
            except AppError as exc:
                if not exc.code.startswith("AMAP_"):
                    raise
                integration_warnings.append(
                    {
                        "service": "amap",
                        "code": exc.code,
                        "message": exc.message,
                        "degraded": True,
                    }
                )
        data, weather_warnings = await enrich_itinerary_weather(
            data,
            city_code=trip.city,
            client=get_qweather_client(),
        )
        integration_warnings.extend({**warning, "degraded": True} for warning in weather_warnings)
        data, route_errors, route_warnings = await enrich_route_checks(data, client=amap_client)
        integration_warnings.extend({**warning, "degraded": True} for warning in route_warnings)
        integration_warnings.extend(
            {**error, "degraded": True, "requires_user_review": True} for error in route_errors
        )
        rule_result = validate_trip_rules(data)
        if rule_result["errors"]:
            raise AppError(
                "AGENT_CONSTRAINT_VIOLATION",
                "生成的行程未通过时间、预算或真实路线校验",
                status_code=422,
                detail=rule_result,
            )
        data["integration_warnings"] = integration_warnings
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


async def generate_replan_candidate(
    *,
    session: AsyncSession,
    trip_id: int,
    user_id: int,
    day_number: int,
    adjustment_requirements: str,
    trip_version: int,
    after_time: str | None,
    trigger: dict,
    candidate_replacements: list[dict],
) -> tuple[AiRunLog, LLMResult]:
    settings = get_settings()
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")
    if trip.version != trip_version:
        raise ConflictError(
            "行程版本已经变化，请刷新后重新生成重排方案",
            {"submitted_version": trip_version, "current_version": trip.version},
        )

    old_itinerary = await build_itinerary_snapshot(session, trip_id)
    prompt_version = "v0.2"
    scope = {
        "type": "rest_of_day",
        "day_index": day_number,
        "after_time": after_time or "00:00",
    }
    effective_trigger = {
        "reason_type": trigger.get("reason_type", "user_request"),
        "description": trigger.get("description", adjustment_requirements),
        "target_activity_ids": trigger.get("target_activity_ids", []),
    }
    input_snapshot = {
        "base_version": trip_version,
        "itinerary": old_itinerary,
        "scope": scope,
        "trigger": effective_trigger,
        "adjustment_requirements": adjustment_requirements,
        "candidate_replacements": candidate_replacements,
    }
    run = AiRunLog(
        trip_id=trip_id,
        requested_by=user_id,
        run_type="replan",
        prompt_version=prompt_version,
        input_snapshot=input_snapshot,
        status="running",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    run_id = int(run.id)
    retry_count = 0
    failed_candidate: dict | None = None
    system_prompt = load_shared_prompt("replan-day", prompt_version)
    user_prompt = json.dumps(
        {
            "itinerary_json": old_itinerary,
            "scope": scope,
            "trigger": effective_trigger,
            "user_instruction": adjustment_requirements,
            "candidate_replacements": candidate_replacements,
        },
        ensure_ascii=False,
        default=str,
    )
    request_id = f"ai-{run_id}-{uuid4().hex[:12]}"
    llm_client = get_llm_client()
    try:
        result = await llm_client.generate_json(
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
            candidate = _complete_replan_candidate(result.parsed_data, old_itinerary)
            failed_candidate = candidate
            try:
                proposed = candidate["proposed_itinerary"]
                validate_itinerary(proposed)
                validate_replan_candidate(
                    old_itinerary,
                    candidate,
                    day_number=day_number,
                    after_time=scope["after_time"],
                )
                break
            except AppError as exc:
                if exc.code != "AGENT_OUTPUT_INVALID" or retry_count >= MAX_SCHEMA_REPAIR_RETRIES:
                    raise
                retry_count += 1
                repair_payload = {
                    "original_request": input_snapshot,
                    "validation_errors": exc.detail,
                    "invalid_output": candidate,
                }
                result = await llm_client.generate_json(
                    system_prompt=f"{system_prompt}\n\n{REPLAN_REPAIR_INSTRUCTION}",
                    user_prompt=json.dumps(repair_payload, ensure_ascii=False, default=str),
                    schema={},
                    model=settings.deepseek_model,
                    prompt_version=prompt_version,
                    request_id=f"{request_id}-repair-{retry_count}",
                    timeout_seconds=settings.deepseek_timeout_seconds,
                    temperature=0.3,
                )

        result.parsed_data = candidate
        run.candidate_output = candidate
        run.status = "succeeded"
        run.retry_count = retry_count
        await session.commit()
        return run, result
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


async def generate_revision_candidate(
    *,
    session: AsyncSession,
    trip_id: int,
    user_id: int,
    changed_constraints: dict,
    user_instruction: str | None,
    trip_version: int,
) -> tuple[AiRunLog, LLMResult]:
    settings = get_settings()
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")
    if trip.version != trip_version:
        raise ConflictError(
            "行程版本已经变化，请刷新后重新生成修订方案",
            {"submitted_version": trip_version, "current_version": trip.version},
        )
    old_itinerary = await build_itinerary_snapshot(session, trip_id)
    prompt_version = "v0.2"
    input_snapshot = {
        "base_version": trip_version,
        "itinerary": old_itinerary,
        "changed_constraints": changed_constraints,
        "user_instruction": user_instruction,
    }
    run = AiRunLog(
        trip_id=trip_id,
        requested_by=user_id,
        run_type="revise",
        prompt_version=prompt_version,
        input_snapshot=input_snapshot,
        status="running",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    run_id = int(run.id)
    retry_count = 0
    failed_candidate: dict | None = None
    system_prompt = load_shared_prompt("revise-itinerary", prompt_version)
    user_prompt = json.dumps(
        {
            "itinerary_json": old_itinerary,
            "changed_constraints": changed_constraints,
            "user_instruction": user_instruction,
        },
        ensure_ascii=False,
        default=str,
    )
    request_id = f"ai-{run_id}-{uuid4().hex[:12]}"
    llm_client = get_llm_client()
    try:
        result = await llm_client.generate_json(
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
            candidate = _complete_replan_candidate(result.parsed_data, old_itinerary)
            failed_candidate = candidate
            try:
                validate_itinerary(candidate["proposed_itinerary"])
                validate_revision_candidate(old_itinerary, candidate)
                break
            except AppError as exc:
                if exc.code != "AGENT_OUTPUT_INVALID" or retry_count >= MAX_SCHEMA_REPAIR_RETRIES:
                    raise
                retry_count += 1
                result = await llm_client.generate_json(
                    system_prompt=f"{system_prompt}\n\n{REVISION_REPAIR_INSTRUCTION}",
                    user_prompt=json.dumps(
                        {
                            "original_request": input_snapshot,
                            "validation_errors": exc.detail,
                            "invalid_output": candidate,
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
        result.parsed_data = candidate
        run.candidate_output = candidate
        run.status = "succeeded"
        run.retry_count = retry_count
        await session.commit()
        return run, result
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


async def generate_diff_explanation(
    *,
    session: AsyncSession,
    trip_id: int,
    user_id: int,
    mode: str,
    old_itinerary: dict,
    new_itinerary: dict | list[dict],
    teammate_itinerary: dict | None,
) -> tuple[AiRunLog, LLMResult]:
    settings = get_settings()
    if await session.get(Trip, trip_id) is None:
        raise NotFoundError("行程不存在")
    prompt_version = "v0.2"
    input_snapshot = {
        "mode": mode,
        "old_itinerary": old_itinerary,
        "new_itinerary": new_itinerary,
        "teammate_itinerary": teammate_itinerary,
    }
    run = AiRunLog(
        trip_id=trip_id,
        requested_by=user_id,
        run_type="explain_diff",
        prompt_version=prompt_version,
        input_snapshot=input_snapshot,
        status="running",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    run_id = int(run.id)
    retry_count = 0
    failed_candidate: dict | None = None
    system_prompt = load_shared_prompt("explain-diff", prompt_version)
    request_id = f"ai-{run_id}-{uuid4().hex[:12]}"
    llm_client = get_llm_client()
    try:
        result = await llm_client.generate_json(
            system_prompt=system_prompt,
            user_prompt=json.dumps(input_snapshot, ensure_ascii=False, default=str),
            schema={},
            model=settings.deepseek_model,
            prompt_version=prompt_version,
            request_id=request_id,
            timeout_seconds=settings.deepseek_timeout_seconds,
            temperature=0.3,
        )
        while True:
            failed_candidate = result.parsed_data
            errors = _diff_explanation_errors(mode, result.parsed_data)
            if not errors:
                break
            if retry_count >= MAX_SCHEMA_REPAIR_RETRIES:
                raise AppError(
                    "AGENT_OUTPUT_INVALID",
                    "差异说明不符合契约",
                    status_code=502,
                    detail=errors,
                )
            retry_count += 1
            result = await llm_client.generate_json(
                system_prompt=f"{system_prompt}\n\n{EXPLANATION_REPAIR_INSTRUCTION}",
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
        await _mark_run_failed(
            session,
            run_id=run_id,
            error_code=exc.code,
            retry_count=retry_count,
            candidate=failed_candidate,
            validation_errors=exc.detail if exc.code == "AGENT_OUTPUT_INVALID" else None,
        )
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


async def apply_ai_candidate(
    *,
    session: AsyncSession,
    run: AiRunLog,
    user_id: int,
    trip_version: int,
) -> tuple[dict, int]:
    if (
        run.run_type not in {"replan", "revise"}
        or run.status != "succeeded"
        or not run.candidate_output
    ):
        raise ConflictError(
            "该 AI 运行没有可应用的候选方案",
            {"ai_run_id": run.id, "status": run.status, "run_type": run.run_type},
        )
    base_version = int(run.input_snapshot["base_version"])
    if trip_version != base_version:
        raise ConflictError(
            "候选方案基于旧版本生成，请刷新后重新生成",
            {"candidate_version": base_version, "submitted_version": trip_version},
        )
    trip = await session.get(Trip, run.trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")

    candidate = run.candidate_output
    proposed = candidate.get("proposed_itinerary")
    if not isinstance(proposed, dict):
        raise AppError("AGENT_OUTPUT_INVALID", "候选方案缺少完整行程", status_code=502)
    old_itinerary = run.input_snapshot["itinerary"]
    scope = run.input_snapshot.get("scope")
    validate_itinerary(proposed)
    if run.run_type == "replan":
        validate_replan_candidate(
            old_itinerary,
            candidate,
            day_number=int(scope["day_index"]),
            after_time=scope.get("after_time"),
        )
    else:
        validate_revision_candidate(old_itinerary, candidate)
    expected_version = base_version
    if trip.version != base_version:
        if run.run_type == "revise":
            await bump_trip_version(
                session,
                trip_id=trip.id,
                expected_version=base_version,
                user_id=user_id,
                resource_type="activity",
                resource_id=None,
                submitted_content={"source": "ai_revise", "ai_run_id": run.id},
            )
            raise AssertionError("stale version must raise a conflict")
        later_revisions = list(
            (
                await session.scalars(
                    select(TripRevision).where(
                        TripRevision.trip_id == trip.id,
                        TripRevision.version > base_version,
                    )
                )
            ).all()
        )
        touched_days = _collect_revision_days(later_revisions)
        target_day = int(scope["day_index"])
        if touched_days is None or target_day in touched_days:
            await bump_trip_version(
                session,
                trip_id=trip.id,
                expected_version=base_version,
                user_id=user_id,
                resource_type="activity",
                resource_id=None,
                submitted_content={"source": "ai_replan", "ai_run_id": run.id},
            )
            raise AssertionError("stale version must raise a conflict")
        current_itinerary = await build_itinerary_snapshot(session, trip.id)
        candidate = _rebase_replan_candidate(candidate, current_itinerary, target_day)
        proposed = candidate["proposed_itinerary"]
        validate_itinerary(proposed)
        validate_replan_candidate(
            current_itinerary,
            candidate,
            day_number=target_day,
            after_time=scope.get("after_time"),
        )
        expected_version = trip.version

    new_version = await bump_trip_version(
        session,
        trip_id=trip.id,
        expected_version=expected_version,
        user_id=user_id,
        resource_type="activity",
        resource_id=None,
        submitted_content={"source": f"ai_{run.run_type}", "ai_run_id": run.id},
    )
    proposed["version"] = new_version
    validate_itinerary(proposed)
    await _replace_activities(session, trip, proposed)
    if run.run_type == "revise":
        _apply_changed_constraints_to_trip(trip, run.input_snapshot.get("changed_constraints", {}))
    run.candidate_output = {
        **candidate,
        "proposed_itinerary": proposed,
        "rebased_from_version": base_version if expected_version != base_version else None,
    }
    run.status = "applied"
    run.applied_at = datetime.now(UTC)
    session.add(
        TripRevision(
            trip_id=trip.id,
            user_id=user_id,
            version=new_version,
            action=run.run_type,
            resource_type="activity",
            resource_id=None,
            diff_content={
                "source": f"ai_{run.run_type}",
                "ai_run_id": run.id,
                "summary": candidate.get("summary"),
                "diff": candidate.get("diff"),
                "changed_constraints": run.input_snapshot.get("changed_constraints"),
            },
        )
    )
    await session.commit()
    return proposed, new_version


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


def _complete_replan_candidate(candidate: dict, old_itinerary: dict) -> dict:
    completed = dict(candidate)
    proposed = dict(completed.get("proposed_itinerary") or {})
    for field in (
        "schema_version",
        "trip_id",
        "version",
        "created_at",
        "updated_at",
        "city",
        "meta",
        "members",
        "permissions",
        "cost_summary",
        "revisions",
        "candidates",
    ):
        proposed.setdefault(field, old_itinerary.get(field))
    completed["proposed_itinerary"] = proposed
    return completed


def _diff_explanation_errors(mode: str, output: dict) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not isinstance(output.get("summary"), str):
        errors.append({"field": "summary", "message": "summary 必须是字符串"})
    required_lists = (
        ("by_day",) if mode == "explain" else ("my_changes", "teammate_changes", "both_changed")
    )
    for field in required_lists:
        if not isinstance(output.get(field), list):
            errors.append({"field": field, "message": f"{field} 必须是数组"})
    return errors


def _apply_changed_constraints_to_trip(trip: Trip, changed_constraints: dict) -> None:
    updated = changed_constraints.get("updated", changed_constraints)
    if not isinstance(updated, dict):
        return
    budget = updated.get("budget_total")
    if isinstance(budget, dict) and budget.get("amount") is not None:
        trip.total_budget = budget["amount"]
    elif isinstance(budget, (int, float)):
        trip.total_budget = budget
    if isinstance(updated.get("traveler_count"), int):
        trip.traveler_count = updated["traveler_count"]
    if isinstance(updated.get("preferences"), list):
        trip.preferences = {"items": updated["preferences"]}
    constraint_fields = {"pace", "party_type", "special_constraints"}
    constraint_updates = {key: updated[key] for key in constraint_fields if key in updated}
    if constraint_updates:
        trip.constraints = {**(trip.constraints or {}), **constraint_updates}


def _collect_revision_days(revisions: list[TripRevision]) -> set[int] | None:
    """返回版本推进后影响的活动天数；无法判断时返回 None，交给 409 处理。"""
    touched: set[int] = set()
    for revision in revisions:
        if revision.resource_type != "activity":
            continue
        content = revision.diff_content or {}
        direct_day = content.get("day_number")
        if isinstance(direct_day, int):
            touched.add(direct_day)
            continue
        found = False
        for key in ("before", "after"):
            value = content.get(key)
            if isinstance(value, dict) and isinstance(value.get("day_number"), int):
                touched.add(value["day_number"])
                found = True
        diff = content.get("diff")
        if isinstance(diff, dict):
            for operation in diff.get("ops", []):
                day_index = operation.get("day_index")
                if isinstance(day_index, int):
                    touched.add(day_index)
                    found = True
        if not found and direct_day is None:
            return None
    return touched


def _rebase_replan_candidate(candidate: dict, current_itinerary: dict, target_day: int) -> dict:
    rebased = deepcopy(current_itinerary)
    proposed = candidate["proposed_itinerary"]
    proposed_day = next(
        (day for day in proposed.get("days", []) if day.get("day_index") == target_day),
        None,
    )
    if proposed_day is None:
        raise AppError(
            "AGENT_OUTPUT_INVALID",
            "重排候选缺少目标日期",
            status_code=502,
            detail={"day_number": target_day},
        )
    rebased["days"] = [
        deepcopy(proposed_day) if day.get("day_index") == target_day else day
        for day in rebased.get("days", [])
    ]
    return {**candidate, "proposed_itinerary": rebased}


def _complete_system_fields(data: dict, trip: Trip) -> dict:
    completed = _normalize_generated_itinerary(deepcopy(data))
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


def _normalize_generated_itinerary(data: dict) -> dict:
    """Normalize common model aliases before strict schema validation.

    This layer only repairs shape and enum aliases. It never invents provider POI IDs,
    coordinates, weather, quoted prices, or additional itinerary decisions.
    """
    type_aliases = {
        "attraction": "poi",
        "sight": "poi",
        "sightseeing": "poi",
        "景点": "poi",
        "restaurant": "meal",
        "food": "meal",
        "dining": "meal",
        "餐饮": "meal",
        "accommodation": "hotel",
        "lodging": "hotel",
        "住宿": "hotel",
        "traffic": "transport",
        "transfer": "transport",
        "交通": "transport",
        "leisure": "free_time",
        "rest": "free_time",
        "自由活动": "free_time",
    }
    activity_seq = 0
    days = data.get("days")
    if not isinstance(days, list):
        return data
    for day_position, day in enumerate(days, start=1):
        if not isinstance(day, dict):
            continue
        day["day_index"] = day.get("day_index") or day.get("day") or day_position
        day.setdefault("transfers", [])
        activities = day.get("activities")
        if not isinstance(activities, list):
            day["activities"] = []
            continue
        for item_position, activity in enumerate(activities, start=1):
            if not isinstance(activity, dict):
                continue
            activity_seq += 1
            activity["activity_id"] = (
                activity.get("activity_id") or activity.get("id") or f"act-{activity_seq}"
            )
            location = activity.get("location")
            if isinstance(location, str):
                location = {"name": location, "poi_source": "llm"}
                activity["location"] = location
            elif not isinstance(location, dict):
                location_name = activity.get("address") or activity.get("place")
                if location_name:
                    location = {"name": str(location_name), "poi_source": "llm"}
                    activity["location"] = location
            if isinstance(location, dict):
                location.setdefault("poi_source", "llm")
            activity["title"] = str(
                activity.get("title")
                or activity.get("name")
                or (location or {}).get("name")
                or f"活动 {day_position}-{item_position}"
            )
            if isinstance(location, dict):
                location["name"] = str(location.get("name") or activity["title"])
            raw_type = str(activity.get("type") or "free_time").strip().casefold()
            activity["type"] = type_aliases.get(raw_type, raw_type)
            if activity["type"] not in TYPE_MAP:
                activity["type"] = "free_time"
            activity["time_slot"] = _normalize_time_slot(activity)
            cost = activity.get("cost")
            if isinstance(cost, (int, float)):
                activity["cost"] = _estimated_money(cost)
            elif isinstance(cost, dict):
                cost.setdefault("amount", 0)
                cost["currency"] = "CNY"
                cost["price_type"] = "estimate"
                cost["source"] = "llm"
            elif activity.get("price") is not None:
                activity["cost"] = _estimated_money(activity["price"])
            activity.setdefault("status", "planned")
            activity.setdefault("note", None)
            activity.setdefault("open_hours_hint", None)
            activity.setdefault("replaced_reason", None)

    cost_summary = data.get("cost_summary")
    if not isinstance(cost_summary, dict):
        cost_summary = {}
        data["cost_summary"] = cost_summary
    total = cost_summary.get("total_estimate", 0)
    if isinstance(total, (int, float)):
        cost_summary["total_estimate"] = _estimated_money(total)
    elif isinstance(total, dict):
        total.setdefault("amount", 0)
        total["currency"] = "CNY"
        total["price_type"] = "estimate"
        total.setdefault("source", "llm")
    else:
        cost_summary["total_estimate"] = _estimated_money(0)
    return data


def _generation_constraints(trip: Trip) -> dict:
    preferences = trip.preferences if isinstance(trip.preferences, dict) else {}
    constraints = trip.constraints if isinstance(trip.constraints, dict) else {}
    preference_items = preferences.get("items", [])
    if not isinstance(preference_items, list):
        preference_items = [str(preference_items)]
    special_constraints = constraints.get("items", [])
    if not isinstance(special_constraints, list):
        special_constraints = [str(special_constraints)]
    return {
        "city": trip.city,
        "date_start": trip.start_date.isoformat(),
        "date_end": trip.end_date.isoformat(),
        "traveler_count": trip.traveler_count or 1,
        "budget_total": {
            "amount": float(trip.total_budget or 0),
            "currency": "CNY",
            "price_type": "estimate",
            "source": "manual",
        },
        "preferences": [str(item) for item in preference_items],
        "pace": constraints.get("pace"),
        "party_type": constraints.get("party_type"),
        "special_constraints": [str(item) for item in special_constraints],
    }


async def _prequery_poi_candidates(
    *, city: str, client: AmapClient
) -> tuple[list[dict], list[dict]]:
    candidates: list[dict] = []
    warnings: list[dict] = []
    for keyword in ("热门景点", "特色餐厅"):
        try:
            result = await client.search_poi(keyword=keyword, city=city)
        except AppError as exc:
            if not exc.code.startswith("AMAP_"):
                raise
            warnings.append(
                {
                    "service": "amap",
                    "stage": "prequery",
                    "code": exc.code,
                    "message": exc.message,
                    "degraded": True,
                }
            )
            break
        for item in result.get("items", [])[:8]:
            if not item.get("name"):
                continue
            candidates.append(
                {
                    "poi_id": item.get("poi_id"),
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "address": item.get("address"),
                    "lng": item.get("longitude"),
                    "lat": item.get("latitude"),
                    "open_hours_hint": None,
                    "ticket_price_hint": None,
                }
            )
    unique: dict[str, dict] = {}
    for item in candidates:
        unique[str(item.get("poi_id") or item["name"])] = item
    return list(unique.values())[:12], warnings


def _validate_initial_generation_content(data: dict) -> None:
    empty_days = [day.get("day_index") for day in data.get("days", []) if not day.get("activities")]
    if empty_days:
        raise AppError(
            "AGENT_OUTPUT_INVALID",
            "初次生成的每天至少需要一个活动",
            status_code=502,
            detail=[
                {
                    "path": f"days.{index - 1}.activities",
                    "message": "初次生成的活动列表不能为空",
                    "code": "EMPTY_GENERATED_DAY",
                }
                for index in empty_days
                if isinstance(index, int)
            ],
        )


def _estimated_money(amount: object) -> dict:
    try:
        normalized_amount = max(float(amount), 0)
    except (TypeError, ValueError):
        normalized_amount = 0
    return {
        "amount": normalized_amount,
        "currency": "CNY",
        "price_type": "estimate",
        "source": "llm",
    }


def _normalize_time_slot(activity: dict) -> dict[str, str]:
    slot = activity.get("time_slot")
    if isinstance(slot, dict):
        start = slot.get("start") or slot.get("start_time")
        end = slot.get("end") or slot.get("end_time")
    else:
        start = activity.get("start_time")
        end = activity.get("end_time")
        raw_time = activity.get("time")
        if isinstance(raw_time, str):
            normalized = raw_time.replace("—", "-").replace("–", "-").replace("~", "-")
            parts = [part.strip() for part in normalized.split("-", maxsplit=1)]
            start = start or (parts[0] if parts else None)
            end = end or (parts[1] if len(parts) == 2 else None)
    start = _normalize_clock(start) or "09:00"
    end = _normalize_clock(end)
    if end is None or end <= start:
        start_dt = datetime.strptime(start, "%H:%M")
        end = (start_dt + timedelta(hours=1)).strftime("%H:%M")
    return {"start": start, "end": end}


def _normalize_clock(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    for pattern in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).strftime("%H:%M")
        except ValueError:
            continue
    return None


async def _replace_activities(session: AsyncSession, trip: Trip, data: dict) -> None:
    existing = list(
        (
            await session.scalars(
                select(DayActivity)
                .where(DayActivity.trip_id == trip.id)
                .order_by(DayActivity.day_number, DayActivity.order_index)
            )
        ).all()
    )
    existing_by_agent_id = {item.agent_activity_id: item for item in existing}
    trip_extra = dict(trip.extra or {})
    trip_extra["weather_by_date"] = {
        str(day.get("date")): day.get("weather") for day in data.get("days", [])
    }
    trip_extra["integration_warnings"] = data.get("integration_warnings", [])
    trip.extra = trip_extra
    # 先把现有顺序挪到临时正数区间，避免日内唯一约束与新顺序碰撞。
    for index, activity in enumerate(existing, start=1):
        activity.order_index = 100_000 + index
    if existing:
        await session.flush()

    for day in data.get("days", []):
        for index, item in enumerate(day.get("activities", []), start=1):
            slot = item.get("time_slot") or {}
            start = slot.get("start")
            end = slot.get("end")
            duration = _duration_minutes(start, end)
            location = item.get("location") or {}
            cost = item.get("cost") or {}
            quoted_cost = item.get("quoted_cost") or {}
            activity = existing_by_agent_id.pop(item["activity_id"], None)
            if activity is None:
                activity = DayActivity(
                    trip_id=trip.id,
                    agent_activity_id=item["activity_id"],
                    day_number=day["day_index"],
                    order_index=index,
                    title=item["title"],
                    type=TYPE_MAP.get(item["type"], "other"),
                )
                session.add(activity)
            activity.day_number = day["day_index"]
            activity.order_index = index
            activity.title = item["title"]
            activity.type = TYPE_MAP.get(item["type"], "other")
            activity.start_time = datetime.strptime(start, "%H:%M").time() if start else None
            activity.duration_min = duration
            activity.location_name = location.get("name")
            activity.latitude = location.get("lat")
            activity.longitude = location.get("lng")
            activity.price_estimated = cost.get("amount")
            activity.price_real = quoted_cost.get("amount")
            activity.price_source = quoted_cost.get("source") or cost.get("source", "llm")
            quoted_at = quoted_cost.get("fetched_at")
            activity.price_queried_at = datetime.fromisoformat(quoted_at) if quoted_at else None
            activity.description = item.get("note")
            activity.poi_provider = location.get("poi_source")
            activity.poi_id = location.get("poi_id")
            activity.extra = {
                "open_hours_hint": item.get("open_hours_hint"),
                "open_hours_source": item.get("open_hours_source"),
                "open_hours_fetched_at": item.get("open_hours_fetched_at"),
                "quoted_price_note": quoted_cost.get("note"),
                "status": item.get("status", "planned"),
                "replaced_reason": item.get("replaced_reason"),
            }

    for obsolete in existing_by_agent_id.values():
        await session.delete(obsolete)


def _duration_minutes(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    start_dt = datetime.strptime(start, "%H:%M")
    end_dt = datetime.strptime(end, "%H:%M")
    minutes = int((end_dt - start_dt).total_seconds() // 60)
    return minutes if minutes > 0 else None
