from __future__ import annotations

from datetime import date, time
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config import WatchConfig
from src.models import TeeTime
from src.scheduler import check_once


class FakeFetcher:
    def fetch(self, target_dates):
        return [TeeTime(date.today(), time(7, 30), "South", 2, holes=18)]


class FakeStore:
    def __init__(self) -> None:
        self.marked = []

    def has_seen(self, tee_time):
        return False

    def mark_seen(self, tee_time):
        self.marked.append(tee_time)


class FakeAlert:
    def __init__(self) -> None:
        self.sent = []

    def send(self, tee_time):
        self.sent.append(tee_time)


def _config() -> WatchConfig:
    return WatchConfig(
        state_backend="sqlite",
        slack_webhook_url=None,
        alert_channel="slack",
        timezone=ZoneInfo("America/Los_Angeles"),
        watch_courses={"south"},
        watch_holes={18},
        target_dates=[date.today()],
        earliest_time=time(6, 0),
        latest_time=time(12, 0),
        min_players=1,
        max_days_ahead=7,
        dry_run=True,
        database_path=Path(":memory:"),
        booking_url="https://www.sandiego.gov/torrey-pines",
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


def test_dry_run_does_not_send_alerts_or_mark_seen() -> None:
    store = FakeStore()
    alert = FakeAlert()

    matches = check_once(_config(), FakeFetcher(), store, alert, dry_run=True)

    assert len(matches) == 1
    assert alert.sent == []
    assert store.marked == []
