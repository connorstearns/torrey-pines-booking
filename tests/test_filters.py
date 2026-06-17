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
        state_backend="sqlite",
        slack_webhook_url=None,
        alert_channel="slack",
        timezone=ZoneInfo("America/Los_Angeles"),
        watch_courses={"north", "south"},
        watch_holes={9, 18},
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
        foreup_base_url="https://foreupsoftware.com",
        foreup_timeout_seconds=10,
        foreup_use_auth=False,
        foreup_bearer_token=None,
        foreup_cookie=None,
        session_alert_cooldown_hours=6,
        token_expiry_warning_hours=24,
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


def test_filter_tee_times_applies_watch_holes() -> None:
    target_date = date.today()
    config = replace(_config(target_date), watch_holes={18})
    slot = TeeTime(target_date, time(7, 30), "South", 4, holes=9)

    assert filter_tee_times([slot], config) == []
