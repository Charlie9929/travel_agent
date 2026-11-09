from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.api.dependencies import CurrentUser, DbSession, require_trip_owner
from app.db.models import TripMember, User
from app.schemas.auth import UserRead
from app.schemas.collaboration import (
    ProfileUpdate,
    UserSearchRead,
    UserSettingsRead,
    UserSettingsUpdate,
)
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search", response_model=ApiResponse[list[UserSearchRead]])
async def search_users(
    session: DbSession,
    current_user: CurrentUser,
    q: str = Query(min_length=1, max_length=50),
    trip_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
) -> ApiResponse[list[UserSearchRead]]:
    member_ids: set[int] = set()
    if trip_id is not None:
        await require_trip_owner(session, trip_id, current_user.id)
        member_ids = set(
            (
                await session.scalars(
                    select(TripMember.user_id).where(TripMember.trip_id == trip_id)
                )
            ).all()
        )
    pattern = f"%{q.strip()}%"
    users = list(
        (
            await session.scalars(
                select(User)
                .where(or_(User.username.ilike(pattern), User.nickname.ilike(pattern)))
                .order_by(User.nickname, User.id)
                .limit(limit)
            )
        ).all()
    )
    return ApiResponse(
        data=[
            UserSearchRead(
                id=user.id,
                username=user.username,
                nickname=user.nickname,
                avatar_url=user.avatar_url,
                is_member=user.id in member_ids,
                can_invite=trip_id is None or user.id not in member_ids,
            )
            for user in users
        ]
    )


@router.put("/me/profile", response_model=ApiResponse[UserRead])
async def update_profile(
    payload: ProfileUpdate, session: DbSession, current_user: CurrentUser
) -> ApiResponse[UserRead]:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    await session.commit()
    await session.refresh(current_user)
    return ApiResponse(data=UserRead.model_validate(current_user))


def _settings(user: User) -> UserSettingsRead:
    extra = user.extra or {}
    return UserSettingsRead(
        agent_preferences=extra.get("agent_preferences", {}),
        memory_enabled=bool(extra.get("memory_enabled", True)),
    )


@router.get("/me/settings", response_model=ApiResponse[UserSettingsRead])
async def get_user_settings(current_user: CurrentUser) -> ApiResponse[UserSettingsRead]:
    return ApiResponse(data=_settings(current_user))


@router.put("/me/settings", response_model=ApiResponse[UserSettingsRead])
async def update_user_settings(
    payload: UserSettingsUpdate, session: DbSession, current_user: CurrentUser
) -> ApiResponse[UserSettingsRead]:
    extra = dict(current_user.extra or {})
    for field, value in payload.model_dump(exclude_unset=True).items():
        extra[field] = value
    current_user.extra = extra
    await session.commit()
    await session.refresh(current_user)
    return ApiResponse(data=_settings(current_user))
