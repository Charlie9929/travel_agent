from uuid import uuid4

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DbSession, require_trip_editor, require_trip_member
from app.core.errors import AppError, NotFoundError
from app.db.models import DayActivity, TripRevision
from app.schemas.activity import (
    ActivityCreate,
    ActivityDeleteRequest,
    ActivityRead,
    ActivityReorderRequest,
    ActivityUpdate,
)
from app.schemas.common import ApiResponse
from app.services.versioning import bump_trip_version

router = APIRouter(prefix="/trips/{trip_id}/activities", tags=["activities"])


@router.get("", response_model=ApiResponse[list[ActivityRead]])
async def list_activities(
    trip_id: int,
    session: DbSession,
    current_user: CurrentUser,
    day_number: int | None = Query(default=None, ge=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
) -> ApiResponse[list[ActivityRead]]:
    await require_trip_member(session, trip_id, current_user.id)
    statement = (
        select(DayActivity)
        .where(DayActivity.trip_id == trip_id)
        .order_by(DayActivity.day_number, DayActivity.order_index)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if day_number is not None:
        statement = statement.where(DayActivity.day_number == day_number)
    items = list((await session.scalars(statement)).all())
    return ApiResponse(data=[ActivityRead.model_validate(item) for item in items])


@router.post("", response_model=ApiResponse[dict], status_code=201)
async def create_activity(
    trip_id: int,
    payload: ActivityCreate,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[dict]:
    await require_trip_editor(session, trip_id, current_user.id)
    submitted = payload.model_dump(mode="json")
    new_version = await bump_trip_version(
        session,
        trip_id=trip_id,
        expected_version=payload.trip_version,
        user_id=current_user.id,
        resource_type="activity",
        resource_id=None,
        submitted_content=submitted,
    )
    values = payload.model_dump(exclude={"trip_version"})
    values["agent_activity_id"] = values.get("agent_activity_id") or f"act-{uuid4().hex[:12]}"
    activity = DayActivity(trip_id=trip_id, **values)
    session.add(activity)
    await session.flush()
    session.add(
        TripRevision(
            trip_id=trip_id,
            user_id=current_user.id,
            version=new_version,
            action="create",
            resource_type="activity",
            resource_id=activity.id,
            diff_content={"before": None, "after": submitted},
        )
    )
    await session.commit()
    await session.refresh(activity)
    return ApiResponse(
        data={
            "activity": ActivityRead.model_validate(activity).model_dump(mode="json"),
            "trip_version": new_version,
        }
    )


@router.put("/{activity_id:int}", response_model=ApiResponse[dict])
async def update_activity(
    trip_id: int,
    activity_id: int,
    payload: ActivityUpdate,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[dict]:
    await require_trip_editor(session, trip_id, current_user.id)
    activity = await session.scalar(
        select(DayActivity).where(DayActivity.id == activity_id, DayActivity.trip_id == trip_id)
    )
    if activity is None:
        raise NotFoundError("活动不存在")
    before = ActivityRead.model_validate(activity).model_dump(mode="json")
    submitted = payload.model_dump(mode="json", exclude_unset=True)
    new_version = await bump_trip_version(
        session,
        trip_id=trip_id,
        expected_version=payload.trip_version,
        user_id=current_user.id,
        resource_type="activity",
        resource_id=activity_id,
        submitted_content=submitted,
    )
    for field, value in payload.model_dump(exclude_unset=True, exclude={"trip_version"}).items():
        setattr(activity, field, value)
    await session.flush()
    await session.refresh(activity)
    after = ActivityRead.model_validate(activity).model_dump(mode="json")
    session.add(
        TripRevision(
            trip_id=trip_id,
            user_id=current_user.id,
            version=new_version,
            action="update",
            resource_type="activity",
            resource_id=activity_id,
            diff_content={"before": before, "after": after},
        )
    )
    await session.commit()
    return ApiResponse(data={"activity": after, "trip_version": new_version})


@router.delete("/{activity_id:int}", response_model=ApiResponse[dict])
async def delete_activity(
    trip_id: int,
    activity_id: int,
    payload: ActivityDeleteRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[dict]:
    await require_trip_editor(session, trip_id, current_user.id)
    activity = await session.scalar(
        select(DayActivity).where(DayActivity.id == activity_id, DayActivity.trip_id == trip_id)
    )
    if activity is None:
        raise NotFoundError("活动不存在")
    before = ActivityRead.model_validate(activity).model_dump(mode="json")
    new_version = await bump_trip_version(
        session,
        trip_id=trip_id,
        expected_version=payload.trip_version,
        user_id=current_user.id,
        resource_type="activity",
        resource_id=activity_id,
        submitted_content={"delete": True},
    )
    await session.delete(activity)
    session.add(
        TripRevision(
            trip_id=trip_id,
            user_id=current_user.id,
            version=new_version,
            action="delete",
            resource_type="activity",
            resource_id=activity_id,
            diff_content={"before": before, "after": None},
        )
    )
    await session.commit()
    return ApiResponse(data={"deleted": True, "trip_version": new_version})


@router.put("/reorder", response_model=ApiResponse[dict])
async def reorder_activities(
    trip_id: int,
    payload: ActivityReorderRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[dict]:
    await require_trip_editor(session, trip_id, current_user.id)
    activities = list(
        (
            await session.scalars(
                select(DayActivity).where(
                    DayActivity.trip_id == trip_id,
                    DayActivity.day_number == payload.day_number,
                )
            )
        ).all()
    )
    by_id = {activity.id: activity for activity in activities}
    if len(payload.id_order) != len(set(payload.id_order)) or set(payload.id_order) != set(by_id):
        raise AppError(
            "INVALID_ACTIVITY_ORDER",
            "排序列表必须恰好包含该天的全部活动，且不能重复",
            status_code=422,
        )
    previous_order = [
        activity.id for activity in sorted(activities, key=lambda item: item.order_index)
    ]
    new_version = await bump_trip_version(
        session,
        trip_id=trip_id,
        expected_version=payload.trip_version,
        user_id=current_user.id,
        resource_type="activity",
        resource_id=None,
        submitted_content=payload.model_dump(mode="json"),
    )
    # 先移到不与现有序号冲突的正数区间，再写入最终顺序。
    # 这样同时满足 order_index >= 1 和日内顺序唯一约束。
    temporary_start = max(activity.order_index for activity in activities) + len(activities) + 1
    for position, activity_id in enumerate(payload.id_order, start=1):
        by_id[activity_id].order_index = temporary_start + position
    await session.flush()
    for position, activity_id in enumerate(payload.id_order, start=1):
        by_id[activity_id].order_index = position
    session.add(
        TripRevision(
            trip_id=trip_id,
            user_id=current_user.id,
            version=new_version,
            action="reorder",
            resource_type="activity",
            resource_id=None,
            diff_content={
                "day_number": payload.day_number,
                "before": previous_order,
                "after": payload.id_order,
            },
        )
    )
    await session.commit()
    return ApiResponse(data={"trip_version": new_version})
