from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DbSession, require_trip_member
from app.core.config import get_settings
from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.db.models import DayActivity, TripHighlight, TripHighlightMedia
from app.schemas.collaboration import (
    HighlightCreate,
    HighlightImageReorder,
    HighlightMediaRead,
    HighlightRead,
    HighlightUpdate,
)
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/trips/{trip_id}/highlights", tags=["highlights"])

MAX_IMAGES = 3
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _upload_root() -> Path:
    root = Path(get_settings().upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


async def _trip_highlight(session: DbSession, trip_id: int, highlight_id: int) -> TripHighlight:
    highlight = await session.scalar(
        select(TripHighlight).where(
            TripHighlight.id == highlight_id,
            TripHighlight.trip_id == trip_id,
        )
    )
    if highlight is None:
        raise NotFoundError("旅行记录不存在")
    return highlight


async def _validate_activity(session: DbSession, trip_id: int, activity_id: int | None) -> None:
    if activity_id is None:
        return
    activity = await session.scalar(
        select(DayActivity.id).where(
            DayActivity.id == activity_id,
            DayActivity.trip_id == trip_id,
        )
    )
    if activity is None:
        raise AppError(
            "INVALID_HIGHLIGHT_ACTIVITY",
            "旅行记录关联的活动不存在",
            status_code=422,
        )


def _require_edit_permission(highlight: TripHighlight, current_user_id: int, role: str) -> None:
    if highlight.created_by != current_user_id and role != "owner":
        raise ForbiddenError("只有创建者或 owner 可以编辑该旅行记录")


async def _highlight_read(session: DbSession, highlight: TripHighlight) -> HighlightRead:
    images = list(
        (
            await session.scalars(
                select(TripHighlightMedia)
                .where(TripHighlightMedia.highlight_id == highlight.id)
                .order_by(TripHighlightMedia.sort_order)
            )
        ).all()
    )
    return HighlightRead(
        id=highlight.id,
        trip_id=highlight.trip_id,
        activity_id=highlight.activity_id,
        created_by=highlight.created_by,
        title=highlight.title,
        content=highlight.content,
        image_url=highlight.image_url,
        occurred_at=highlight.occurred_at,
        created_at=highlight.created_at,
        updated_at=highlight.updated_at,
        images=[HighlightMediaRead.model_validate(item) for item in images],
    )


@router.get("", response_model=ApiResponse[list[HighlightRead]])
async def list_highlights(
    trip_id: int,
    session: DbSession,
    current_user: CurrentUser,
    activity_id: int | None = Query(default=None, ge=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> ApiResponse[list[HighlightRead]]:
    await require_trip_member(session, trip_id, current_user.id)
    statement = select(TripHighlight).where(TripHighlight.trip_id == trip_id)
    if activity_id is not None:
        statement = statement.where(TripHighlight.activity_id == activity_id)
    items = list(
        (
            await session.scalars(
                statement
                .order_by(TripHighlight.occurred_at.desc().nullslast(), TripHighlight.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return ApiResponse(data=[await _highlight_read(session, item) for item in items])


@router.post("", response_model=ApiResponse[HighlightRead], status_code=201)
async def create_highlight(
    trip_id: int,
    payload: HighlightCreate,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[HighlightRead]:
    await require_trip_member(session, trip_id, current_user.id)
    await _validate_activity(session, trip_id, payload.activity_id)
    highlight = TripHighlight(
        trip_id=trip_id,
        created_by=current_user.id,
        **payload.model_dump(),
    )
    session.add(highlight)
    await session.commit()
    await session.refresh(highlight)
    return ApiResponse(data=await _highlight_read(session, highlight))


@router.put("/{highlight_id}", response_model=ApiResponse[HighlightRead])
async def update_highlight(
    trip_id: int,
    highlight_id: int,
    payload: HighlightUpdate,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[HighlightRead]:
    membership = await require_trip_member(session, trip_id, current_user.id)
    highlight = await _trip_highlight(session, trip_id, highlight_id)
    _require_edit_permission(highlight, current_user.id, membership.role)
    if "activity_id" in payload.model_fields_set:
        await _validate_activity(session, trip_id, payload.activity_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(highlight, field, value)
    await session.commit()
    await session.refresh(highlight)
    return ApiResponse(data=await _highlight_read(session, highlight))


@router.delete("/{highlight_id}", response_model=ApiResponse[dict[str, bool]])
async def delete_highlight(
    trip_id: int,
    highlight_id: int,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[dict[str, bool]]:
    membership = await require_trip_member(session, trip_id, current_user.id)
    highlight = await _trip_highlight(session, trip_id, highlight_id)
    _require_edit_permission(highlight, current_user.id, membership.role)
    images = list(
        (
            await session.scalars(
                select(TripHighlightMedia).where(
                    TripHighlightMedia.highlight_id == highlight.id
                )
            )
        ).all()
    )
    await session.delete(highlight)
    await session.commit()
    root = _upload_root()
    for image in images:
        (root / image.storage_path).unlink(missing_ok=True)
    return ApiResponse(data={"deleted": True})


@router.post(
    "/{highlight_id}/images",
    response_model=ApiResponse[HighlightMediaRead],
    status_code=201,
)
async def upload_highlight_image(
    trip_id: int,
    highlight_id: int,
    request: Request,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[HighlightMediaRead]:
    membership = await require_trip_member(session, trip_id, current_user.id)
    highlight = await _trip_highlight(session, trip_id, highlight_id)
    _require_edit_permission(highlight, current_user.id, membership.role)
    images = list(
        (
            await session.scalars(
                select(TripHighlightMedia)
                .where(TripHighlightMedia.highlight_id == highlight.id)
                .order_by(TripHighlightMedia.sort_order)
            )
        ).all()
    )
    if len(images) >= MAX_IMAGES:
        raise AppError(
            "HIGHLIGHT_IMAGE_LIMIT",
            f"每条旅行记录最多上传 {MAX_IMAGES} 张图片",
            status_code=422,
        )
    mime_type = (request.headers.get("content-type") or "").split(";", maxsplit=1)[0].lower()
    extension = ALLOWED_IMAGE_TYPES.get(mime_type)
    if extension is None:
        raise AppError(
            "UNSUPPORTED_IMAGE_TYPE",
            "仅支持 JPEG、PNG 和 WebP 图片",
            status_code=415,
        )
    body = await request.body()
    if not body:
        raise AppError("EMPTY_IMAGE", "图片内容不能为空", status_code=422)
    if len(body) > MAX_IMAGE_BYTES:
        raise AppError(
            "HIGHLIGHT_IMAGE_TOO_LARGE",
            "单张图片不能超过 8MB",
            status_code=413,
        )
    relative_dir = Path(f"trip-{trip_id}") / f"highlight-{highlight.id}"
    absolute_dir = _upload_root() / relative_dir
    absolute_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    relative_path = relative_dir / filename
    (absolute_dir / filename).write_bytes(body)
    media = TripHighlightMedia(
        highlight_id=highlight.id,
        uploaded_by=current_user.id,
        file_url=f"/uploads/{relative_path.as_posix()}",
        storage_path=relative_path.as_posix(),
        mime_type=mime_type,
        size_bytes=len(body),
        sort_order=len(images) + 1,
    )
    session.add(media)
    await session.commit()
    await session.refresh(media)
    return ApiResponse(data=HighlightMediaRead.model_validate(media))


@router.put(
    "/{highlight_id}/images/reorder",
    response_model=ApiResponse[list[HighlightMediaRead]],
)
async def reorder_highlight_images(
    trip_id: int,
    highlight_id: int,
    payload: HighlightImageReorder,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[list[HighlightMediaRead]]:
    membership = await require_trip_member(session, trip_id, current_user.id)
    highlight = await _trip_highlight(session, trip_id, highlight_id)
    _require_edit_permission(highlight, current_user.id, membership.role)
    images = list(
        (
            await session.scalars(
                select(TripHighlightMedia).where(
                    TripHighlightMedia.highlight_id == highlight.id
                )
            )
        ).all()
    )
    by_id = {item.id: item for item in images}
    if len(payload.image_ids) != len(images) or set(payload.image_ids) != set(by_id):
        raise AppError(
            "INVALID_IMAGE_ORDER",
            "图片排序必须包含该记录的全部图片",
            status_code=422,
        )
    for index, image_id in enumerate(payload.image_ids, start=10):
        by_id[image_id].sort_order = index
    await session.flush()
    for index, image_id in enumerate(payload.image_ids, start=1):
        by_id[image_id].sort_order = index
    await session.commit()
    ordered = [by_id[image_id] for image_id in payload.image_ids]
    return ApiResponse(data=[HighlightMediaRead.model_validate(item) for item in ordered])


@router.delete(
    "/{highlight_id}/images/{image_id}",
    response_model=ApiResponse[dict[str, bool]],
)
async def delete_highlight_image(
    trip_id: int,
    highlight_id: int,
    image_id: int,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[dict[str, bool]]:
    membership = await require_trip_member(session, trip_id, current_user.id)
    highlight = await _trip_highlight(session, trip_id, highlight_id)
    _require_edit_permission(highlight, current_user.id, membership.role)
    image = await session.scalar(
        select(TripHighlightMedia).where(
            TripHighlightMedia.id == image_id,
            TripHighlightMedia.highlight_id == highlight.id,
        )
    )
    if image is None:
        raise NotFoundError("旅行记录图片不存在")
    storage_path = image.storage_path
    await session.delete(image)
    await session.flush()
    remaining = list(
        (
            await session.scalars(
                select(TripHighlightMedia)
                .where(TripHighlightMedia.highlight_id == highlight.id)
                .order_by(TripHighlightMedia.sort_order)
            )
        ).all()
    )
    for index, item in enumerate(remaining, start=1):
        item.sort_order = index
    await session.commit()
    (_upload_root() / storage_path).unlink(missing_ok=True)
    return ApiResponse(data={"deleted": True})
