import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import CurrentUser, DbSession, require_trip_member, require_trip_owner
from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.db.models import Trip, TripMember, TripRevision, User
from app.schemas.common import ApiResponse
from app.schemas.member import (
    JoinTripRequest,
    MemberInvite,
    MemberRead,
    MemberRoleUpdate,
    ShareCodeRequest,
    ShareCodeResult,
)
from app.services.versioning import advance_trip_version

router = APIRouter(tags=["members"])


@router.get("/trips/{trip_id}/members", response_model=ApiResponse[list[MemberRead]])
async def list_members(
    trip_id: int, session: DbSession, current_user: CurrentUser
) -> ApiResponse[list[MemberRead]]:
    await require_trip_member(session, trip_id, current_user.id)
    members = list(
        (await session.scalars(select(TripMember).where(TripMember.trip_id == trip_id))).all()
    )
    return ApiResponse(data=[MemberRead.model_validate(member) for member in members])


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
    new_version = await advance_trip_version(
        session, trip_id=trip_id, user_id=current_user.id
    )
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
                "after": MemberRead.model_validate(member).model_dump(mode="json"),
            },
        )
    )
    await session.commit()
    await session.refresh(member)
    return ApiResponse(data=MemberRead.model_validate(member))


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
        select(TripMember).where(
            TripMember.trip_id == trip_id, TripMember.user_id == user_id
        )
    )
    if member is None:
        raise NotFoundError("成员不存在")
    before = MemberRead.model_validate(member).model_dump(mode="json")
    member.role = payload.role
    new_version = await advance_trip_version(
        session, trip_id=trip_id, user_id=current_user.id
    )
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
                "after": MemberRead.model_validate(member).model_dump(mode="json"),
            },
        )
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
        select(TripMember).where(
            TripMember.trip_id == trip_id, TripMember.user_id == user_id
        )
    )
    if member is None:
        raise NotFoundError("成员不存在")
    before = MemberRead.model_validate(member).model_dump(mode="json")
    member_id = member.id
    new_version = await advance_trip_version(
        session, trip_id=trip_id, user_id=current_user.id
    )
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
    await session.commit()
    return ApiResponse(data={"deleted": True})


@router.post("/trips/{trip_id}/members/leave", response_model=ApiResponse[dict[str, bool]])
async def leave_trip(
    trip_id: int, session: DbSession, current_user: CurrentUser
) -> ApiResponse[dict[str, bool]]:
    member = await require_trip_member(session, trip_id, current_user.id)
    if member.role == "owner":
        raise ForbiddenError("owner 不能直接退出行程")
    before = MemberRead.model_validate(member).model_dump(mode="json")
    member_id = member.id
    new_version = await advance_trip_version(
        session, trip_id=trip_id, user_id=current_user.id
    )
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
    new_version = await advance_trip_version(
        session, trip_id=trip_id, user_id=current_user.id
    )
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
    new_version = await advance_trip_version(
        session, trip_id=trip.id, user_id=current_user.id
    )
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
                "after": MemberRead.model_validate(member).model_dump(mode="json"),
            },
        )
    )
    await session.commit()
    await session.refresh(member)
    return ApiResponse(data=MemberRead.model_validate(member))
