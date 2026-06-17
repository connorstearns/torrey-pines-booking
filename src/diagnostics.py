from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, TextIO

import requests

from .config import WatchConfig
from .fetchers.foreup_booking_times import ForeUpBookingTimesFetcher
from .session_health import decode_jwt_expiration

TEST_ALERT_TEXT = (
    "Test alert from Torrey Pines tee-time monitor. If you see this on your phone, "
    "Slack notifications are working."
)


@dataclass(frozen=True, slots=True)
class AuthCheckResult:
    status_code: int | None
    parsed_json: bool
    slots_returned: int
    first_slot_preview: dict[str, Any] | None
    message: str
    error: str | None = None


def print_auth_check(
    config: WatchConfig,
    stream: TextIO,
    fetcher: ForeUpBookingTimesFetcher | None = None,
) -> AuthCheckResult:
    fetcher = fetcher or ForeUpBookingTimesFetcher.from_config(config)
    target_date = config.target_dates[0] if config.target_dates else datetime.now(config.timezone).date()
    profiles = fetcher._active_profiles()
    if not profiles:
        result = AuthCheckResult(None, False, 0, None, "No configured ForeUp course profiles.")
        _print_auth_summary(config, result, stream)
        return result

    profile = profiles[0]
    try:
        response = fetcher.request_profile_date(profile, target_date)
    except requests.Timeout:
        result = AuthCheckResult(None, False, 0, None, "Timeout: slow down and try again later.", "timeout")
        _print_auth_summary(config, result, stream)
        return result
    except requests.RequestException as exc:
        result = AuthCheckResult(None, False, 0, None, "Network error: check connectivity and try again later.", type(exc).__name__)
        _print_auth_summary(config, result, stream)
        return result

    parsed_json = False
    slots_returned = 0
    preview = None
    try:
        payload = response.json()
        parsed_json = True
        if isinstance(payload, list):
            normalized = fetcher._normalize_response(
                [item for item in payload if isinstance(item, dict)],
                profile,
            )
            slots_returned = len(payload)
            preview = normalized[0].as_dict() if normalized else None
    except (ValueError, json.JSONDecodeError):
        parsed_json = False

    result = AuthCheckResult(
        status_code=response.status_code,
        parsed_json=parsed_json,
        slots_returned=slots_returned,
        first_slot_preview=preview,
        message=_auth_next_step(response.status_code, parsed_json, slots_returned),
    )
    _print_auth_summary(config, result, stream)
    return result


def _auth_next_step(status_code: int, parsed_json: bool, slots_returned: int) -> str:
    if status_code == 200 and parsed_json and slots_returned > 0:
        return "Success: read-only availability returned slots. Try check-once --dry-run next."
    if status_code == 200 and parsed_json:
        return "Success: endpoint authorized, but no slots were returned for the checked date/profile."
    if status_code == 200:
        return "Parse error: endpoint returned 200, but the body was not valid JSON."
    if status_code == 401:
        return "401 Unauthorized: add only local read-only session values in .env if you choose to use auth."
    if status_code == 403:
        return "403 Forbidden: your session may be blocked, expired, or not allowed for this endpoint."
    if status_code == 429:
        return "429 Rate limited: stop polling and wait before trying again."
    if 500 <= status_code <= 599:
        return "Server error: slow down and try again later."
    return "Unexpected status: inspect local config without exposing secrets."


def _print_auth_summary(config: WatchConfig, result: AuthCheckResult, stream: TextIO) -> None:
    token_status = decode_jwt_expiration(
        config.foreup_bearer_token,
        config.token_expiry_warning_hours,
    )
    print("ForeUp auth check:", file=stream)
    print(f"FOREUP_USE_AUTH={config.foreup_use_auth}", file=stream)
    print(f"FOREUP_BEARER_TOKEN present={bool(config.foreup_bearer_token)}", file=stream)
    print(f"FOREUP_COOKIE present={bool(config.foreup_cookie)}", file=stream)
    print(f"SLACK_WEBHOOK_URL present={bool(config.slack_webhook_url)}", file=stream)
    print(f"endpoint status code={result.status_code}", file=stream)
    if config.foreup_bearer_token:
        if token_status.expires_at:
            print(f"token expiration datetime={token_status.expires_at.isoformat()}", file=stream)
            print(f"token time remaining={token_status.human_remaining}", file=stream)
            print(f"token expired={token_status.is_expired}", file=stream)
            print(f"token nearing expiration={token_status.expires_soon}", file=stream)
            if token_status.expires_soon:
                print("token warning=Bearer token expires soon.", file=stream)
        elif token_status.is_malformed:
            print("token expiration status=malformed or unreadable", file=stream)
        else:
            print("token expiration status=no exp claim found", file=stream)
    print(f"response parses as JSON={result.parsed_json}", file=stream)
    print(f"slots returned={result.slots_returned}", file=stream)
    if result.first_slot_preview:
        print(f"first normalized slot preview={result.first_slot_preview}", file=stream)
    print(f"next step={result.message}", file=stream)


def send_test_alert(
    webhook_url: str | None,
    stream: TextIO,
    post: Callable[..., requests.Response] | None = None,
) -> bool:
    if not webhook_url:
        print("SLACK_WEBHOOK_URL is missing.", file=stream)
        print("Create a Slack incoming webhook, add it to .env, then rerun test-alert.", file=stream)
        return False

    post = post or requests.post
    response = post(webhook_url, json={"text": TEST_ALERT_TEXT}, timeout=10)
    response.raise_for_status()
    print("Sent one Slack test alert. Webhook URL was not printed.", file=stream)
    return True
