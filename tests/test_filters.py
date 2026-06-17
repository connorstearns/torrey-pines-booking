from __future__ import annotations

from dataclasses import replace
from datetime import date, time
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config import WatchConfig
from src.filters import filter_tee_times
from src.models import TeeTime


def _config(target_date: date) -> WatchConfig:
    return WatchConfig(
        slack_webhook_url=None,
        alert_channel="slack",
        timezone=ZoneInfo("America/Los_Angeles"),
        watch_courses={"north", "south"},
        target_dates=[target_date],
        earliest_time=time(6, 0),
        latest_time=time(11, 0),
        min_players=2,
        max_days_ahead=30,
        dry_run=True,
        database_path=Path(":memory:"),
        booking_url="https://example.com",
        normal_poll_min_seconds=300,
        normal_poll_max_seconds=900,
        release_poll_min_seconds=10,
        release_poll_max_seconds=20,
        release_window_start=time(18, 58),
        release_window_end=time(19, 5),
        log_level="INFO",
    )


def test_filter_tee_times_applies_course_time_players_and_date() -> None:
    target_date = date.today()
    config = _config(target_date)
    match = TeeTime(target_date, time(7, 30), "South", 2)

    slots = [
        match,
        TeeTime(target_date, time(5, 59), "South", 2),
        TeeTime(target_date, time(7, 30), "Balboa", 2),
        TeeTime(target_date, time(7, 30), "South", 1),
        TeeTime(date(2099, 1, 1), time(7, 30), "South", 2),
    ]

    assert filter_tee_times(slots, config) == [match]


def test_filter_tee_times_is_case_insensitive_for_courses() -> None:
    target_date = date.today()
    config = replace(_config(target_date), watch_courses={"south"})
    slot = TeeTime(target_date, time(7, 30), "SOUTH", 4)

    assert filter_tee_times([slot], config) == [slot]

