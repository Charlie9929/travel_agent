import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import CurrentUser, DbSession, require_trip_member, require_trip_owner
from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.db.models import TravelRequirement, Trip, TripMember, TripRevision, User
from app.schemas.common import ApiResponse
from app.schemas.member import (
    JoinTripRequest,
    MemberInvite,
    MemberRead,
    MemberRoleUpdate,
    ShareCodeRequest,
    ShareCodeResult,
)
from app.services.collaboration import queue_system_message
from app.services.versioning import advance_trip_version

router = APIRouter(tags=["members"])


async def _member_read(session: DbSession, member: TripMember) -> MemberRead:
    user = await session.get(User, member.user_id)
    requirement = await session.scalar(
        select(TravelRequirement).where(
            TravelRequirement.trip_id == member.trip_id,
            TravelRequirement.user_id == member.user_id,
        )
    )
    filled_by = (
        await session.get(User, requirement.filled_by)
        if requirement and requirement.filled_by
        else None
    )
    return MemberRead(
        id=member.id,
        trip_id=member.trip_id,
        user_id=member.user_id,
        role=member.role,
        joined_at=member.joined_at,
        username=user.username if user else None,
        nickname=user.nickname if user else None,
        avatar_url=user.avatar_url if user else None,
        requirement_status=requirement.status if requirement else "pending",
        requirement_filled_by=requirement.filled_by if requirement else None,
        requirement_filled_by_nickname=filled_by.nickname if filled_by else None,
    )


@router.get("/trips/{trip_id}/members", response_model=ApiResponse[list[MemberRead]])
async def list_members(
    trip_id: int, session: DbSession, current_user: CurrentUser
) -> ApiResponse[list[MemberRead]]:
    await require_trip_member(session, trip_id, current_user.id)
    members = list(
        (await session.scalars(select(TripMember).where(TripMember.trip_id == trip_id))).all()
    )
    return ApiResponse(data=[await _member_read(session, member) for member in members])


@router.post(
    "/trips/{trip_id}/members/invite", response_model=ApiResponse[MemberRead], status_code=201
)
async def invite_member(
    trip_id: int,
    payload: MemberInvite,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[MemberRead]:
    await require_trip_owner(session, trip_id, current_user.id)
    if await session.get(User, payload.user_id) is None:
        raise NotFoundError("被邀请用户不存在")
    member = TripMember(trip_id=trip_id, user_id=payload.user_id, role=payload.role)
    session.add(member)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError("MEMBER_EXISTS", "该用户已经是行程成员", status_code=409) from exc
    new_version = await advance_trip_version(session, trip_id=trip_id, user_id=current_user.id)
    session.add(
        TripRevision(
            trip_id=trip_id,
            user_id=current_user.id,
            version=new_version,
            action="create",
            resource_type="member",
            resource_id=member.id,
            diff_content={
                "before": None,
                "after": (await _member_read(session, member)).model_dump(mode="json"),
            },
        )
    )
    invited_user = await session.get(User, payload.user_id)
    queue_system_message(
        session,
        trip_id=trip_id,
        event_type="member_joined",
        content=f"{invited_user.nickname if invited_user else '新成员'} 已加入行程",
        data={"user_id": payload.user_id, "role": payload.role, "trip_version": new_version},
    )
    await session.commit()
    await session.refresh(member)
    return ApiResponse(data=await _member_read(session, member))


@router.put("/trips/{trip_id}/members/{user_id}", response_model=ApiResponse[dict[str, bool]])
async def update_member_role(
    trip_id: int,
    user_id: int,
    payload: MemberRoleUpdate,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[dict[str, bool]]:
    await require_trip_owner(session, trip_id, current_user.id)
    if user_id == current_user.id:
        raise ForbiddenError("owner 不能修改自己的角色")
    member = await session.scalar(
        select(TripMember).where(TripMember.trip_id == trip_id, TripMember.user_id == user_id)
    )
    if member is None:
        raise NotFoundError("成员不存在")
    before = (await _member_read(session, member)).model_dump(mode="json")
    member.role = payload.role
    new_version = await advance_trip_version(session, trip_id=trip_id, user_id=current_user.id)
    session.add(
        TripRevision(
            trip_id=trip_id,
            user_id=current_user.id,
            version=new_version,
            action="update",
            resource_type="member",
            resource_id=member.id,
            diff_content={
                "before": before,
                "after": (await _member_read(session, member)).model_dump(mode="json"),
            },
        )
    )
    target_user = await session.get(User, user_id)
    queue_system_message(
        session,
        trip_id=trip_id,
        event_type="member_role_changed",
        content=f"{target_user.nickname if target_user else '成员'} 的角色已调整为 {payload.role}",
        data={"user_id": user_id, "role": payload.role, "trip_version": new_version},
    )
    await session.commit()
    return ApiResponse(data={"updated": True})


@router.delete("/trips/{trip_id}/members/{user_id}", response_model=ApiResponse[dict[str, bool]])
async def remove_member(
    trip_id: int, user_id: int, session: DbSession, current_user: CurrentUser
) -> ApiResponse[dict[str, bool]]:
    await require_trip_owner(session, trip_id, current_user.id)
    if user_id == current_user.id:
        raise ForbiddenError("owner 不能移除自己")
    member = await session.scalar(
        select(TripMember).where(TripMember.trip_id == trip_id, TripMember.user_id == user_id)
    )
    if member is None:
        raise NotFoundError("成员不存在")
    before = (await _member_read(session, member)).model_dump(mode="json")
    member_id = member.id
    new_version = await advance_trip_version(session, trip_id=trip_id, user_id=current_user.id)
    await session.delete(member)
    session.add(
        TripRevision(
            trip_id=trip_id,
            user_id=current_user.id,
            version=new_version,
            action="delete",
            resource_type="member",
            resource_id=member_id,
            diff_content={"before": before, "after": None},
        )
    )
    target_user = await session.get(User, user_id)
    queue_system_message(
        session,
        trip_id=trip_id,
        event_type="member_left",
        content=f"{target_user.nickname if target_user else '成员'} 已离开行程",
        data={"user_id": user_id, "trip_version": new_version},
    )
    await session.commit()
    return ApiResponse(data={"deleted": True})


@router.post("/trips/{trip_id}/members/leave", response_model=ApiResponse[dict[str, bool]])
async def leave_trip(
    trip_id: int, session: DbSession, current_user: CurrentUser
) -> ApiResponse[dict[str, bool]]:
    member = await require_trip_member(session, trip_id, current_user.id)
    if member.role == "owner":
        raise ForbiddenError("owner 不能直接退出行程")
    before = (await _member_read(session, member)).model_dump(mode="json")
    member_id = member.id
    new_version = await advance_trip_version(session, trip_id=trip_id, user_id=current_user.id)
    await session.delete(member)
    session.add(
        TripRevision(
            trip_id=trip_id,
            user_id=current_user.id,
            version=new_version,
            action="delete",
            resource_type="member",
            resource_id=member_id,
            diff_content={"before": before, "after": None},
        )
    )
    queue_system_message(
        session,
        trip_id=trip_id,
        event_type="member_left",
        content=f"{current_user.nickname} 已离开行程",
        data={"user_id": current_user.id, "trip_version": new_version},
    )
    await session.commit()
    return ApiResponse(data={"left": True})


@router.post("/trips/{trip_id}/share-code", response_model=ApiResponse[ShareCodeResult])
async def create_share_code(
    trip_id: int,
    payload: ShareCodeRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[ShareCodeResult]:
    await require_trip_owner(session, trip_id, current_user.id)
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")
    trip.share_code = secrets.token_urlsafe(18)[:32]
    trip.share_code_expires_at = datetime.now(UTC) + timedelta(hours=payload.expires_in_hours)
    new_version = await advance_trip_version(session, trip_id=trip_id, user_id=current_user.id)
    session.add(
        TripRevision(
            trip_id=trip_id,
            user_id=current_user.id,
            version=new_version,
            action="update",
            resource_type="trip",
            resource_id=trip_id,
            diff_content={
                "share_code": "regenerated",
                "expires_at": trip.share_code_expires_at.isoformat(),
            },
        )
    )
    await session.commit()
    return ApiResponse(
        data=ShareCodeResult(share_code=trip.share_code, expires_at=trip.share_code_expires_at)
    )


@router.get("/trips/share/{share_code}", response_model=ApiResponse[dict])
async def lookup_share_code(share_code: str, session: DbSession) -> ApiResponse[dict]:
    trip = await session.scalar(select(Trip).where(Trip.share_code == share_code))
    if trip is None:
        raise NotFoundError("分享码不存在")
    if trip.share_code_expires_at is None or trip.share_code_expires_at <= datetime.now(UTC):
        raise AppError("SHARE_CODE_EXPIRED", "分享码已过期", status_code=410)
    return ApiResponse(
        data={
            "trip_id": trip.id,
            "title": trip.title,
            "city": trip.city,
            "start_date": trip.start_date,
            "end_date": trip.end_date,
            "expires_at": trip.share_code_expires_at,
        }
    )


@router.post("/trips/join", response_model=ApiResponse[MemberRead], status_code=201)
async def join_trip(
    payload: JoinTripRequest, session: DbSession, current_user: CurrentUser
) -> ApiResponse[MemberRead]:
    trip = await session.scalar(select(Trip).where(Trip.share_code == payload.share_code))
    if trip is None:
        raise NotFoundError("分享码不存在")
    if trip.share_code_expires_at is None or trip.share_code_expires_at <= datetime.now(UTC):
        raise AppError("SHARE_CODE_EXPIRED", "分享码已过期", status_code=410)
    member = TripMember(trip_id=trip.id, user_id=current_user.id, role="editor")
    session.add(member)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError("MEMBER_EXISTS", "你已经加入该行程", status_code=409) from exc
    new_version = await advance_trip_version(session, trip_id=trip.id, user_id=current_user.id)
    session.add(
        TripRevision(
            trip_id=trip.id,
            user_id=current_user.id,
            version=new_version,
            action="create",
            resource_type="member",
            resource_id=member.id,
            diff_content={
                "before": None,
                "after": (await _member_read(session, member)).model_dump(mode="json"),
            },
        )
    )
    queue_system_message(
        session,
        trip_id=trip.id,
        event_type="member_joined",
        content=f"{current_user.nickname} 通过分享码加入了行程",
        data={"user_id": current_user.id, "role": "editor", "trip_version": new_version},
    )
    await session.commit()
    await session.refresh(member)
    return ApiResponse(data=await _member_read(session, member))
