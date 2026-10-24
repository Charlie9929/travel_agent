from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import CurrentUser, DbSession
from app.core.errors import AppError
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.schemas.auth import AuthResult, LoginRequest, RegisterRequest, UserRead
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=ApiResponse[AuthResult], status_code=201)
async def register(payload: RegisterRequest, session: DbSession) -> ApiResponse[AuthResult]:
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        nickname=payload.nickname,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError("USERNAME_EXISTS", "用户名已存在", status_code=409) from exc
    await session.refresh(user)
    token = create_access_token(str(user.id))
    return ApiResponse(data=AuthResult(token=token, user_info=UserRead.model_validate(user)))


@router.post("/login", response_model=ApiResponse[AuthResult])
async def login(payload: LoginRequest, session: DbSession) -> ApiResponse[AuthResult]:
    user = await session.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "用户名或密码错误", status_code=401)
    token = create_access_token(str(user.id))
    return ApiResponse(data=AuthResult(token=token, user_info=UserRead.model_validate(user)))


@router.get("/me", response_model=ApiResponse[UserRead])
async def me(current_user: CurrentUser) -> ApiResponse[UserRead]:
    return ApiResponse(data=UserRead.model_validate(current_user))
