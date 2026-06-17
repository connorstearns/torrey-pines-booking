from __future__ import annotations

from datetime import date, time

from src.models import TeeTime
from src.priorities import score_and_sort_tee_times, score_tee_time
from tests.test_scheduler import _config


def test_south_18_before_1530_ranks_highest() -> None:
    config = _config()
    south_top = TeeTime(date.today(), time(15, 0), "South", 1, holes=18)
    north_good = TeeTime(date.today(), time(8, 0), "North", 1, holes=18)

    assert score_tee_time(south_top, config).priority_score > score_tee_time(north_good, config).priority_score


def test_south_any_before_1630_ranks_above_north() -> None:
    config = _config()
    south_any = TeeTime(date.today(), time(16, 0), "South", 1, holes=9)
    north_18 = TeeTime(date.today(), time(8, 0), "North", 1, holes=18)

    assert score_tee_time(south_any, config).priority_score > score_tee_time(north_18, config).priority_score


def test_north_18_before_1630_ranks_above_later_generic() -> None:
    config = _config()
    north_18 = TeeTime(date.today(), time(16, 0), "North", 1, holes=18)
    later = TeeTime(date.today(), time(17, 0), "North", 1, holes=9)

    assert score_tee_time(north_18, config).priority_score > score_tee_time(later, config).priority_score


def test_sorted_alert_order_uses_priority_then_date_then_time() -> None:
    config = _config()
    slots = [
        TeeTime(date.today(), time(17, 0), "North", 1, holes=9),
        TeeTime(date.today(), time(15, 0), "South", 1, holes=18),
        TeeTime(date.today(), time(16, 0), "South", 1, holes=9),
    ]

    sorted_slots = score_and_sort_tee_times(slots, config)

    assert [slot.course for slot in sorted_slots] == ["South", "South", "North"]
    assert sorted_slots[0].holes == 18
