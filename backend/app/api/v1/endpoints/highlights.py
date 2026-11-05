from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DbSession, require_trip_member
from app.core.errors import ForbiddenError, NotFoundError
from app.db.models import TripHighlight
from app.schemas.collaboration import HighlightCreate, HighlightRead, HighlightUpdate
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/trips/{trip_id}/highlights", tags=["highlights"])


async def _trip_highlight(session: DbSession, trip_id: int, highlight_id: int) -> TripHighlight:
    highlight = await session.scalar(
        select(TripHighlight).where(
            TripHighlight.id == highlight_id,
            TripHighlight.trip_id == trip_id,
        )
    )
    if highlight is None:
        raise NotFoundError("旅行高光不存在")
    return highlight


@router.get("", response_model=ApiResponse[list[HighlightRead]])
async def list_highlights(
    trip_id: int,
    session: DbSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> ApiResponse[list[HighlightRead]]:
    await require_trip_member(session, trip_id, current_user.id)
    items = list(
        (
            await session.scalars(
                select(TripHighlight)
                .where(TripHighlight.trip_id == trip_id)
                .order_by(TripHighlight.occurred_at.desc().nullslast(), TripHighlight.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return ApiResponse(data=[HighlightRead.model_validate(item) for item in items])


@router.post("", response_model=ApiResponse[HighlightRead], status_code=201)
async def create_highlight(
    trip_id: int,
    payload: HighlightCreate,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[HighlightRead]:
    await require_trip_member(session, trip_id, current_user.id)
    highlight = TripHighlight(
        trip_id=trip_id,
        created_by=current_user.id,
        **payload.model_dump(),
    )
    session.add(highlight)
    await session.commit()
    await session.refresh(highlight)
    return ApiResponse(data=HighlightRead.model_validate(highlight))


@router.put("/{highlight_id}", response_model=ApiResponse[HighlightRead])
async def update_highlight(
    trip_id: int,
    highlight_id: int,
    payload: HighlightUpdate,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[HighlightRead]:
    membership = await require_trip_member(session, trip_id, current_user.id)
    highlight = await _trip_highlight(session, trip_id, highlight_id)
    if highlight.created_by != current_user.id and membership.role != "owner":
        raise ForbiddenError("只有创建者或 owner 可以编辑该高光")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(highlight, field, value)
    await session.commit()
    await session.refresh(highlight)
    return ApiResponse(data=HighlightRead.model_validate(highlight))
