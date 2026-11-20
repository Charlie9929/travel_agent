from datetime import time
from uuid import uuid4

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.dependencies import (
    CurrentUser,
    DbSession,
    require_active_trip_editor,
    require_trip_member,
)
from app.api.v1.endpoints.map import get_amap_client
from app.core.errors import AppError, NotFoundError
from app.db.models import DayActivity, Trip, TripRevision
from app.schemas.activity import (
    ActivityCreate,
    ActivityDeleteRequest,
    ActivityRead,
    ActivityReorderRequest,
    ActivityUpdate,
)
from app.schemas.common import ApiResponse
from app.services.collaboration import queue_system_message
from app.services.poi_enrichment import poi_unavailable_reason, resolve_activity_poi
from app.services.versioning import bump_trip_version

router = APIRouter(prefix="/trips/{trip_id}/activities", tags=["activities"])

DEFAULT_ACTIVITY_GAP_MINUTES = 30


def _activity_anchors(
    activities: list[DayActivity], *, excluding_id: int | None = None
) -> list[tuple[float, float]]:
    return [
        (float(activity.longitude), float(activity.latitude))
        for activity in activities
        if activity.id != excluding_id
        and activity.longitude is not None
        and activity.latitude is not None
    ]


async def _resolve_location_values(
    *,
    location_name: str,
    city: str,
    activity_type: str,
    anchors: list[tuple[float, float]],
) -> dict:
    poi = await resolve_activity_poi(
        location_name=location_name,
        city=city,
        client=get_amap_client(),
        anchors=anchors,
        expected_type=activity_type,
    )
    if poi is None or poi.get("longitude") is None or poi.get("latitude") is None:
        raise AppError(
            "POI_MATCH_UNCERTAIN",
            f"没有在{city}找到与“{location_name}”可靠匹配的地点，请填写更完整的正式名称或分店名",
            status_code=422,
        )
    unavailable_reason = poi_unavailable_reason(poi)
    if unavailable_reason:
        raise AppError(
            "POI_UNAVAILABLE",
            f"“{poi.get('name') or location_name}”已标记为{unavailable_reason}，请更换活动地点",
            status_code=422,
        )
    return {
        "location_name": poi.get("name") or location_name,
        "longitude": poi["longitude"],
        "latitude": poi["latitude"],
        "poi_provider": "amap",
        "poi_id": poi.get("poi_id"),
    }


def _start_minutes(activity: DayActivity) -> int | None:
    if activity.start_time is None:
        return None
    return activity.start_time.hour * 60 + activity.start_time.minute


def _recommended_route_minutes(routes: dict) -> int | None:
    walking = routes.get("walk") or {}
    if walking.get("available") and (walking.get("distance_m") or 10**9) <= 1600:
        return walking.get("duration_min")
    cycling = routes.get("bike") or {}
    if cycling.get("available") and (cycling.get("distance_m") or 10**9) <= 6000:
        return cycling.get("duration_min")
    durations = [
        route.get("duration_min")
        for route in routes.values()
        if route.get("available") and isinstance(route.get("duration_min"), int)
    ]
    return min(durations) if durations else None


async def _cascade_activity_times(
    *,
    trip: Trip,
    activity: DayActivity,
    day_activities: list[DayActivity],
    old_start: int | None,
    old_duration: int | None,
    location_changed: bool,
) -> dict[int, dict[str, str | None]]:
    new_start = _start_minutes(activity)
    if new_start is None:
        return {}
    following = sorted(
        (
            item
            for item in day_activities
            if item.id != activity.id and item.order_index > activity.order_index
        ),
        key=lambda item: item.order_index,
    )
    if not following:
        return {}
    timeline_changed = old_start != new_start or old_duration != activity.duration_min
    if not timeline_changed and not location_changed:
        return {}

    original_starts = {item.id: _start_minutes(item) for item in day_activities}
    original_durations = {item.id: item.duration_min or 60 for item in day_activities}
    previous_old_end = (
        old_start + (old_duration or 60) if old_start is not None else None
    )
    previous_new_end = new_start + (activity.duration_min or 60)
    changes: dict[int, dict[str, str | None]] = {}
    for index, current in enumerate(following):
        current_old_start = original_starts[current.id]
        if index == 0 and location_changed:
            route_minutes = None
            if all(
                value is not None
                for value in (
                    activity.longitude,
                    activity.latitude,
                    current.longitude,
                    current.latitude,
                )
            ):
                route_result = await get_amap_client().routes(
                    from_lng=float(activity.longitude),
                    from_lat=float(activity.latitude),
                    to_lng=float(current.longitude),
                    to_lat=float(current.latitude),
                    city_code=trip.city_adcode,
                )
                route_minutes = _recommended_route_minutes(route_result.get("routes") or {})
            gap = (
                route_minutes + 15
                if route_minutes is not None
                else DEFAULT_ACTIVITY_GAP_MINUTES
            )
        elif current_old_start is not None and previous_old_end is not None:
            gap = max(current_old_start - previous_old_end, 0)
        else:
            gap = DEFAULT_ACTIVITY_GAP_MINUTES

        next_start = previous_new_end + gap
        next_end = next_start + (current.duration_min or 60)
        if next_start < 0 or next_end > 24 * 60:
            raise AppError(
                "DAY_SCHEDULE_OVERFLOW",
                "修改后的后续活动超出当天时间，请缩短活动或调整顺序",
                status_code=422,
            )
        before = current.start_time.strftime("%H:%M") if current.start_time else None
        current.start_time = time(hour=next_start // 60, minute=next_start % 60)
        changes[current.id] = {
            "before": before,
            "after": current.start_time.strftime("%H:%M"),
        }
        previous_old_start = original_starts[current.id]
        previous_old_end = (
            previous_old_start + original_durations[current.id]
            if previous_old_start is not None
            else None
        )
        previous_new_end = next_end
    return changes


def _reschedule_reordered_activities(
    activities: list[DayActivity], id_order: list[int]
) -> tuple[dict[int, str | None], dict[int, str]]:
    original = sorted(activities, key=lambda item: item.order_index)
    known_starts = [
        value
        for activity in original
        if (value := _start_minutes(activity)) is not None
    ]
    cursor = min(known_starts, default=9 * 60)
    gaps: list[int] = []
    for current, following in zip(original, original[1:], strict=False):
        current_start = _start_minutes(current)
        following_start = _start_minutes(following)
        if current_start is None or following_start is None:
            gaps.append(DEFAULT_ACTIVITY_GAP_MINUTES)
            continue
        current_end = current_start + (current.duration_min or 60)
        gaps.append(max(following_start - current_end, 0))

    by_id = {activity.id: activity for activity in activities}
    before = {
        activity.id: activity.start_time.strftime("%H:%M") if activity.start_time else None
        for activity in activities
    }
    after: dict[int, str] = {}
    for position, activity_id in enumerate(id_order):
        activity = by_id[activity_id]
        duration = activity.duration_min or 60
        if cursor + duration > 24 * 60:
            raise AppError(
                "DAY_SCHEDULE_OVERFLOW",
                "调整顺序后当天活动超出午夜，请缩短活动时长或减少活动",
                status_code=422,
            )
        activity.start_time = time(hour=cursor // 60, minute=cursor % 60)
        after[activity.id] = activity.start_time.strftime("%H:%M")
        cursor += duration
        if position < len(id_order) - 1:
            cursor += gaps[position] if position < len(gaps) else DEFAULT_ACTIVITY_GAP_MINUTES
    return before, after


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
    await require_active_trip_editor(session, trip_id, current_user.id)
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")
    values = payload.model_dump(exclude={"trip_version"})
    desired_order = values["order_index"]
    day_activities = list(
        (
            await session.scalars(
                select(DayActivity)
                .where(
                    DayActivity.trip_id == trip_id,
                    DayActivity.day_number == payload.day_number,
                )
                .order_by(DayActivity.order_index)
            )
        ).all()
    )
    maximum_insert_order = len(day_activities) + 1
    if desired_order > maximum_insert_order:
        raise AppError(
            "INVALID_ACTIVITY_ORDER",
            f"新活动序号不能超过 {maximum_insert_order}",
            status_code=422,
        )
    if location_name := str(values.get("location_name") or "").strip():
        values.update(
            await _resolve_location_values(
                location_name=location_name,
                city=trip.city,
                activity_type=values["type"],
                anchors=_activity_anchors(day_activities),
            )
        )
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
    affected = [activity for activity in day_activities if activity.order_index >= desired_order]
    if affected:
        original_orders = {activity.id: activity.order_index for activity in affected}
        temporary_start = (
            max(activity.order_index for activity in day_activities) + len(affected) + 1
        )
        for offset, existing in enumerate(affected):
            existing.order_index = temporary_start + offset
        await session.flush()
        for existing in affected:
            existing.order_index = original_orders[existing.id] + 1
        await session.flush()
    values["agent_activity_id"] = values.get("agent_activity_id") or f"act-{uuid4().hex[:12]}"
    activity = DayActivity(trip_id=trip_id, **values)
    session.add(activity)
    await session.flush()
    created = ActivityRead.model_validate(activity).model_dump(mode="json")
    session.add(
        TripRevision(
            trip_id=trip_id,
            user_id=current_user.id,
            version=new_version,
            action="create",
            resource_type="activity",
            resource_id=activity.id,
            diff_content={"before": None, "after": created},
        )
    )
    queue_system_message(
        session,
        trip_id=trip_id,
        event_type="itinerary_changed",
        content=f"{current_user.nickname} 新增了行程活动“{activity.title}”",
        data={"action": "create", "activity_id": activity.id, "trip_version": new_version},
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
    await require_active_trip_editor(session, trip_id, current_user.id)
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")
    activity = await session.scalar(
        select(DayActivity).where(DayActivity.id == activity_id, DayActivity.trip_id == trip_id)
    )
    if activity is None:
        raise NotFoundError("活动不存在")
    before = ActivityRead.model_validate(activity).model_dump(mode="json")
    old_start = _start_minutes(activity)
    old_duration = activity.duration_min
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
    changes = payload.model_dump(exclude_unset=True, exclude={"trip_version"})
    location_changed = (
        "location_name" in changes and changes["location_name"] != activity.location_name
    )
    needs_location_resolution = bool(
        (location_changed and changes.get("location_name"))
        or (
            not location_changed
            and activity.location_name
            and (activity.latitude is None or activity.longitude is None or not activity.poi_id)
        )
    )
    if needs_location_resolution:
        target_day = changes.get("day_number", activity.day_number)
        day_activities = list(
            (
                await session.scalars(
                    select(DayActivity).where(
                        DayActivity.trip_id == trip_id,
                        DayActivity.day_number == target_day,
                    )
                )
            ).all()
        )
        changes.update(
            await _resolve_location_values(
                location_name=str(changes.get("location_name") or activity.location_name),
                city=trip.city,
                activity_type=str(changes.get("type") or activity.type),
                anchors=_activity_anchors(day_activities, excluding_id=activity.id),
            )
        )
    elif location_changed:
        changes.update(
            latitude=None,
            longitude=None,
            poi_provider=None,
            poi_id=None,
        )
    for field, value in changes.items():
        setattr(activity, field, value)
    await session.flush()
    updated_day_activities = list(
        (
            await session.scalars(
                select(DayActivity)
                .where(
                    DayActivity.trip_id == trip_id,
                    DayActivity.day_number == activity.day_number,
                )
                .order_by(DayActivity.order_index)
            )
        ).all()
    )
    cascaded_times = await _cascade_activity_times(
        trip=trip,
        activity=activity,
        day_activities=updated_day_activities,
        old_start=old_start,
        old_duration=old_duration,
        location_changed=location_changed,
    )
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
            diff_content={
                "before": before,
                "after": after,
                "cascaded_start_times": cascaded_times,
            },
        )
    )
    queue_system_message(
        session,
        trip_id=trip_id,
        event_type="itinerary_changed",
        content=f"{current_user.nickname} 调整了行程活动“{activity.title}”",
        data={"action": "update", "activity_id": activity.id, "trip_version": new_version},
    )
    await session.commit()
    return ApiResponse(
        data={
            "activity": after,
            "trip_version": new_version,
            "cascaded_start_times": cascaded_times,
        }
    )


@router.delete("/{activity_id:int}", response_model=ApiResponse[dict])
async def delete_activity(
    trip_id: int,
    activity_id: int,
    payload: ActivityDeleteRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[dict]:
    await require_active_trip_editor(session, trip_id, current_user.id)
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
    queue_system_message(
        session,
        trip_id=trip_id,
        event_type="itinerary_changed",
        content=f"{current_user.nickname} 删除了行程活动“{before['title']}”",
        data={"action": "delete", "activity_id": activity_id, "trip_version": new_version},
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
    await require_active_trip_editor(session, trip_id, current_user.id)
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
    previous_times, updated_times = _reschedule_reordered_activities(
        activities, payload.id_order
    )
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
                "start_times_before": previous_times,
                "start_times_after": updated_times,
            },
        )
    )
    queue_system_message(
        session,
        trip_id=trip_id,
        event_type="itinerary_changed",
        content=f"{current_user.nickname} 调整了第 {payload.day_number} 天的活动顺序和时间",
        data={"action": "reorder", "day_number": payload.day_number, "trip_version": new_version},
    )
    await session.commit()
    return ApiResponse(
        data={"trip_version": new_version, "start_times": updated_times}
    )
