from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol

import requests

from .config import WatchConfig
from .fetchers.foreup_booking_times import ForeUpBookingTimesFetcher

SESSION_EXPIRED_MESSAGE = (
    "ForeUp session expired. Refresh FOREUP_BEARER_TOKEN and FOREUP_COOKIE in local .env, "
    "then run python -m src.main auth-check."
)
TOKEN_EXPIRES_SOON_MESSAGE = (
    "ForeUp bearer token expires soon. Refresh FOREUP_BEARER_TOKEN and FOREUP_COOKIE in local .env, "
    "then run python -m src.main auth-check."
)


class SessionAlertStore(Protocol):
    def last_session_alert_at(self, alert_key: str) -> str | None:
        ...

    def mark_session_alert_sent(self, alert_key: str, sent_at_iso: str) -> None:
        ...


@dataclass(frozen=True, slots=True)
class TokenExpiryStatus:
    expires_at: datetime | None
    seconds_remaining: int | None
    is_expired: bool
    expires_soon: bool
    is_malformed: bool = False

    @property
    def human_remaining(self) -> str:
        if self.seconds_remaining is None:
            return "unknown"
        if self.seconds_remaining < 0:
            return "expired"
        minutes = self.seconds_remaining // 60
        if minutes < 120:
            return f"{minutes} minutes"
        return f"{minutes // 60} hours"


def decode_jwt_expiration(
    token: str | None,
    warning_hours: int = 24,
    now: datetime | None = None,
) -> TokenExpiryStatus:
    now = now or datetime.now(timezone.utc)
    if not token:
        return TokenExpiryStatus(None, None, False, False)

    try:
        parts = token.split(".")
        if len(parts) < 2:
            raise ValueError("not enough JWT parts")
        payload_segment = parts[1]
        padding = "=" * (-len(payload_segment) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_segment + padding)
        payload = json.loads(payload_bytes.decode("utf-8"))
        exp = payload.get("exp")
        if exp is None:
            return TokenExpiryStatus(None, None, False, False)
        expires_at = datetime.fromtimestamp(int(exp), timezone.utc)
    except (
        AttributeError,
        binascii.Error,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        return TokenExpiryStatus(None, None, False, False, is_malformed=True)

    seconds_remaining = int((expires_at - now).total_seconds())
    return TokenExpiryStatus(
        expires_at=expires_at,
        seconds_remaining=seconds_remaining,
        is_expired=seconds_remaining <= 0,
        expires_soon=seconds_remaining <= warning_hours * 3600,
    )


def send_slack_text(
    webhook_url: str | None,
    text: str,
    post: Callable[..., requests.Response] | None = None,
) -> bool:
    if not webhook_url:
        return False
    post = post or requests.post
    response = post(webhook_url, json={"text": text}, timeout=10)
    response.raise_for_status()
    return True


def should_send_session_alert(
    store: SessionAlertStore,
    alert_key: str,
    cooldown_hours: int,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(timezone.utc)
    last_sent_at = store.last_session_alert_at(alert_key)
    if last_sent_at is None:
        return True
    try:
        last_sent = datetime.fromisoformat(last_sent_at)
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return now - last_sent >= timedelta(hours=cooldown_hours)


def send_session_alert_once(
    config: WatchConfig,
    store: SessionAlertStore,
    alert_key: str,
    message: str,
    post: Callable[..., requests.Response] | None = None,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(timezone.utc)
    if not should_send_session_alert(
        store,
        alert_key,
        config.session_alert_cooldown_hours,
        now,
    ):
        return False
    if send_slack_text(config.slack_webhook_url, message, post=post):
        store.mark_session_alert_sent(alert_key, now.isoformat())
        return True
    return False


def session_watch_once(
    config: WatchConfig,
    store: SessionAlertStore,
    fetcher: ForeUpBookingTimesFetcher | None = None,
    post: Callable[..., requests.Response] | None = None,
) -> list[str]:
    messages: list[str] = []
    token_status = decode_jwt_expiration(
        config.foreup_bearer_token,
        config.token_expiry_warning_hours,
    )
    if token_status.is_expired:
        if send_session_alert_once(
            config,
            store,
            "foreup_auth_expired",
            SESSION_EXPIRED_MESSAGE,
            post=post,
        ):
            messages.append("session-expired-alert-sent")
    elif token_status.expires_soon:
        if send_session_alert_once(
            config,
            store,
            "token_expiring",
            TOKEN_EXPIRES_SOON_MESSAGE,
            post=post,
        ):
            messages.append("token-expiry-alert-sent")

    fetcher = fetcher or ForeUpBookingTimesFetcher.from_config(config)
    target_date = config.target_dates[0] if config.target_dates else datetime.now(config.timezone).date()
    profiles = fetcher._active_profiles()
    if not profiles:
        messages.append("no-active-profiles")
        return messages

    try:
        response = fetcher.request_profile_date(profiles[0], target_date)
    except requests.RequestException:
        messages.append("availability-check-network-error")
        return messages

    if response.status_code in {401, 403}:
        if send_session_alert_once(
            config,
            store,
            "foreup_auth_expired",
            SESSION_EXPIRED_MESSAGE,
            post=post,
        ):
            messages.append("session-expired-alert-sent")
        else:
            messages.append("session-expired-alert-suppressed")
    else:
        messages.append(f"availability-status-{response.status_code}")
    return messages
