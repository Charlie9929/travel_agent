from fastapi import APIRouter
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DbSession, require_trip_editor, require_trip_member
from app.core.errors import AppError, NotFoundError
from app.db.models import AiRunLog
from app.schemas.ai import (
    ApplyAiRunRequest,
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
    retry_failed_ai_run,
)
from app.services.guide_import_service import apply_guide_candidates, generate_guide_candidates

router = APIRouter(prefix="/ai", tags=["ai"])
trip_ai_router = APIRouter(prefix="/trips/{trip_id}/ai-runs", tags=["ai"])


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
    return ApiResponse(
        data={
            "ai_run_id": run.id,
            "status": run.status,
            "itinerary": result.parsed_data,
            "validation": {"valid": True},
            "trip_version": new_version,
            "model": result.model,
            "latency_ms": result.latency_ms,
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
    return ApiResponse(
        data={
            "ai_run_id": run.id,
            "status": run.status,
            "trip_version": new_version,
            "itinerary": itinerary,
        }
    )
