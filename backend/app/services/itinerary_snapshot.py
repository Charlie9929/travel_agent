from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import DayActivity, Trip, TripMember, TripRevision, User

AGENT_TYPE_BY_DB_TYPE = {
    "sight": "poi",
    "food": "meal",
    "hotel": "hotel",
    "transport": "transport",
    "other": "free_time",
}


async def build_itinerary_snapshot(session: AsyncSession, trip_id: int) -> dict[str, Any]:
    """从当前已落库事实组装一份干净的 Agent 行程快照。"""
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")
    activities = list(
        (
            await session.scalars(
                select(DayActivity)
                .where(DayActivity.trip_id == trip_id)
                .order_by(DayActivity.day_number, DayActivity.order_index)
            )
        ).all()
    )
    members = list(
        (
            await session.execute(
                select(TripMember, User)
                .join(User, User.id == TripMember.user_id)
                .where(TripMember.trip_id == trip_id)
                .order_by(TripMember.id)
            )
        ).all()
    )
    revisions = list(
        (
            await session.scalars(
                select(TripRevision)
                .where(TripRevision.trip_id == trip_id)
                .order_by(TripRevision.version, TripRevision.id)
            )
        ).all()
    )

    activities_by_day: dict[int, list[dict[str, Any]]] = {}
    total_estimate = Decimal("0")
    for activity in activities:
        converted = _activity_to_agent(activity)
        activities_by_day.setdefault(activity.day_number, []).append(converted)
        if activity.price_estimated is not None:
            total_estimate += activity.price_estimated

    day_count = (trip.end_date - trip.start_date).days + 1
    days = [
        {
            "date": (trip.start_date + timedelta(days=index - 1)).isoformat(),
            "day_index": index,
            "activities": activities_by_day.get(index, []),
            "transfers": [],
        }
        for index in range(1, day_count + 1)
    ]
    budget_amount = float(trip.total_budget or 0)
    preferences = trip.preferences if isinstance(trip.preferences, dict) else {}
    constraints = trip.constraints if isinstance(trip.constraints, dict) else {}
    return {
        "schema_version": "1.0",
        "trip_id": str(trip.agent_trip_id),
        "version": trip.version,
        "created_at": trip.created_at.isoformat() if trip.created_at else None,
        "updated_at": trip.updated_at.isoformat() if trip.updated_at else None,
        "city": {"name": trip.city},
        "meta": {
            "title": trip.title,
            "date_start": trip.start_date.isoformat(),
            "date_end": trip.end_date.isoformat(),
            "traveler_count": trip.traveler_count or 1,
            "budget_total": _money(budget_amount, source="manual"),
            "preferences": _string_list(preferences),
            "pace": constraints.get("pace"),
            "party_type": constraints.get("party_type"),
            "special_constraints": _string_list(constraints),
        },
        "members": [
            {
                "user_id": str(member.user_id),
                "nickname": user.nickname,
                "role": member.role,
                "joined_at": member.joined_at.isoformat() if member.joined_at else None,
            }
            for member, user in members
        ],
        "permissions": {
            "collab_mode": "A2_poll",
            "edit_policy": "all_members",
            "invite_code": trip.share_code,
            "invite_expires_at": (
                trip.share_code_expires_at.isoformat() if trip.share_code_expires_at else None
            ),
            "locked_by": None,
        },
        "days": days,
        "cost_summary": {
            "total_estimate": _money(float(total_estimate), source="manual"),
            "by_day": [
                {
                    "date": day["date"],
                    "amount": sum(
                        item.get("cost", {}).get("amount", 0) for item in day["activities"]
                    ),
                }
                for day in days
            ],
            "budget_status": "within" if total_estimate <= Decimal(str(budget_amount)) else "over",
            "over_by": max(float(total_estimate) - budget_amount, 0),
        },
        "revisions": [_revision_to_agent(item) for item in revisions],
        "candidates": [],
    }


def _activity_to_agent(activity: DayActivity) -> dict[str, Any]:
    start = activity.start_time.strftime("%H:%M") if activity.start_time else "00:00"
    end_dt = datetime.combine(datetime.min.date(), activity.start_time or datetime.min.time())
    end_dt += timedelta(minutes=activity.duration_min or 1)
    extra = activity.extra if isinstance(activity.extra, dict) else {}
    item: dict[str, Any] = {
        "activity_id": activity.agent_activity_id,
        "type": AGENT_TYPE_BY_DB_TYPE.get(activity.type, "free_time"),
        "title": activity.title,
        "time_slot": {"start": start, "end": end_dt.strftime("%H:%M")},
        "note": activity.description,
        "open_hours_hint": extra.get("open_hours_hint"),
        "status": extra.get("status", "planned"),
        "replaced_reason": extra.get("replaced_reason"),
    }
    if activity.location_name:
        item["location"] = {
            "name": activity.location_name,
            "lng": float(activity.longitude) if activity.longitude is not None else None,
            "lat": float(activity.latitude) if activity.latitude is not None else None,
            "poi_id": activity.poi_id,
            "poi_source": activity.poi_provider,
        }
    if activity.price_estimated is not None:
        item["cost"] = _money(
            float(activity.price_estimated), source=activity.price_source or "llm"
        )
    return item


def _money(amount: float, *, source: str) -> dict[str, Any]:
    allowed_sources = {"llm", "amap", "baidu", "qweather", "manual", "other"}
    allowed_source = source if source in allowed_sources else "other"
    return {
        "amount": amount,
        "currency": "CNY",
        "price_type": "estimate",
        "source": allowed_source,
    }


def _string_list(value: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for key, item in value.items():
        if isinstance(item, list):
            result.extend(str(entry) for entry in item)
        elif item not in (None, "", False):
            result.append(f"{key}: {item}")
    return result


def _revision_to_agent(revision: TripRevision) -> dict[str, Any]:
    action = {
        "create": "create",
        "replan": "replan_midtrip",
        "update": "member_edit",
        "delete": "member_edit",
        "reorder": "member_edit",
    }.get(revision.action, "member_edit")
    return {
        "revision_id": f"rev-{revision.id}",
        "seq": revision.version,
        "actor": {"user_id": str(revision.user_id), "source": "human"},
        "action": action,
        "summary": revision.diff_content.get("summary") if revision.diff_content else None,
        "diff": [],
        "status": "applied",
        "created_at": revision.created_at.isoformat() if revision.created_at else None,
        "confirmed_by": str(revision.user_id),
        "confirmed_at": revision.created_at.isoformat() if revision.created_at else None,
    }
