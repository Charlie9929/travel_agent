from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DbSession
from app.core.errors import NotFoundError
from app.db.models import UserMemory
from app.schemas.collaboration import MemoryCreate, MemoryRead, MemoryUpdate
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/memories", tags=["memories"])


async def _owned_memory(session: DbSession, memory_id: int, user_id: int) -> UserMemory:
    memory = await session.scalar(
        select(UserMemory).where(UserMemory.id == memory_id, UserMemory.user_id == user_id)
    )
    if memory is None:
        raise NotFoundError("记忆不存在")
    return memory


@router.get("", response_model=ApiResponse[list[MemoryRead]])
async def list_memories(
    session: DbSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> ApiResponse[list[MemoryRead]]:
    items = list(
        (
            await session.scalars(
                select(UserMemory)
                .where(UserMemory.user_id == current_user.id)
                .order_by(UserMemory.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return ApiResponse(data=[MemoryRead.model_validate(item) for item in items])


@router.post("", response_model=ApiResponse[MemoryRead], status_code=201)
async def create_memory(
    payload: MemoryCreate, session: DbSession, current_user: CurrentUser
) -> ApiResponse[MemoryRead]:
    memory = UserMemory(user_id=current_user.id, **payload.model_dump())
    session.add(memory)
    await session.commit()
    await session.refresh(memory)
    return ApiResponse(data=MemoryRead.model_validate(memory))


@router.get("/{memory_id}", response_model=ApiResponse[MemoryRead])
async def get_memory(
    memory_id: int, session: DbSession, current_user: CurrentUser
) -> ApiResponse[MemoryRead]:
    return ApiResponse(
        data=MemoryRead.model_validate(await _owned_memory(session, memory_id, current_user.id))
    )


@router.put("/{memory_id}", response_model=ApiResponse[MemoryRead])
async def update_memory(
    memory_id: int,
    payload: MemoryUpdate,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[MemoryRead]:
    memory = await _owned_memory(session, memory_id, current_user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(memory, field, value)
    await session.commit()
    await session.refresh(memory)
    return ApiResponse(data=MemoryRead.model_validate(memory))


@router.delete("/{memory_id}", response_model=ApiResponse[dict[str, bool]])
async def delete_memory(
    memory_id: int, session: DbSession, current_user: CurrentUser
) -> ApiResponse[dict[str, bool]]:
    memory = await _owned_memory(session, memory_id, current_user.id)
    await session.delete(memory)
    await session.commit()
    return ApiResponse(data={"deleted": True})
