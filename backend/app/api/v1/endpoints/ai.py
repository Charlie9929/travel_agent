from fastapi import APIRouter
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DbSession, require_trip_editor, require_trip_member
from app.core.errors import NotFoundError
from app.db.models import AiRunLog
from app.schemas.ai import GenerateRequest
from app.schemas.common import ApiResponse
from app.services.ai_service import generate_initial_itinerary, retry_failed_ai_run

router = APIRouter(prefix="/ai", tags=["ai"])


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
