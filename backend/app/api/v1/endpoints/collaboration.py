from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.dependencies import CurrentUser, DbSession, require_trip_member
from app.core.errors import AppError, NotFoundError
from app.db.models import (
    AgentChatMessage,
    AgentConversation,
    LobbyMessage,
    LobbyReadState,
    User,
)
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
from app.services.collaboration import generate_chat_reply

router = APIRouter(tags=["collaboration"])


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
) -> ApiResponse[list[LobbyMessageRead]]:
    await require_trip_member(session, trip_id, current_user.id)
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
    ask_agent = payload.ask_agent or "@Agent" in payload.content or "@agent" in payload.content
    if ask_agent:
        recent = list(
            (
                await session.scalars(
                    select(LobbyMessage)
                    .where(LobbyMessage.trip_id == trip_id)
                    .order_by(LobbyMessage.id.desc())
                    .limit(30)
                )
            ).all()
        )
        try:
            reply = await generate_chat_reply(
                session,
                trip_id=trip_id,
                user_id=current_user.id,
                question=payload.content,
                mode="group",
                recent_messages=[
                    {"kind": item.kind, "sender_id": item.sender_id, "content": item.content}
                    for item in reversed(recent)
                ],
            )
        except AppError as exc:
            await session.commit()
            exc.detail = {"user_message_id": user_message.id, "agent_error": exc.detail}
            raise
        agent_message = LobbyMessage(
            trip_id=trip_id,
            sender_id=None,
            kind="agent",
            content=reply,
            reply_to_id=user_message.id,
            structured_data={"trigger": "explicit_mention"},
        )
        session.add(agent_message)
        created.append(agent_message)
    await session.commit()
    for item in created:
        await session.refresh(item)
    return ApiResponse(data=[await _lobby_message_read(session, item) for item in created])


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
    conversation = await session.scalar(
        select(AgentConversation).where(
            AgentConversation.trip_id == trip_id,
            AgentConversation.user_id == current_user.id,
        )
    )
    if conversation is None:
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
) -> ApiResponse[AgentChatSendResult]:
    conversation = await _owned_conversation(session, conversation_id, current_user.id)
    await require_trip_member(session, conversation.trip_id, current_user.id)
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
    )
    session.add_all([user_message, pending])
    conversation.updated_at = func.now()
    await session.commit()
    await session.refresh(user_message)
    await session.refresh(pending)
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
    try:
        pending.content = await generate_chat_reply(
            session,
            trip_id=conversation.trip_id,
            user_id=current_user.id,
            question=payload.content,
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
    await session.commit()
    await session.refresh(pending)
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
