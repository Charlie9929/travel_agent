import re

from fastapi import APIRouter, BackgroundTasks, Query
from sqlalchemy import func, select

from app.api.dependencies import (
    CurrentUser,
    DbSession,
    require_active_trip_member,
    require_trip_member,
)
from app.core.errors import AppError, NotFoundError
from app.db.models import (
    AgentChatMessage,
    AgentConversation,
    LobbyMessage,
    LobbyReadState,
    Trip,
    User,
)
from app.db.session import AsyncSessionFactory
from app.schemas.collaboration import (
    AgentChatMessageCreate,
    AgentChatMessageRead,
    AgentChatSendResult,
    AgentConversationRead,
    LobbyMessageCreate,
    LobbyMessagePage,
    LobbyMessageRead,
    MarkLobbyReadRequest,
)
from app.schemas.common import ApiResponse
from app.services.ai_service import generate_revision_candidate
from app.services.collaboration import candidate_presentation, generate_chat_reply

router = APIRouter(tags=["collaboration"])


def _agent_adjustment_requested(content: str) -> bool:
    """区分需要改行程的请求和只查询行程事实的问题。"""
    return bool(
        re.search(
            r"调整|修改|改成|改到|换成|替换|删除|增加|添加|取消|重排|提前|推迟|延后|"
            r"不要|不想|想去|保留|少安排|多安排|预算|节奏|安排.*第[一二三四五六七八九十\d]+天|"
            r"放到第[一二三四五六七八九十\d]+天|排到第[一二三四五六七八九十\d]+天",
            content,
        )
    )


def _agent_mentioned(content: str) -> bool:
    """Recognize the common half/full-width forms users enter in chat."""
    return bool(re.search(r"(?:@|＠)\s*agent\b|艾特\s*agent\b", content, re.IGNORECASE))


async def _lobby_message_read(session: DbSession, message: LobbyMessage) -> LobbyMessageRead:
    sender = await session.get(User, message.sender_id) if message.sender_id else None
    return LobbyMessageRead(
        id=message.id,
        trip_id=message.trip_id,
        sender_id=message.sender_id,
        sender_nickname=sender.nickname if sender else None,
        sender_avatar_url=sender.avatar_url if sender else None,
        kind=message.kind,
        content=message.content,
        visibility=message.visibility,
        reply_to_id=message.reply_to_id,
        structured_data=message.structured_data,
        created_at=message.created_at,
    )


async def _generate_lobby_agent_message(
    session: DbSession,
    *,
    trip_id: int,
    user_message: LobbyMessage,
    user_id: int,
) -> LobbyMessage:
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")
    public_history = list(
        (
            await session.scalars(
                select(LobbyMessage)
                .where(LobbyMessage.trip_id == trip_id)
                .order_by(LobbyMessage.id.desc())
                .limit(30)
            )
        ).all()
    )
    history_text = "\n".join(
        f"[{item.kind}:{item.sender_id or 'system'}] {item.content}"
        for item in reversed(public_history)
    )
    if _agent_adjustment_requested(user_message.content):
        instruction = (
            "请根据以下截至当前最近 30 条群聊公开记录，生成一版新的整体行程调整候选。"
            "只采用群聊中明确提出且与行程有关的共识或最新要求；不得读取任何成员私聊。\n\n"
            f"群聊记录：\n{history_text}\n\n最新触发消息：{user_message.content}"
        )
        run, result = await generate_revision_candidate(
            session=session,
            trip_id=trip_id,
            user_id=user_id,
            changed_constraints={},
            user_instruction=instruction,
            trip_version=trip.version,
        )
        candidate = result.parsed_data
        presentation = candidate_presentation(candidate)
        structured_data = {
            "workflow": "group_revise",
            "ai_run_id": run.id,
            "candidate_itinerary": candidate["proposed_itinerary"],
            "diff": candidate["diff"],
            "summary": candidate["summary"],
            "base_version": trip.version,
            "retry_count": run.retry_count,
            "requires_confirmation": True,
            "trigger": "explicit_mention",
            "requested_by": user_id,
            **presentation,
        }
        agent_content = candidate["summary"]
    else:
        agent_content = await generate_chat_reply(
            session,
            trip_id=trip_id,
            user_id=user_id,
            question=user_message.content,
            mode="group",
            recent_messages=[
                {"role": item.kind, "content": item.content}
                for item in reversed(public_history)
                if item.kind in {"user", "agent", "system"}
            ],
        )
        structured_data = {
            "workflow": "group_chat",
            "mode": "answer",
            "trigger": "explicit_mention",
            "requested_by": user_id,
            "requires_confirmation": False,
        }
    return LobbyMessage(
        trip_id=trip_id,
        sender_id=None,
        kind="agent",
        content=agent_content,
        reply_to_id=user_message.id,
        structured_data=structured_data,
    )


async def _complete_lobby_agent_message(
    *, trip_id: int, user_message_id: int, pending_message_id: int, user_id: int
) -> None:
    async with AsyncSessionFactory() as session:
        pending = await session.get(LobbyMessage, pending_message_id)
        user_message = await session.get(LobbyMessage, user_message_id)
        if pending is None or user_message is None:
            return
        try:
            pending.structured_data = {
                **(pending.structured_data or {}),
                "local_status": "pending",
                "progress_step": 1,
                "progress_label": "正在读取需求",
            }
            await session.commit()
            pending.structured_data = {
                **(pending.structured_data or {}),
                "progress_step": 2,
                "progress_label": "正在分析行程",
            }
            await session.commit()
            pending.structured_data = {
                **(pending.structured_data or {}),
                "progress_step": 3,
                "progress_label": "正在生成回复",
            }
            await session.commit()
            generated = await _generate_lobby_agent_message(
                session,
                trip_id=trip_id,
                user_message=user_message,
                user_id=user_id,
            )
            pending.content = generated.content
            pending.structured_data = generated.structured_data
        except AppError as exc:
            pending.content = exc.message
            pending.structured_data = {
                "local_status": "failed",
                "retry_content": user_message.content,
                "retry_message_id": user_message.id,
                "error_code": exc.code,
            }
        except Exception:
            pending.content = "Agent 暂时无法回复，请稍后重试"
            pending.structured_data = {
                "local_status": "failed",
                "retry_content": user_message.content,
                "retry_message_id": user_message.id,
                "error_code": "INTERNAL_ERROR",
            }
        await session.commit()


@router.get("/trips/{trip_id}/messages", response_model=ApiResponse[LobbyMessagePage])
async def list_lobby_messages(
    trip_id: int,
    session: DbSession,
    current_user: CurrentUser,
    after_id: int | None = Query(default=None, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> ApiResponse[LobbyMessagePage]:
    await require_trip_member(session, trip_id, current_user.id)
    statement = (
        select(LobbyMessage)
        .where(LobbyMessage.trip_id == trip_id)
        .order_by(LobbyMessage.id)
        .limit(limit)
    )
    if after_id is not None:
        statement = statement.where(LobbyMessage.id > after_id)
    messages = list((await session.scalars(statement)).all())
    read_state = await session.scalar(
        select(LobbyReadState).where(
            LobbyReadState.trip_id == trip_id,
            LobbyReadState.user_id == current_user.id,
        )
    )
    last_read_id = read_state.last_read_message_id if read_state else 0
    unread_count = int(
        await session.scalar(
            select(func.count(LobbyMessage.id)).where(
                LobbyMessage.trip_id == trip_id,
                LobbyMessage.id > (last_read_id or 0),
                (LobbyMessage.sender_id.is_(None) | (LobbyMessage.sender_id != current_user.id)),
            )
        )
        or 0
    )
    return ApiResponse(
        data=LobbyMessagePage(
            items=[await _lobby_message_read(session, item) for item in messages],
            unread_count=unread_count,
            next_after_id=messages[-1].id if messages else after_id,
        )
    )


@router.post(
    "/trips/{trip_id}/messages", response_model=ApiResponse[list[LobbyMessageRead]], status_code=201
)
async def send_lobby_message(
    trip_id: int,
    payload: LobbyMessageCreate,
    session: DbSession,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> ApiResponse[list[LobbyMessageRead]]:
    await require_active_trip_member(session, trip_id, current_user.id)
    if payload.reply_to_id is not None:
        reply_target = await session.scalar(
            select(LobbyMessage).where(
                LobbyMessage.id == payload.reply_to_id,
                LobbyMessage.trip_id == trip_id,
            )
        )
        if reply_target is None:
            raise NotFoundError("被引用的群聊消息不存在")
    user_message = LobbyMessage(
        trip_id=trip_id,
        sender_id=current_user.id,
        kind="user",
        content=payload.content,
        reply_to_id=payload.reply_to_id,
    )
    session.add(user_message)
    await session.flush()
    created = [user_message]
    ask_agent = payload.ask_agent or _agent_mentioned(payload.content)
    if ask_agent:
        agent_message = LobbyMessage(
            trip_id=trip_id,
            sender_id=None,
            kind="agent",
            content="",
            reply_to_id=user_message.id,
            structured_data={
                "local_status": "pending",
                "progress_step": 1,
                "progress_label": "正在读取需求",
                "retry_content": payload.content,
                "retry_message_id": user_message.id,
            },
        )
        session.add(agent_message)
        created.append(agent_message)
    await session.commit()
    for item in created:
        await session.refresh(item)
    if ask_agent:
        background_tasks.add_task(
            _complete_lobby_agent_message,
            trip_id=trip_id,
            user_message_id=user_message.id,
            pending_message_id=agent_message.id,
            user_id=current_user.id,
        )
    return ApiResponse(data=[await _lobby_message_read(session, item) for item in created])


@router.post(
    "/trips/{trip_id}/messages/{message_id}/agent",
    response_model=ApiResponse[list[LobbyMessageRead]],
    status_code=201,
)
async def retry_lobby_agent_message(
    trip_id: int,
    message_id: int,
    session: DbSession,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> ApiResponse[list[LobbyMessageRead]]:
    await require_active_trip_member(session, trip_id, current_user.id)
    user_message = await session.scalar(
        select(LobbyMessage).where(
            LobbyMessage.id == message_id,
            LobbyMessage.trip_id == trip_id,
            LobbyMessage.kind == "user",
        )
    )
    if user_message is None:
        raise NotFoundError("需要重试的群聊消息不存在")
    existing = await session.scalar(
        select(LobbyMessage)
        .where(
            LobbyMessage.trip_id == trip_id,
            LobbyMessage.reply_to_id == message_id,
            LobbyMessage.kind == "agent",
        )
        .order_by(LobbyMessage.id.desc())
    )
    if existing is not None:
        if existing.structured_data.get("local_status") == "pending":
            return ApiResponse(data=[await _lobby_message_read(session, existing)])
        existing.content = ""
        existing.structured_data = {
            "local_status": "pending",
            "progress_step": 1,
            "progress_label": "正在读取需求",
            "retry_content": user_message.content,
            "retry_message_id": user_message.id,
        }
        agent_message = existing
    else:
        agent_message = LobbyMessage(
            trip_id=trip_id,
            sender_id=None,
            kind="agent",
            content="",
            reply_to_id=user_message.id,
            structured_data={
                "local_status": "pending",
                "progress_step": 1,
                "progress_label": "正在读取需求",
                "retry_content": user_message.content,
                "retry_message_id": user_message.id,
            },
        )
        session.add(agent_message)
    await session.commit()
    await session.refresh(agent_message)
    background_tasks.add_task(
        _complete_lobby_agent_message,
        trip_id=trip_id,
        user_message_id=user_message.id,
        pending_message_id=agent_message.id,
        user_id=current_user.id,
    )
    return ApiResponse(data=[await _lobby_message_read(session, agent_message)])


@router.post("/trips/{trip_id}/messages/read", response_model=ApiResponse[dict[str, int]])
async def mark_lobby_read(
    trip_id: int,
    payload: MarkLobbyReadRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[dict[str, int]]:
    await require_trip_member(session, trip_id, current_user.id)
    message = await session.scalar(
        select(LobbyMessage).where(
            LobbyMessage.id == payload.last_read_message_id,
            LobbyMessage.trip_id == trip_id,
        )
    )
    if message is None:
        raise NotFoundError("群聊消息不存在")
    state = await session.scalar(
        select(LobbyReadState).where(
            LobbyReadState.trip_id == trip_id,
            LobbyReadState.user_id == current_user.id,
        )
    )
    if state is None:
        state = LobbyReadState(trip_id=trip_id, user_id=current_user.id)
        session.add(state)
    state.last_read_message_id = max(state.last_read_message_id or 0, message.id)
    await session.commit()
    return ApiResponse(data={"last_read_message_id": state.last_read_message_id})


@router.get("/agent/conversations", response_model=ApiResponse[list[AgentConversationRead]])
async def list_agent_conversations(
    session: DbSession, current_user: CurrentUser
) -> ApiResponse[list[AgentConversationRead]]:
    items = list(
        (
            await session.scalars(
                select(AgentConversation)
                .where(AgentConversation.user_id == current_user.id)
                .order_by(AgentConversation.updated_at.desc())
            )
        ).all()
    )
    return ApiResponse(data=[AgentConversationRead.model_validate(item) for item in items])


@router.post(
    "/trips/{trip_id}/agent/conversation",
    response_model=ApiResponse[AgentConversationRead],
)
async def get_or_create_agent_conversation(
    trip_id: int, session: DbSession, current_user: CurrentUser
) -> ApiResponse[AgentConversationRead]:
    await require_trip_member(session, trip_id, current_user.id)
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")
    conversation = await session.scalar(
        select(AgentConversation).where(
            AgentConversation.trip_id == trip_id,
            AgentConversation.user_id == current_user.id,
        )
    )
    if conversation is None:
        await require_active_trip_member(session, trip_id, current_user.id)
        conversation = AgentConversation(trip_id=trip_id, user_id=current_user.id)
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)
    return ApiResponse(data=AgentConversationRead.model_validate(conversation))


async def _owned_conversation(
    session: DbSession, conversation_id: int, user_id: int
) -> AgentConversation:
    conversation = await session.scalar(
        select(AgentConversation).where(
            AgentConversation.id == conversation_id,
            AgentConversation.user_id == user_id,
        )
    )
    if conversation is None:
        raise NotFoundError("Agent 私聊会话不存在")
    return conversation


async def _complete_agent_chat_message(
    *, conversation_id: int, pending_message_id: int, user_message_id: int, user_id: int
) -> None:
    async with AsyncSessionFactory() as session:
        conversation = await session.scalar(
            select(AgentConversation).where(
                AgentConversation.id == conversation_id,
                AgentConversation.user_id == user_id,
            )
        )
        pending = await session.get(AgentChatMessage, pending_message_id)
        user_message = await session.get(AgentChatMessage, user_message_id)
        if conversation is None or pending is None or user_message is None:
            return
        try:
            pending.structured_data = {
                **(pending.structured_data or {}),
                "progress_step": 1,
                "progress_label": "正在读取需求",
            }
            await session.commit()
            history = list(
                (
                    await session.scalars(
                        select(AgentChatMessage)
                        .where(AgentChatMessage.conversation_id == conversation.id)
                        .order_by(AgentChatMessage.id.desc())
                        .limit(30)
                    )
                ).all()
            )
            pending.structured_data = {
                **(pending.structured_data or {}),
                "progress_step": 2,
                "progress_label": "正在分析行程",
            }
            await session.commit()
            pending.structured_data = {
                **(pending.structured_data or {}),
                "progress_step": 3,
                "progress_label": "正在生成回复",
            }
            await session.commit()
            if _agent_adjustment_requested(user_message.content):
                trip = await session.get(Trip, conversation.trip_id)
                if trip is None:
                    raise NotFoundError("行程不存在")
                context = "\n".join(
                    f"{item.role}: {item.content}"
                    for item in reversed(history)
                    if item.id != pending.id
                )
                run, result = await generate_revision_candidate(
                    session=session,
                    trip_id=conversation.trip_id,
                    user_id=user_id,
                    changed_constraints={},
                    user_instruction=f"结合本次私聊上下文调整行程。\n{context}\n最新要求：{user_message.content}",
                    trip_version=trip.version,
                )
                candidate = result.parsed_data
                pending.content = candidate["summary"]
                pending.structured_data = {
                    "workflow": "revise",
                    "ai_run_id": run.id,
                    "candidate_itinerary": candidate["proposed_itinerary"],
                    "diff": candidate["diff"],
                    "summary": candidate["summary"],
                    "base_version": trip.version,
                    "retry_count": run.retry_count,
                    "requires_confirmation": True,
                    **candidate_presentation(candidate),
                }
            else:
                pending.content = await generate_chat_reply(
                    session,
                    trip_id=conversation.trip_id,
                    user_id=user_id,
                    question=user_message.content,
                    mode="private",
                    recent_messages=[
                        {"role": item.role, "content": item.content}
                        for item in reversed(history)
                        if item.id != pending.id
                    ],
                )
            pending.status = "succeeded"
            pending.error_code = None
        except AppError as exc:
            pending.status = "failed"
            pending.error_code = exc.code
            pending.content = exc.message
        except Exception:
            pending.status = "failed"
            pending.error_code = "INTERNAL_ERROR"
            pending.content = "Agent 暂时无法回复，请稍后重试"
        await session.commit()


@router.get(
    "/agent/conversations/{conversation_id}/messages",
    response_model=ApiResponse[list[AgentChatMessageRead]],
)
async def list_agent_chat_messages(
    conversation_id: int,
    session: DbSession,
    current_user: CurrentUser,
    after_id: int | None = Query(default=None, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> ApiResponse[list[AgentChatMessageRead]]:
    await _owned_conversation(session, conversation_id, current_user.id)
    statement = (
        select(AgentChatMessage)
        .where(AgentChatMessage.conversation_id == conversation_id)
        .order_by(AgentChatMessage.id)
        .limit(limit)
    )
    if after_id is not None:
        statement = statement.where(AgentChatMessage.id > after_id)
    items = list((await session.scalars(statement)).all())
    return ApiResponse(data=[AgentChatMessageRead.model_validate(item) for item in items])


@router.post(
    "/agent/conversations/{conversation_id}/messages",
    response_model=ApiResponse[AgentChatSendResult],
    status_code=201,
)
async def send_agent_chat_message(
    conversation_id: int,
    payload: AgentChatMessageCreate,
    session: DbSession,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> ApiResponse[AgentChatSendResult]:
    conversation = await _owned_conversation(session, conversation_id, current_user.id)
    await require_active_trip_member(session, conversation.trip_id, current_user.id)
    user_message = AgentChatMessage(
        conversation_id=conversation.id,
        role="user",
        content=payload.content,
        status="succeeded",
    )
    pending = AgentChatMessage(
        conversation_id=conversation.id,
        role="assistant",
        content="",
        status="pending",
        structured_data={
            "progress_step": 1,
            "progress_label": "正在读取需求",
        },
    )
    session.add_all([user_message, pending])
    conversation.updated_at = func.now()
    await session.commit()
    await session.refresh(user_message)
    await session.refresh(pending)
    await session.commit()
    await session.refresh(pending)
    background_tasks.add_task(
        _complete_agent_chat_message,
        conversation_id=conversation.id,
        pending_message_id=pending.id,
        user_message_id=user_message.id,
        user_id=current_user.id,
    )
    return ApiResponse(
        data=AgentChatSendResult(
            user_message=AgentChatMessageRead.model_validate(user_message),
            agent_message=AgentChatMessageRead.model_validate(pending),
        )
    )


@router.get("/agent/messages/{message_id}", response_model=ApiResponse[AgentChatMessageRead])
async def get_agent_chat_message(
    message_id: int, session: DbSession, current_user: CurrentUser
) -> ApiResponse[AgentChatMessageRead]:
    message = await session.get(AgentChatMessage, message_id)
    if message is None:
        raise NotFoundError("Agent 私聊消息不存在")
    await _owned_conversation(session, message.conversation_id, current_user.id)
    return ApiResponse(data=AgentChatMessageRead.model_validate(message))
