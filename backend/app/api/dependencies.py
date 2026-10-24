from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.core.security import decode_access_token
from app.db.models import TripMember, User
from app.db.session import get_db_session

bearer_scheme = HTTPBearer(auto_error=False)
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise AppError("UNAUTHORIZED", "请先登录", status_code=401)
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise AppError("UNAUTHORIZED", "登录凭证无效或已过期", status_code=401) from exc
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("UNAUTHORIZED", "用户不存在", status_code=401)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_membership(session: AsyncSession, trip_id: int, user_id: int) -> TripMember:
    membership = await session.scalar(
        select(TripMember).where(TripMember.trip_id == trip_id, TripMember.user_id == user_id)
    )
    if membership is None:
        raise NotFoundError("行程不存在或你尚未加入")
    return membership


async def require_trip_member(session: AsyncSession, trip_id: int, user_id: int) -> TripMember:
    return await get_membership(session, trip_id, user_id)


async def require_trip_editor(session: AsyncSession, trip_id: int, user_id: int) -> TripMember:
    membership = await get_membership(session, trip_id, user_id)
    if membership.role not in {"owner", "editor"}:
        raise ForbiddenError("当前成员只有查看权限")
    return membership


async def require_trip_owner(session: AsyncSession, trip_id: int, user_id: int) -> TripMember:
    membership = await get_membership(session, trip_id, user_id)
    if membership.role != "owner":
        raise ForbiddenError("只有行程创建者可以执行该操作")
    return membership
