from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from sqlalchemy import or_, select

from app.api.dependencies import CurrentUser, DbSession, require_trip_owner
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.db.models import TripMember, User
from app.schemas.auth import PasswordChangeRequest, UserRead
from app.schemas.collaboration import (
    ProfileUpdate,
    UserSearchRead,
    UserSettingsRead,
    UserSettingsUpdate,
)
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/users", tags=["users"])

MAX_AVATAR_BYTES = 5 * 1024 * 1024
ALLOWED_AVATAR_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _upload_root() -> Path:
    root = Path(get_settings().upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _local_avatar_path(avatar_url: str | None) -> Path | None:
    prefix = "/uploads/"
    if not avatar_url or not avatar_url.startswith(prefix):
        return None
    candidate = (_upload_root() / avatar_url.removeprefix(prefix)).resolve()
    avatars_root = (_upload_root() / "avatars").resolve()
    if candidate == avatars_root or avatars_root not in candidate.parents:
        return None
    return candidate


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


@router.post("/me/avatar", response_model=ApiResponse[UserRead])
async def upload_avatar(
    request: Request, session: DbSession, current_user: CurrentUser
) -> ApiResponse[UserRead]:
    mime_type = (request.headers.get("content-type") or "").split(";", maxsplit=1)[0].lower()
    extension = ALLOWED_AVATAR_TYPES.get(mime_type)
    if extension is None:
        raise AppError(
            "UNSUPPORTED_AVATAR_TYPE",
            "头像仅支持 JPEG、PNG 和 WebP 图片",
            status_code=415,
        )
    body = await request.body()
    if not body:
        raise AppError("EMPTY_AVATAR", "头像内容不能为空", status_code=422)
    if len(body) > MAX_AVATAR_BYTES:
        raise AppError("AVATAR_TOO_LARGE", "头像不能超过 5MB", status_code=413)

    relative_dir = Path("avatars") / f"user-{current_user.id}"
    absolute_dir = _upload_root() / relative_dir
    absolute_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    new_path = absolute_dir / filename
    new_path.write_bytes(body)
    old_path = _local_avatar_path(current_user.avatar_url)
    current_user.avatar_url = f"/uploads/{(relative_dir / filename).as_posix()}"
    try:
        await session.commit()
        await session.refresh(current_user)
    except Exception:
        new_path.unlink(missing_ok=True)
        raise
    if old_path and old_path != new_path:
        old_path.unlink(missing_ok=True)
    return ApiResponse(data=UserRead.model_validate(current_user))


@router.put("/me/password", response_model=ApiResponse[dict[str, bool]])
async def change_password(
    payload: PasswordChangeRequest, session: DbSession, current_user: CurrentUser
) -> ApiResponse[dict[str, bool]]:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise AppError("INVALID_CURRENT_PASSWORD", "当前密码不正确", status_code=422)
    if verify_password(payload.new_password, current_user.password_hash):
        raise AppError("PASSWORD_UNCHANGED", "新密码不能与当前密码相同", status_code=422)
    current_user.password_hash = hash_password(payload.new_password)
    current_user.token_version += 1
    await session.commit()
    return ApiResponse(data={"changed": True})


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
