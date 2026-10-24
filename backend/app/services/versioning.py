from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.db.models import EditConflict, Trip


async def bump_trip_version(
    session: AsyncSession,
    *,
    trip_id: int,
    expected_version: int,
    user_id: int,
    resource_type: str,
    resource_id: int | None,
    submitted_content: dict[str, Any],
) -> int:
    result = await session.execute(
        update(Trip)
        .where(Trip.id == trip_id, Trip.version == expected_version)
        .values(version=Trip.version + 1, last_editor_id=user_id)
        .returning(Trip.version)
    )
    new_version = result.scalar_one_or_none()
    if new_version is not None:
        return new_version

    current = await session.scalar(select(Trip).where(Trip.id == trip_id))
    if current is None:
        raise NotFoundError("行程不存在")

    session.add(
        EditConflict(
            trip_id=trip_id,
            resource_type=resource_type,
            resource_id=resource_id,
            submitted_by=user_id,
            base_version=expected_version,
            current_version=current.version,
            submitted_content=submitted_content,
            current_content={
                "id": current.id,
                "version": current.version,
                "updated_at": current.updated_at.isoformat() if current.updated_at else None,
            },
        )
    )
    await session.commit()
    raise ConflictError(
        "行程已被其他成员修改，请刷新后重试",
        detail={"submitted_version": expected_version, "current_version": current.version},
    )


async def advance_trip_version(
    session: AsyncSession,
    *,
    trip_id: int,
    user_id: int,
) -> int:
    """推进行程聚合版本，用于不会覆盖同一资源的成员/权限变更。"""
    result = await session.execute(
        update(Trip)
        .where(Trip.id == trip_id)
        .values(version=Trip.version + 1, last_editor_id=user_id)
        .returning(Trip.version)
    )
    new_version = result.scalar_one_or_none()
    if new_version is None:
        raise NotFoundError("行程不存在")
    return new_version
