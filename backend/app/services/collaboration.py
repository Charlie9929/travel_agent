import json
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import LobbyMessage, TravelRequirement, Trip
from app.integrations.llm import DeepSeekClient, FakeLLMClient, LLMClient
from app.services.itinerary_snapshot import build_itinerary_snapshot


def queue_system_message(
    session: AsyncSession,
    *,
    trip_id: int,
    event_type: str,
    content: str,
    data: dict[str, Any] | None = None,
) -> LobbyMessage:
    message = LobbyMessage(
        trip_id=trip_id,
        sender_id=None,
        kind="system",
        content=content,
        structured_data={"event_type": event_type, **(data or {})},
    )
    session.add(message)
    return message


async def generate_chat_reply(
    session: AsyncSession,
    *,
    trip_id: int,
    user_id: int,
    question: str,
    mode: str,
    recent_messages: list[dict[str, Any]],
    client: LLMClient | None = None,
) -> str:
    settings = get_settings()
    trip = await session.get(Trip, trip_id)
    itinerary = await build_itinerary_snapshot(session, trip_id)
    requirement_statement = select(TravelRequirement).where(TravelRequirement.trip_id == trip_id)
    if mode == "group":
        requirement_statement = requirement_statement.where(
            TravelRequirement.shared_at.is_not(None)
        )
    else:
        requirement_statement = requirement_statement.where(TravelRequirement.user_id == user_id)
    requirements = list((await session.scalars(requirement_statement)).all())
    visible_requirements = []
    for item in requirements:
        if mode == "group":
            visible_requirements.append(
                {"user_id": item.user_id, "shared_summary": item.shared_summary}
            )
        else:
            visible_requirements.append({"user_id": item.user_id, "content": item.content})

    system_prompt = (
        "你是多人旅行助手的聊天模块。只根据提供的当前行程、当前可见聊天和明确可见的旅行需求回答。"
        "不得猜测或转述未提供的私聊、私密需求或长期记忆。"
        '返回 JSON 对象，格式为 {"reply": "简洁、可执行的中文回答"}。'
    )
    payload = {
        "mode": mode,
        "trip": {"id": trip_id, "title": trip.title if trip else None},
        "current_itinerary": itinerary,
        "visible_requirements": visible_requirements,
        "recent_messages": recent_messages[-30:],
        "question": question,
    }
    if client is None:
        client = (
            FakeLLMClient()
            if settings.llm_use_fake
            else DeepSeekClient(
                base_url=settings.deepseek_base_url,
                api_key=settings.deepseek_api_key,
            )
        )
    result = await client.generate_json(
        system_prompt=system_prompt,
        user_prompt=json.dumps(payload, ensure_ascii=False, default=str),
        schema={"type": "object", "required": ["reply"]},
        model=settings.deepseek_model,
        prompt_version="chat-v0.1",
        request_id=f"chat-{trip_id}-{uuid4().hex[:12]}",
        timeout_seconds=settings.deepseek_timeout_seconds,
        temperature=0.4,
    )
    reply = result.parsed_data.get("reply")
    if isinstance(reply, str) and reply.strip():
        return reply.strip()
    if settings.llm_use_fake:
        return "这是测试环境中的 Agent 回复。真实模式下会结合当前行程和可见需求给出建议。"
    return "Agent 已收到问题，但未能生成可展示的回复。"


def present_revision_diff(diff_content: dict[str, Any]) -> dict[str, Any]:
    before = diff_content.get("before")
    after = diff_content.get("after")
    changes: list[dict[str, Any]] = []
    if isinstance(before, dict) and isinstance(after, dict):
        for field in sorted(set(before) | set(after)):
            if before.get(field) != after.get(field):
                changes.append(
                    {"field": field, "before": before.get(field), "after": after.get(field)}
                )
    elif before != after and (before is not None or after is not None):
        changes.append({"field": "value", "before": before, "after": after})

    source = diff_content.get("source")
    if source:
        summary = f"由 {source} 产生的行程修改"
    elif before is None and after is not None:
        summary = "新增内容"
    elif before is not None and after is None:
        summary = "删除内容"
    elif changes:
        summary = f"修改了 {len(changes)} 个字段"
    else:
        summary = "行程内容发生变化"
    return {"summary": summary, "before": before, "after": after, "changes": changes}


def candidate_presentation(candidate: dict[str, Any]) -> dict[str, Any]:
    itinerary = candidate.get("proposed_itinerary") or {}
    cost_info = itinerary.get("cost_summary") or {}
    operations = (candidate.get("diff") or {}).get("ops") or []
    changed_items = [
        {
            "operation": item.get("op"),
            "activity_id": item.get("activity_id"),
            "day_index": item.get("day_index"),
            "fields": item.get("fields", []),
            "reason": item.get("reason"),
        }
        for item in operations
    ]
    changed_ids = {item["activity_id"] for item in changed_items if item.get("activity_id")}
    kept_items = []
    for day in itinerary.get("days", []):
        for activity in day.get("activities", []):
            activity_id = activity.get("activity_id")
            if activity_id and activity_id not in changed_ids:
                kept_items.append(
                    {
                        "activity_id": activity_id,
                        "day_index": day.get("day_index"),
                        "title": activity.get("title"),
                    }
                )
    return {
        "cost_info": cost_info,
        "changed_items": changed_items,
        "kept_items": kept_items,
    }
