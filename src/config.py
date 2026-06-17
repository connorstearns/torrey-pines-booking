from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


def _load_dotenv() -> None:
    if load_dotenv is not None:
        load_dotenv()


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


def _get_time(name: str, default: str) -> time:
    value = os.getenv(name, default)
    return datetime.strptime(value, "%H:%M").time()


def _get_csv(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _get_target_dates(max_days_ahead: int, timezone: ZoneInfo) -> list[date]:
    configured = _get_csv("TARGET_DATES")
    if configured:
        return [date.fromisoformat(item) for item in configured]

    today = datetime.now(timezone).date()
    return [today + timedelta(days=offset) for offset in range(max_days_ahead + 1)]


@dataclass(frozen=True, slots=True)
class WatchConfig:
    slack_webhook_url: str | None
    alert_channel: str
    timezone: ZoneInfo
    watch_courses: set[str]
    target_dates: list[date]
    earliest_time: time
    latest_time: time
    min_players: int
    max_days_ahead: int
    dry_run: bool
    database_path: Path
    booking_url: str
    normal_poll_min_seconds: int
    normal_poll_max_seconds: int
    release_poll_min_seconds: int
    release_poll_max_seconds: int
    release_window_start: time
    release_window_end: time
    log_level: str


def load_config() -> WatchConfig:
    _load_dotenv()

    timezone = ZoneInfo(os.getenv("TIMEZONE", "America/Los_Angeles"))
    max_days_ahead = _get_int("MAX_DAYS_AHEAD", 7)
    normal_min = _get_int("NORMAL_POLL_MIN_SECONDS", 300)
    normal_max = _get_int("NORMAL_POLL_MAX_SECONDS", 900)
    release_min = _get_int("RELEASE_POLL_MIN_SECONDS", 10)
    release_max = _get_int("RELEASE_POLL_MAX_SECONDS", 20)

    if normal_min > normal_max:
        raise ValueError("NORMAL_POLL_MIN_SECONDS must be <= NORMAL_POLL_MAX_SECONDS")
    if release_min > release_max:
        raise ValueError("RELEASE_POLL_MIN_SECONDS must be <= RELEASE_POLL_MAX_SECONDS")

    return WatchConfig(
        slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL") or None,
        alert_channel=os.getenv("ALERT_CHANNEL", "slack").strip().lower(),
        timezone=timezone,
        watch_courses={course.lower() for course in _get_csv("WATCH_COURSES", "North,South")},
        target_dates=_get_target_dates(max_days_ahead, timezone),
        earliest_time=_get_time("EARLIEST_TIME", "06:00"),
        latest_time=_get_time("LATEST_TIME", "11:00"),
        min_players=_get_int("MIN_PLAYERS", 1),
        max_days_ahead=max_days_ahead,
        dry_run=_get_bool("DRY_RUN", True),
        database_path=Path(os.getenv("DATABASE_PATH", "torrey_tee_times.db")),
        booking_url=os.getenv("BOOKING_URL", "https://www.sandiego.gov/torrey-pines"),
        normal_poll_min_seconds=normal_min,
        normal_poll_max_seconds=normal_max,
        release_poll_min_seconds=release_min,
        release_poll_max_seconds=release_max,
        release_window_start=_get_time("RELEASE_WINDOW_START", "18:58"),
        release_window_end=_get_time("RELEASE_WINDOW_END", "19:05"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )

