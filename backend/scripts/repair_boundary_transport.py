"""Repair duplicate/misplaced outbound and return transport in an existing trip.

The command is dry-run by default. Add ``--apply`` only after checking the
resolved activities printed by the script.
"""

from __future__ import annotations

import argparse
import asyncio
import re
from datetime import timedelta

from sqlalchemy import select

from app.db.models import DayActivity, Trip, TripRevision
from app.db.session import AsyncSessionFactory

INTERCITY_PATTERN = re.compile(r"航班|飞机|机场|高铁|动车|火车|铁路|车次")


def _mode(text: str) -> str:
    if re.search(r"航班|飞机|机场", text):
        return "flight"
    if re.search(r"高铁|动车", text):
        return "high_speed_rail"
    return "rail"


async def repair(trip_id: int, *, apply: bool) -> None:
    async with AsyncSessionFactory() as session:
        trip = await session.get(Trip, trip_id)
        if trip is None:
            raise SystemExit(f"trip {trip_id} does not exist")
        if not trip.origin_city or trip.origin_city == trip.city:
            raise SystemExit("trip has no distinct origin city")
        activities = list(
            (
                await session.scalars(
                    select(DayActivity)
                    .where(DayActivity.trip_id == trip_id)
                    .order_by(DayActivity.day_number, DayActivity.order_index)
                )
            ).all()
        )
        if not activities:
            raise SystemExit("trip has no activities")

        intercity = [
            activity
            for activity in activities
            if activity.type == "transport"
            and INTERCITY_PATTERN.search(f"{activity.title} {activity.description or ''}")
        ]
        outbound = [
            activity
            for activity in intercity
            if trip.origin_city in f"{activity.title} {activity.description or ''}"
            and activity.day_number == 1
            and not re.search(r"返程|返回|回家|回到", activity.title)
        ]
        returns = [
            activity
            for activity in intercity
            if trip.origin_city in f"{activity.title} {activity.description or ''}"
            and re.search(r"返程|返回|回家|回到", activity.title)
        ]
        if len(outbound) != 1 or not returns:
            raise SystemExit(
                f"cannot resolve safely: outbound={len(outbound)}, return={len(returns)}"
            )

        canonical_return = returns[0]
        duplicate_returns = returns[1:]
        last_day = max(activity.day_number for activity in activities)
        last_order = max(
            activity.order_index
            for activity in activities
            if activity.day_number == last_day and activity not in duplicate_returns
        )
        if canonical_return.day_number != last_day:
            last_order += 1

        print(
            f"trip={trip.id} version={trip.version} dates={trip.start_date}..{trip.end_date} "
            f"days={last_day}"
        )
        print(f"outbound={outbound[0].agent_activity_id} {outbound[0].title}")
        print(
            f"return={canonical_return.agent_activity_id} {canonical_return.title} "
            f"move_to=day{last_day}/order{last_order}"
        )
        print(
            "delete_duplicates="
            + ",".join(activity.agent_activity_id for activity in duplicate_returns)
        )
        if not apply:
            print("dry run only; pass --apply to commit")
            return

        outbound_extra = dict(outbound[0].extra or {})
        outbound_extra.update(
            {
                "journey_role": "outbound",
                "transport_mode": _mode(outbound[0].title),
                "origin_city": trip.origin_city,
                "destination_city": trip.city,
                "transport_status": "estimate",
            }
        )
        outbound[0].extra = outbound_extra

        for duplicate in duplicate_returns:
            await session.delete(duplicate)
        await session.flush()
        canonical_return.day_number = last_day
        canonical_return.order_index = last_order
        return_extra = dict(canonical_return.extra or {})
        return_extra.update(
            {
                "journey_role": "return",
                "transport_mode": _mode(canonical_return.title),
                "origin_city": trip.city,
                "destination_city": trip.origin_city,
                "transport_status": "estimate",
            }
        )
        canonical_return.extra = return_extra
        previous_version = trip.version
        trip.end_date = trip.start_date + timedelta(days=last_day - 1)
        trip.version += 1
        trip.last_editor_id = trip.creator_id
        session.add(
            TripRevision(
                trip_id=trip.id,
                resource_id=canonical_return.id,
                user_id=trip.creator_id,
                version=trip.version,
                action="update",
                diff_content={
                    "source": "boundary_transport_repair",
                    "before_version": previous_version,
                    "return_activity_id": canonical_return.agent_activity_id,
                    "deleted_duplicate_ids": [
                        activity.agent_activity_id for activity in duplicate_returns
                    ],
                    "day_number": last_day,
                },
                resource_type="activity",
            )
        )
        await session.commit()
        print(f"committed version={trip.version} end_date={trip.end_date}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trip-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(repair(args.trip_id, apply=args.apply))


if __name__ == "__main__":
    main()
