from datetime import timedelta

from fastapi import APIRouter, Query
from sqlalchemy import delete, select, update

from app.api.dependencies import (
    CurrentUser,
    DbSession,
    require_trip_editor,
    require_trip_member,
    require_trip_owner,
)
from app.core.errors import ConflictError, NotFoundError
from app.db.models import DayActivity, EditConflict, Trip, TripMember, TripRevision
from app.schemas.activity import ActivityRead
from app.schemas.common import ApiResponse
from app.schemas.trip import (
    TripCreate,
    TripDayRead,
    TripDeleteRequest,
    TripDetail,
    TripList,
    TripRead,
    TripUpdate,
)

router = APIRouter(prefix="/trips", tags=["trips"])


@router.get("", response_model=ApiResponse[TripList])
async def list_trips(
    session: DbSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None, pattern=r"^(draft|ongoing|finished)$"),
) -> ApiResponse[TripList]:
    statement = (
        select(Trip)
        .join(TripMember, TripMember.trip_id == Trip.id)
        .where(TripMember.user_id == current_user.id)
        .order_by(Trip.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if status:
        statement = statement.where(Trip.status == status)
    trips = list((await session.scalars(statement)).all())
    return ApiResponse(
        data=TripList(
            items=[TripRead.model_validate(trip) for trip in trips],
            page=page,
            page_size=page_size,
        )
    )


@router.post("", response_model=ApiResponse[TripRead], status_code=201)
async def create_trip(
    payload: TripCreate, session: DbSession, current_user: CurrentUser
) -> ApiResponse[TripRead]:
    trip = Trip(**payload.model_dump(), creator_id=current_user.id, last_editor_id=current_user.id)
    session.add(trip)
    await session.flush()
    session.add(TripMember(trip_id=trip.id, user_id=current_user.id, role="owner"))
    session.add(
        TripRevision(
            trip_id=trip.id,
            user_id=current_user.id,
            version=trip.version,
            action="create",
            resource_type="trip",
            resource_id=trip.id,
            diff_content={"before": None, "after": payload.model_dump(mode="json")},
        )
    )
    await session.commit()
    await session.refresh(trip)
    return ApiResponse(data=TripRead.model_validate(trip))


@router.get("/{trip_id}", response_model=ApiResponse[TripDetail])
async def get_trip(
    trip_id: int, session: DbSession, current_user: CurrentUser
) -> ApiResponse[TripDetail]:
    await require_trip_member(session, trip_id, current_user.id)
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")
    activities = list(
        (
            await session.scalars(
                select(DayActivity)
                .where(DayActivity.trip_id == trip_id)
                .order_by(DayActivity.day_number, DayActivity.order_index)
            )
        ).all()
    )
    by_day: dict[int, list[ActivityRead]] = {}
    for activity in activities:
        by_day.setdefault(activity.day_number, []).append(ActivityRead.model_validate(activity))
    trip_data = TripRead.model_validate(trip).model_dump()
    expected_days = range(1, (trip.end_date - trip.start_date).days + 2)
    day_numbers = sorted(set(expected_days) | set(by_day))
    return ApiResponse(
        data=TripDetail(
            **trip_data,
            days=[
                TripDayRead(
                    day_number=day_number,
                    date=trip.start_date + timedelta(days=day_number - 1),
                    activities=by_day.get(day_number, []),
                )
                for day_number in day_numbers
            ],
        )
    )


@router.put("/{trip_id}", response_model=ApiResponse[TripRead])
async def update_trip(
    trip_id: int, payload: TripUpdate, session: DbSession, current_user: CurrentUser
) -> ApiResponse[TripRead]:
    await require_trip_editor(session, trip_id, current_user.id)
    values = payload.model_dump(exclude_unset=True, exclude={"version"})
    values.update(version=Trip.version + 1, last_editor_id=current_user.id)
    result = await session.execute(
        update(Trip)
        .where(Trip.id == trip_id, Trip.version == payload.version)
        .values(**values)
        .returning(Trip)
    )
    trip = result.scalar_one_or_none()
    if trip is None:
        current = await session.get(Trip, trip_id)
        if current is None:
            raise NotFoundError("行程不存在")
        session.add(
            EditConflict(
                trip_id=trip_id,
                resource_type="trip",
                resource_id=trip_id,
                submitted_by=current_user.id,
                base_version=payload.version,
                current_version=current.version,
                submitted_content=payload.model_dump(mode="json"),
                current_content=TripRead.model_validate(current).model_dump(mode="json"),
            )
        )
        await session.commit()
        raise ConflictError(
            "行程已被其他成员修改，请刷新后重试",
            {"submitted_version": payload.version, "current_version": current.version},
        )
    session.add(
        TripRevision(
            trip_id=trip.id,
            user_id=current_user.id,
            version=trip.version,
            action="update",
            resource_type="trip",
            resource_id=trip.id,
            diff_content={"submitted": payload.model_dump(mode="json", exclude={"version"})},
        )
    )
    await session.commit()
    return ApiResponse(data=TripRead.model_validate(trip))


@router.delete("/{trip_id}", response_model=ApiResponse[dict[str, bool]])
async def delete_trip(
    trip_id: int,
    payload: TripDeleteRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[dict[str, bool]]:
    await require_trip_owner(session, trip_id, current_user.id)
    result = await session.execute(
        delete(Trip).where(Trip.id == trip_id, Trip.version == payload.version).returning(Trip.id)
    )
    if result.scalar_one_or_none() is None:
        current = await session.get(Trip, trip_id)
        if current is None:
            raise NotFoundError("行程不存在")
        session.add(
            EditConflict(
                trip_id=trip_id,
                resource_type="trip",
                resource_id=trip_id,
                submitted_by=current_user.id,
                base_version=payload.version,
                current_version=current.version,
                submitted_content={"delete": True, "version": payload.version},
                current_content=TripRead.model_validate(current).model_dump(mode="json"),
            )
        )
        await session.commit()
        raise ConflictError(
            "行程版本已经变化，请刷新后重试",
            {"submitted_version": payload.version, "current_version": current.version},
        )
    await session.commit()
    return ApiResponse(data={"deleted": True})
