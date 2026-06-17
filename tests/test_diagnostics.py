from __future__ import annotations

import base64
import json
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.config import WatchConfig
from src.diagnostics import TEST_ALERT_TEXT, print_auth_check, send_test_alert
from src.fetchers.foreup_booking_times import ForeUpBookingTimesFetcher


SENSITIVE_TOKEN = "secret-token-value"
SENSITIVE_COOKIE = "session-cookie-value"
SENSITIVE_WEBHOOK = "https://example.com/slack-webhook"


def _jwt(exp: int) -> str:
    header = _b64({"alg": "none", "typ": "JWT"})
    payload = _b64({"exp": exp})
    return f"{header}.{payload}."


def _b64(payload: dict) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


class FakeResponse:
    def __init__(self, status_code: int, payload=None, json_error: Exception | None = None) -> None:
        self.status_code = status_code
        self.payload = payload
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls = []

    def get(self, url, params, headers, timeout):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return self.response


def _config() -> WatchConfig:
    return WatchConfig(
        state_backend="sqlite",
        slack_webhook_url=SENSITIVE_WEBHOOK,
        alert_channel="slack",
        timezone=ZoneInfo("America/Los_Angeles"),
        watch_courses={"north", "south"},
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
        foreup_bearer_token=SENSITIVE_TOKEN,
        foreup_cookie=SENSITIVE_COOKIE,
        session_alert_cooldown_hours=6,
        token_expiry_warning_hours=24,
    )


def _fetcher(response: FakeResponse) -> ForeUpBookingTimesFetcher:
    return ForeUpBookingTimesFetcher(
        session=FakeSession(response),
        watch_courses={"north"},
        use_auth=True,
        bearer_token=SENSITIVE_TOKEN,
        cookie=SENSITIVE_COOKIE,
    )


def test_auth_check_200_response() -> None:
    payload = [
        {
            "time": "2026-06-20 16:57",
            "start_front": 202606201657,
            "schedule_id": 1468,
            "booking_class_id": 1135,
            "available_spots": 1,
            "holes": 9,
            "green_fee": 123,
        }
    ]
    stream = StringIO()

    result = print_auth_check(_config(), stream, _fetcher(FakeResponse(200, payload)))

    assert result.status_code == 200
    assert result.parsed_json
    assert result.slots_returned == 1
    assert result.first_slot_preview is not None
    assert "Success" in result.message


def test_auth_check_401_response() -> None:
    stream = StringIO()

    result = print_auth_check(_config(), stream, _fetcher(FakeResponse(401, [])))

    assert result.status_code == 401
    assert "401 Unauthorized" in result.message


def test_auth_check_403_response() -> None:
    stream = StringIO()

    result = print_auth_check(_config(), stream, _fetcher(FakeResponse(403, [])))

    assert result.status_code == 403
    assert "403 Forbidden" in result.message


def test_auth_check_redacts_token_cookie_and_webhook() -> None:
    stream = StringIO()

    print_auth_check(_config(), stream, _fetcher(FakeResponse(401, [])))
    output = stream.getvalue()

    assert SENSITIVE_TOKEN not in output
    assert SENSITIVE_COOKIE not in output
    assert SENSITIVE_WEBHOOK not in output
    assert "FOREUP_BEARER_TOKEN present=True" in output
    assert "FOREUP_COOKIE present=True" in output
    assert "SLACK_WEBHOOK_URL present=True" in output


def test_auth_check_warns_when_bearer_token_expires_soon() -> None:
    token = _jwt(int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()))
    config = replace(_config(), foreup_bearer_token=token)
    stream = StringIO()

    print_auth_check(config, stream, _fetcher(FakeResponse(200, [])))

    output = stream.getvalue()
    assert "token warning=Bearer token expires soon." in output
    assert token not in output


def test_test_alert_sends_exactly_one_slack_payload() -> None:
    calls = []

    def fake_post(url, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse(200, {})

    stream = StringIO()

    assert send_test_alert(SENSITIVE_WEBHOOK, stream, post=fake_post)
    assert calls == [
        {
            "url": SENSITIVE_WEBHOOK,
            "json": {"text": TEST_ALERT_TEXT},
            "timeout": 10,
        }
    ]
    assert SENSITIVE_WEBHOOK not in stream.getvalue()


def test_test_alert_missing_webhook_does_not_call_post() -> None:
    def fake_post(url, json, timeout):
        raise AssertionError("Slack post should not be called")

    stream = StringIO()

    assert not send_test_alert(None, stream, post=fake_post)
    assert "SLACK_WEBHOOK_URL is missing" in stream.getvalue()
