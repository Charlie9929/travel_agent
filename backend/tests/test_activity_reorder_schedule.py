from datetime import time
from types import SimpleNamespace

from app.api.v1.endpoints.activities import _reschedule_reordered_activities


def _activity(
    activity_id: int, order_index: int, start: time, duration_min: int
) -> SimpleNamespace:
    return SimpleNamespace(
        id=activity_id,
        order_index=order_index,
        start_time=start,
        duration_min=duration_min,
    )


def test_reorder_reschedules_times_and_preserves_positional_gaps() -> None:
    first = _activity(1, 1, time(9, 0), 120)
    second = _activity(2, 2, time(11, 30), 60)
    third = _activity(3, 3, time(13, 0), 90)

    before, after = _reschedule_reordered_activities(
        [first, second, third], [3, 1, 2]  # type: ignore[list-item]
    )

    assert before == {1: "09:00", 2: "11:30", 3: "13:00"}
    assert after == {3: "09:00", 1: "11:00", 2: "13:30"}
    assert third.start_time == time(9, 0)
    assert first.start_time == time(11, 0)
    assert second.start_time == time(13, 30)
