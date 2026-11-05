from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select

from app.api.dependencies import (
    CurrentUser,
    DbSession,
    require_trip_member,
    require_trip_owner,
)
from app.core.errors import NotFoundError
from app.db.models import TravelRequirement, TripMember, User
from app.schemas.collaboration import (
    RequirementRead,
    RequirementShareRequest,
    RequirementUpsert,
)
from app.schemas.common import ApiResponse
from app.services.collaboration import queue_system_message

router = APIRouter(prefix="/trips/{trip_id}/requirements", tags=["requirements"])


async def _require_target_member(session: DbSession, trip_id: int, user_id: int) -> None:
    member = await session.scalar(
        select(TripMember).where(
            TripMember.trip_id == trip_id,
            TripMember.user_id == user_id,
        )
    )
    if member is None:
        raise NotFoundError("目标用户不是行程成员")


async def _upsert_requirement(
    session: DbSession,
    *,
    trip_id: int,
    target_user_id: int,
    filled_by: int,
    payload: RequirementUpsert,
) -> TravelRequirement:
    requirement = await session.scalar(
        select(TravelRequirement).where(
            TravelRequirement.trip_id == trip_id,
            TravelRequirement.user_id == target_user_id,
        )
    )
    if requirement is None:
        requirement = TravelRequirement(trip_id=trip_id, user_id=target_user_id)
        session.add(requirement)
    requirement.content = payload.content
    requirement.status = payload.status
    requirement.filled_by = filled_by if filled_by != target_user_id else None
    await session.commit()
    await session.refresh(requirement)
    return requirement


async def _requirement_read(
    session: DbSession,
    requirement: TravelRequirement | None,
    *,
    trip_id: int,
    user: User,
    viewer_id: int,
) -> RequirementRead:
    filled_by = (
        await session.get(User, requirement.filled_by)
        if requirement and requirement.filled_by
        else None
    )
    can_view_private = user.id == viewer_id or bool(
        requirement and requirement.filled_by == viewer_id
    )
    return RequirementRead(
        id=requirement.id if requirement else 0,
        trip_id=trip_id,
        user_id=user.id,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        content=requirement.content if requirement and can_view_private else None,
        status=requirement.status if requirement else "pending",
        filled_by=requirement.filled_by if requirement else None,
        filled_by_nickname=filled_by.nickname if filled_by else None,
        shared_summary=requirement.shared_summary if requirement else None,
        shared_at=requirement.shared_at if requirement else None,
        can_view_private=can_view_private,
        updated_at=(requirement.updated_at if requirement else user.updated_at),
    )


@router.get("", response_model=ApiResponse[list[RequirementRead]])
async def list_requirements(
    trip_id: int, session: DbSession, current_user: CurrentUser
) -> ApiResponse[list[RequirementRead]]:
    await require_trip_member(session, trip_id, current_user.id)
    rows = (
        await session.execute(
            select(TripMember, User, TravelRequirement)
            .join(User, User.id == TripMember.user_id)
            .outerjoin(
                TravelRequirement,
                (TravelRequirement.trip_id == TripMember.trip_id)
                & (TravelRequirement.user_id == TripMember.user_id),
            )
            .where(TripMember.trip_id == trip_id)
            .order_by(TripMember.joined_at)
        )
    ).all()
    return ApiResponse(
        data=[
            await _requirement_read(
                session,
                requirement,
                trip_id=trip_id,
                user=user,
                viewer_id=current_user.id,
            )
            for _, user, requirement in rows
        ]
    )


@router.put("/me", response_model=ApiResponse[RequirementRead])
async def save_my_requirement(
    trip_id: int,
    payload: RequirementUpsert,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[RequirementRead]:
    await require_trip_member(session, trip_id, current_user.id)
    requirement = await _upsert_requirement(
        session,
        trip_id=trip_id,
        target_user_id=current_user.id,
        filled_by=current_user.id,
        payload=payload,
    )
    return ApiResponse(
        data=await _requirement_read(
            session,
            requirement,
            trip_id=trip_id,
            user=current_user,
            viewer_id=current_user.id,
        )
    )


@router.put("/{user_id:int}", response_model=ApiResponse[RequirementRead])
async def save_requirement_for_member(
    trip_id: int,
    user_id: int,
    payload: RequirementUpsert,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[RequirementRead]:
    await require_trip_owner(session, trip_id, current_user.id)
    await _require_target_member(session, trip_id, user_id)
    target_user = await session.get(User, user_id)
    if target_user is None:
        raise NotFoundError("用户不存在")
    requirement = await _upsert_requirement(
        session,
        trip_id=trip_id,
        target_user_id=user_id,
        filled_by=current_user.id,
        payload=payload,
    )
    return ApiResponse(
        data=await _requirement_read(
            session,
            requirement,
            trip_id=trip_id,
            user=target_user,
            viewer_id=current_user.id,
        )
    )


@router.post("/me/share", response_model=ApiResponse[RequirementRead])
async def share_my_requirement(
    trip_id: int,
    payload: RequirementShareRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[RequirementRead]:
    await require_trip_member(session, trip_id, current_user.id)
    requirement = await session.scalar(
        select(TravelRequirement).where(
            TravelRequirement.trip_id == trip_id,
            TravelRequirement.user_id == current_user.id,
        )
    )
    if requirement is None:
        raise NotFoundError("请先填写旅行需求")
    requirement.shared_summary = payload.summary
    requirement.shared_at = datetime.now(UTC)
    queue_system_message(
        session,
        trip_id=trip_id,
        event_type="requirement_shared",
        content=f"{current_user.nickname} 分享了旅行需求摘要",
        data={"user_id": current_user.id},
    )
    await session.commit()
    await session.refresh(requirement)
    return ApiResponse(
        data=await _requirement_read(
            session,
            requirement,
            trip_id=trip_id,
            user=current_user,
            viewer_id=current_user.id,
        )
    )


@router.delete("/me/share", response_model=ApiResponse[dict[str, bool]])
async def revoke_my_requirement_share(
    trip_id: int, session: DbSession, current_user: CurrentUser
) -> ApiResponse[dict[str, bool]]:
    await require_trip_member(session, trip_id, current_user.id)
    requirement = await session.scalar(
        select(TravelRequirement).where(
            TravelRequirement.trip_id == trip_id,
            TravelRequirement.user_id == current_user.id,
        )
    )
    if requirement is None:
        raise NotFoundError("旅行需求不存在")
    requirement.shared_summary = None
    requirement.shared_at = None
    await session.commit()
    return ApiResponse(data={"revoked": True})
