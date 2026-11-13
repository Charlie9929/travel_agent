import json
from uuid import uuid4

from fastapi import APIRouter
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DbSession, require_trip_editor, require_trip_member
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.db.models import AiRunLog, Trip
from app.schemas.ai import (
    ApplyAiRunRequest,
    ClarifyPreferencesRequest,
    ExplainDiffRequest,
    GenerateRequest,
    ImportGuideRequest,
    ReplanRequest,
    ReviseRequest,
)
from app.schemas.common import ApiResponse
from app.services.ai_service import (
    apply_ai_candidate,
    generate_diff_explanation,
    generate_initial_itinerary,
    generate_replan_candidate,
    generate_revision_candidate,
    get_llm_client,
    retry_failed_ai_run,
)
from app.services.collaboration import (
    candidate_presentation,
    queue_system_message,
    record_agent_event,
    record_agent_workflow,
)
from app.services.guide_import_service import apply_guide_candidates, generate_guide_candidates

router = APIRouter(prefix="/ai", tags=["ai"])
trip_ai_router = APIRouter(prefix="/trips/{trip_id}/ai-runs", tags=["ai"])


@router.post("/clarify-preferences", response_model=ApiResponse[dict])
async def clarify_preferences(
    payload: ClarifyPreferencesRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[dict]:
    await require_trip_editor(session, payload.trip_id, current_user.id)
    trip = await session.get(Trip, payload.trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")
    input_data = {
        "trip": {
            "origin_city": trip.origin_city,
            "city": trip.city,
            "start_date": trip.start_date,
            "end_date": trip.end_date,
            "traveler_count": trip.traveler_count,
            "budget": float(trip.total_budget) if trip.total_budget is not None else None,
            "preferences": trip.preferences,
            "constraints": trip.constraints,
        },
        "conversation_summary": payload.conversation_summary,
        "latest_user_message": payload.user_message,
    }
    settings = get_settings()
    result = await get_llm_client().generate_json(
        system_prompt=(
            "你是多人旅行助手的偏好理解模块。提取用户明确提供的偏好和限制，不能臆测。"
            "必须返回 JSON：ready(boolean)、questions(string数组，最多3个)、"
            "structured_constraints(object)、summary(string)。"
            "城市、日期、人数必须存在；预算、出发地、节奏、兴趣、饮食或行动限制若未说明，"
            "应简短追问。用户明确说不限、无要求或跳过时视为已回答。"
        ),
        user_prompt=json.dumps(input_data, ensure_ascii=False, default=str),
        schema={
            "type": "object",
            "required": ["ready", "questions", "structured_constraints", "summary"],
        },
        model=settings.deepseek_model,
        prompt_version="preference-clarify-v0.1",
        request_id=f"clarify-{payload.trip_id}-{uuid4().hex[:12]}",
        timeout_seconds=settings.deepseek_timeout_seconds,
        temperature=0.2,
    )
    data = result.parsed_data
    questions = [str(item) for item in data.get("questions", []) if str(item).strip()][:3]
    return ApiResponse(
        data={
            "ready": bool(data.get("ready")) and not questions,
            "questions": questions,
            "structured_constraints": data.get("structured_constraints")
            if isinstance(data.get("structured_constraints"), dict)
            else {},
            "summary": str(data.get("summary") or payload.user_message or ""),
        }
    )


@router.post("/generate", response_model=ApiResponse[dict])
async def generate(
    payload: GenerateRequest, session: DbSession, current_user: CurrentUser
) -> ApiResponse[dict]:
    await require_trip_editor(session, payload.trip_id, current_user.id)
    run, result, new_version = await generate_initial_itinerary(
        session=session,
        trip_id=payload.trip_id,
        user_id=current_user.id,
        additional_requirements=payload.additional_requirements,
    )
    queue_system_message(
        session,
        trip_id=payload.trip_id,
        event_type="ai_itinerary_applied",
        content=f"{current_user.nickname} 使用 Agent 生成了初始行程",
        data={"ai_run_id": run.id, "trip_version": new_version, "run_type": "generate"},
    )
    trip = await session.get(Trip, payload.trip_id)
    trip_brief = (
        f"请为「{trip.title}」生成初始行程。目的地：{trip.city}；"
        f"日期：{trip.start_date} 至 {trip.end_date}；人数：{trip.traveler_count or '待定'}；"
        f"预算：{trip.total_budget or '待定'}。"
        if trip
        else "请生成初始行程。"
    )
    if payload.additional_requirements:
        trip_brief += f"补充要求：{payload.additional_requirements}"
    await record_agent_workflow(
        session,
        trip_id=payload.trip_id,
        user_id=current_user.id,
        user_content=trip_brief,
        assistant_content="初始行程已经生成并保存。你可以在行程页查看，也可以在这里继续告诉我想调整的地方。",
        structured_data={
            "workflow": "generate",
            "ai_run_id": run.id,
            "applied": True,
            "trip_version": new_version,
        },
    )
    await session.commit()
    return ApiResponse(
        data={
            "ai_run_id": run.id,
            "status": run.status,
            "itinerary": result.parsed_data,
            "validation": {"valid": True},
            "trip_version": new_version,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "integration_warnings": result.parsed_data.get("integration_warnings", []),
        }
    )


@router.post("/replan", response_model=ApiResponse[dict])
async def replan(
    payload: ReplanRequest, session: DbSession, current_user: CurrentUser
) -> ApiResponse[dict]:
    await require_trip_editor(session, payload.trip_id, current_user.id)
    run, result = await generate_replan_candidate(
        session=session,
        trip_id=payload.trip_id,
        user_id=current_user.id,
        day_number=payload.day_number,
        adjustment_requirements=payload.adjustment_requirements,
        trip_version=payload.trip_version,
        after_time=payload.after_time.strftime("%H:%M") if payload.after_time else None,
        trigger=payload.trigger,
        candidate_replacements=payload.candidate_replacements,
    )
    candidate = result.parsed_data
    presentation = candidate_presentation(candidate)
    response_data = {
        "workflow": "replan",
        "ai_run_id": run.id,
        "candidate_itinerary": candidate["proposed_itinerary"],
        "diff": candidate["diff"],
        "summary": candidate["summary"],
        "base_version": payload.trip_version,
        "retry_count": run.retry_count,
        "requires_confirmation": True,
        **presentation,
    }
    await record_agent_workflow(
        session,
        trip_id=payload.trip_id,
        user_id=current_user.id,
        user_content=payload.adjustment_requirements,
        assistant_content=candidate["summary"],
        structured_data=response_data,
    )
    await session.commit()
    return ApiResponse(
        data={
            "ai_run_id": run.id,
            "status": run.status,
            "candidate_itinerary": candidate["proposed_itinerary"],
            "diff": candidate["diff"],
            "summary": candidate["summary"],
            "validation": {"valid": True},
            "base_version": payload.trip_version,
            "retry_count": run.retry_count,
            "model": result.model,
            "latency_ms": result.latency_ms,
            **presentation,
        }
    )


@router.post("/revise", response_model=ApiResponse[dict])
async def revise(
    payload: ReviseRequest, session: DbSession, current_user: CurrentUser
) -> ApiResponse[dict]:
    await require_trip_editor(session, payload.trip_id, current_user.id)
    run, result = await generate_revision_candidate(
        session=session,
        trip_id=payload.trip_id,
        user_id=current_user.id,
        changed_constraints=payload.changed_constraints,
        user_instruction=payload.user_instruction,
        trip_version=payload.trip_version,
    )
    candidate = result.parsed_data
    presentation = candidate_presentation(candidate)
    response_data = {
        "workflow": "revise",
        "ai_run_id": run.id,
        "candidate_itinerary": candidate["proposed_itinerary"],
        "diff": candidate["diff"],
        "summary": candidate["summary"],
        "base_version": payload.trip_version,
        "retry_count": run.retry_count,
        "requires_confirmation": True,
        **presentation,
    }
    await record_agent_workflow(
        session,
        trip_id=payload.trip_id,
        user_id=current_user.id,
        user_content=payload.user_instruction or "请根据我更新的旅行要求整体调整行程。",
        assistant_content=candidate["summary"],
        structured_data=response_data,
    )
    await session.commit()
    return ApiResponse(
        data={
            "ai_run_id": run.id,
            "status": run.status,
            "candidate_itinerary": candidate["proposed_itinerary"],
            "diff": candidate["diff"],
            "summary": candidate["summary"],
            "validation": {"valid": True},
            "base_version": payload.trip_version,
            "retry_count": run.retry_count,
            "model": result.model,
            "latency_ms": result.latency_ms,
            **presentation,
        }
    )


@router.post("/explain-diff", response_model=ApiResponse[dict])
async def explain_diff(
    payload: ExplainDiffRequest, session: DbSession, current_user: CurrentUser
) -> ApiResponse[dict]:
    await require_trip_member(session, payload.trip_id, current_user.id)
    run, result = await generate_diff_explanation(
        session=session,
        trip_id=payload.trip_id,
        user_id=current_user.id,
        mode=payload.mode,
        old_itinerary=payload.old_itinerary,
        new_itinerary=payload.new_itinerary,
        teammate_itinerary=payload.teammate_itinerary,
    )
    return ApiResponse(
        data={
            "ai_run_id": run.id,
            "status": run.status,
            "explanation": result.parsed_data,
            "retry_count": run.retry_count,
            "model": result.model,
            "latency_ms": result.latency_ms,
        }
    )


@router.post("/import-guide", response_model=ApiResponse[dict])
async def import_guide(
    payload: ImportGuideRequest, session: DbSession, current_user: CurrentUser
) -> ApiResponse[dict]:
    await require_trip_editor(session, payload.trip_id, current_user.id)
    run, result = await generate_guide_candidates(
        session=session,
        trip_id=payload.trip_id,
        user_id=current_user.id,
        text=payload.text,
    )
    return ApiResponse(
        data={
            "ai_run_id": run.id,
            "status": run.status,
            "candidates": result.parsed_data["candidates"],
            "warnings": result.parsed_data["warnings"],
            "text_truncated": bool(run.input_snapshot.get("text_truncated")),
            "retry_count": run.retry_count,
            "model": result.model,
            "latency_ms": result.latency_ms,
        }
    )


@router.get("/runs/{ai_run_id}", response_model=ApiResponse[dict])
async def get_run(
    ai_run_id: int, session: DbSession, current_user: CurrentUser
) -> ApiResponse[dict]:
    run = await session.scalar(select(AiRunLog).where(AiRunLog.id == ai_run_id))
    if run is None:
        raise NotFoundError("AI 调用记录不存在")
    await require_trip_member(session, run.trip_id, current_user.id)
    return ApiResponse(
        data={
            "id": run.id,
            "trip_id": run.trip_id,
            "run_type": run.run_type,
            "status": run.status,
            "candidate_output": run.candidate_output,
            "error_code": run.error_code,
            "retry_count": run.retry_count,
            "created_at": run.created_at,
            "applied_at": run.applied_at,
        }
    )


@router.post("/runs/{ai_run_id}/retry-apply", response_model=ApiResponse[dict])
async def retry_apply(
    ai_run_id: int, session: DbSession, current_user: CurrentUser
) -> ApiResponse[dict]:
    run = await session.scalar(select(AiRunLog).where(AiRunLog.id == ai_run_id))
    if run is None:
        raise NotFoundError("AI 调用记录不存在")
    await require_trip_editor(session, run.trip_id, current_user.id)
    itinerary, new_version = await retry_failed_ai_run(
        session=session, run=run, user_id=current_user.id
    )
    return ApiResponse(
        data={
            "ai_run_id": run.id,
            "status": run.status,
            "trip_version": new_version,
            "itinerary": itinerary,
        }
    )


@trip_ai_router.post("/{ai_run_id}/apply", response_model=ApiResponse[dict])
async def apply_ai_run(
    trip_id: int,
    ai_run_id: int,
    payload: ApplyAiRunRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[dict]:
    await require_trip_editor(session, trip_id, current_user.id)
    run = await session.scalar(
        select(AiRunLog).where(AiRunLog.id == ai_run_id, AiRunLog.trip_id == trip_id)
    )
    if run is None:
        raise NotFoundError("AI 调用记录不存在")
    if run.run_type == "import_guide":
        if payload.apply_mode != "append_selected":
            raise AppError(
                "INVALID_APPLY_MODE",
                "攻略候选必须使用 append_selected 模式",
                status_code=422,
            )
        activities, new_version = await apply_guide_candidates(
            session=session,
            run=run,
            user_id=current_user.id,
            trip_version=payload.trip_version,
            selected_candidate_ids=payload.selected_candidate_ids,
        )
        queue_system_message(
            session,
            trip_id=trip_id,
            event_type="ai_itinerary_applied",
            content=f"{current_user.nickname} 将攻略候选应用到了行程",
            data={"ai_run_id": run.id, "trip_version": new_version, "run_type": run.run_type},
        )
        await session.commit()
        return ApiResponse(
            data={
                "ai_run_id": run.id,
                "status": run.status,
                "trip_version": new_version,
                "activities": activities,
            }
        )
    if payload.apply_mode != "replace_itinerary":
        raise AppError(
            "INVALID_APPLY_MODE",
            "行程候选必须使用 replace_itinerary 模式",
            status_code=422,
        )
    itinerary, new_version = await apply_ai_candidate(
        session=session,
        run=run,
        user_id=current_user.id,
        trip_version=payload.trip_version,
    )
    queue_system_message(
        session,
        trip_id=trip_id,
        event_type="ai_itinerary_applied",
        content=f"{current_user.nickname} 确认并应用了 Agent 的行程调整",
        data={"ai_run_id": run.id, "trip_version": new_version, "run_type": run.run_type},
    )
    await record_agent_event(
        session,
        trip_id=trip_id,
        user_id=current_user.id,
        content="你已确认这版调整，新的行程已经保存。",
        structured_data={
            "workflow": run.run_type,
            "ai_run_id": run.id,
            "applied": True,
            "trip_version": new_version,
        },
    )
    await session.commit()
    return ApiResponse(
        data={
            "ai_run_id": run.id,
            "status": run.status,
            "trip_version": new_version,
            "itinerary": itinerary,
        }
    )
