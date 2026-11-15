from datetime import time
from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import activities as activity_endpoint
from app.db.models import DayActivity


def _activity(
    activity_id: int,
    order: int,
    start: time,
    duration: int,
) -> DayActivity:
    return DayActivity(
        id=activity_id,
        agent_activity_id=f"act-{activity_id}",
        trip_id=1,
        day_number=1,
        order_index=order,
        title=f"活动{activity_id}",
        type="sight",
        start_time=start,
        duration_min=duration,
        location_name=f"地点{activity_id}",
        latitude=23.0 + activity_id / 100,
        longitude=113.0 + activity_id / 100,
        extra={},
    )


@pytest.mark.asyncio
async def test_duration_change_cascades_all_following_start_times() -> None:
    edited = _activity(1, 1, time(9, 0), 90)
    second = _activity(2, 2, time(10, 30), 60)
    third = _activity(3, 3, time(12, 0), 60)

    changes = await activity_endpoint._cascade_activity_times(
        trip=SimpleNamespace(city_adcode="440100"),  # type: ignore[arg-type]
        activity=edited,
        day_activities=[edited, second, third],
        old_start=9 * 60,
        old_duration=60,
        location_changed=False,
    )

    assert second.start_time == time(11, 0)
    assert third.start_time == time(12, 30)
    assert changes[2] == {"before": "10:30", "after": "11:00"}


@pytest.mark.asyncio
async def test_location_change_uses_new_route_then_shifts_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAmap:
        async def routes(self, **kwargs) -> dict:
            assert kwargs["city_code"] == "440100"
            return {
                "routes": {
                    "walk": {
                        "available": True,
                        "distance_m": 1200,
                        "duration_min": 20,
                    }
                }
            }

    monkeypatch.setattr(activity_endpoint, "get_amap_client", lambda: FakeAmap())
    edited = _activity(1, 1, time(9, 0), 60)
    second = _activity(2, 2, time(10, 30), 60)
    third = _activity(3, 3, time(12, 0), 60)

    await activity_endpoint._cascade_activity_times(
        trip=SimpleNamespace(city_adcode="440100"),  # type: ignore[arg-type]
        activity=edited,
        day_activities=[edited, second, third],
        old_start=9 * 60,
        old_duration=60,
        location_changed=True,
    )

    assert second.start_time == time(10, 35)
    assert third.start_time == time(12, 5)
