from __future__ import annotations

import base64
import json
from dataclasses import replace
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config import WatchConfig
from src.session_health import (
    SESSION_EXPIRED_MESSAGE,
    decode_jwt_expiration,
    session_watch_once,
)


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        return None


class FakeFetcher:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.calls = []

    def _active_profiles(self):
        return ["north-profile"]

    def request_profile_date(self, profile, target_date):
        self.calls.append((profile, target_date))
        return FakeResponse(self.status_code)


class FakeStore:
    def __init__(self, last_sent_at: str | None = None) -> None:
        self.last_sent_at = last_sent_at
        self.marked = []

    def last_session_alert_at(self, alert_key: str) -> str | None:
        return self.last_sent_at

    def mark_session_alert_sent(self, alert_key: str, sent_at_iso: str) -> None:
        self.marked.append((alert_key, sent_at_iso))
        self.last_sent_at = sent_at_iso


def _jwt(exp: int) -> str:
    header = _b64({"alg": "none", "typ": "JWT"})
    payload = _b64({"exp": exp, "sub": "local-test-subject"})
    return f"{header}.{payload}."


def _b64(payload: dict) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _config(token: str | None = None) -> WatchConfig:
    return WatchConfig(
        state_backend="sqlite",
        slack_webhook_url="https://example.com/local-webhook",
        alert_channel="slack",
        timezone=ZoneInfo("America/Los_Angeles"),
        watch_courses={"north"},
        watch_holes={9, 18},
        target_dates=[date(2026, 6, 20)],
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
        release_watch_duration_seconds=420,
        release_watch_interval_seconds=15,
        release_watch_jitter_seconds=2,
        release_watch_max_runs=None,
        priority_south_18_before=time(15, 30),
        priority_south_any_before=time(16, 30),
        priority_north_18_before=time(16, 30),
        log_level="INFO",
        foreup_base_url="https://foreupsoftware.com",
        foreup_timeout_seconds=10,
        foreup_use_auth=True,
        foreup_bearer_token=token,
        foreup_cookie="local-cookie-value",
        session_alert_cooldown_hours=6,
        token_expiry_warning_hours=24,
    )


def test_jwt_exp_parsing_works() -> None:
    now = datetime(2026, 6, 20, tzinfo=timezone.utc)
    token = _jwt(int(datetime(2026, 6, 21, tzinfo=timezone.utc).timestamp()))

    status = decode_jwt_expiration(token, warning_hours=24, now=now)

    assert status.expires_at == datetime(2026, 6, 21, tzinfo=timezone.utc)
    assert not status.is_expired
    assert status.expires_soon


def test_expired_jwt_is_detected() -> None:
    now = datetime(2026, 6, 20, tzinfo=timezone.utc)
    token = _jwt(int(datetime(2026, 6, 19, tzinfo=timezone.utc).timestamp()))

    status = decode_jwt_expiration(token, now=now)

    assert status.is_expired
    assert status.expires_soon


def test_near_expiry_jwt_is_detected() -> None:
    now = datetime(2026, 6, 20, tzinfo=timezone.utc)
    token = _jwt(int(datetime(2026, 6, 20, 12, tzinfo=timezone.utc).timestamp()))

    status = decode_jwt_expiration(token, warning_hours=24, now=now)

    assert not status.is_expired
    assert status.expires_soon


def test_malformed_token_does_not_crash() -> None:
    status = decode_jwt_expiration("not-a-jwt")

    assert status.is_malformed
    assert status.expires_at is None


def test_401_triggers_one_slack_session_expired_alert() -> None:
    calls = []

    def fake_post(url, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse(200)

    store = FakeStore()
    fetcher = FakeFetcher(401)

    messages = session_watch_once(_config(), store, fetcher=fetcher, post=fake_post)

    assert "session-expired-alert-sent" in messages
    assert calls == [
        {
            "url": "https://example.com/local-webhook",
            "json": {"text": SESSION_EXPIRED_MESSAGE},
            "timeout": 10,
        }
    ]
    assert len(fetcher.calls) == 1


def test_repeated_401_within_cooldown_does_not_spam() -> None:
    calls = []
    recent = datetime.now(timezone.utc).isoformat()

    def fake_post(url, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse(200)

    messages = session_watch_once(
        _config(),
        FakeStore(last_sent_at=recent),
        fetcher=FakeFetcher(401),
        post=fake_post,
    )

    assert "session-expired-alert-suppressed" in messages
    assert calls == []


def test_no_token_cookie_or_webhook_is_printed_by_session_watch(capsys) -> None:
    config = _config(token=_jwt(1))
    config = replace(
        config,
        slack_webhook_url="local-webhook-secret",
        foreup_cookie="local-cookie-secret",
    )

    session_watch_once(config, FakeStore(), fetcher=FakeFetcher(200), post=lambda *args, **kwargs: FakeResponse(200))
    output = capsys.readouterr().out + capsys.readouterr().err

    assert "local-webhook-secret" not in output
    assert "local-cookie-secret" not in output
    assert config.foreup_bearer_token not in output


def test_session_watch_calls_only_read_only_availability_endpoint_shape() -> None:
    fetcher = FakeFetcher(200)

    messages = session_watch_once(_config(), FakeStore(), fetcher=fetcher, post=lambda *args, **kwargs: FakeResponse(200))

    assert messages == ["availability-status-200"]
    assert len(fetcher.calls) == 1
