from __future__ import annotations

import logging
import random
import time as time_module
from datetime import datetime, time

import requests

from .alerts.batch import format_batch_alert, included_batch_slots
from .alerts.base import AlertChannel, format_alert
from .config import WatchConfig
from .db import SeenTeeTimeStore
from .fetchers.base import TeeTimeFetcher
from .filters import filter_tee_times
from .models import TeeTime
from .priorities import score_and_sort_tee_times
from .session_health import SESSION_EXPIRED_MESSAGE, send_session_alert_once


class AuthSessionFailure(RuntimeError):
    pass

logger = logging.getLogger(__name__)


def _time_in_window(current: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def _next_interval_seconds(config: WatchConfig) -> int:
    now = datetime.now(config.timezone).time()
    if _time_in_window(now, config.release_window_start, config.release_window_end):
        return random.randint(config.release_poll_min_seconds, config.release_poll_max_seconds)
    return random.randint(config.normal_poll_min_seconds, config.normal_poll_max_seconds)


def _backoff_seconds(config: WatchConfig, current_backoff_seconds: int, error: Exception) -> int:
    base = max(current_backoff_seconds * 2, config.normal_poll_min_seconds)
    capped = min(base, config.normal_poll_max_seconds * 2)
    if isinstance(error, requests.HTTPError) and error.response is not None:
        status_code = error.response.status_code
        if status_code in {401, 403, 429} or 500 <= status_code <= 599:
            return capped
    if isinstance(error, requests.RequestException):
        return capped
    return min(max(current_backoff_seconds * 2, 30), 300)


def check_once(
    config: WatchConfig,
    fetcher: TeeTimeFetcher,
    store: SeenTeeTimeStore,
    alert_channel: AlertChannel | None,
    dry_run: bool,
) -> list[TeeTime]:
    fetched = fetcher.fetch(config.target_dates)
    matching = score_and_sort_tee_times(filter_tee_times(fetched, config), config)
    new_matches = [tee_time for tee_time in matching if not store.has_seen(tee_time)]

    logger.info(
        "Fetched %s slots, %s matched filters, %s new",
        len(fetched),
        len(matching),
        len(new_matches),
    )

    if config.slack_alert_mode == "batch":
        included, overflow_count = included_batch_slots(new_matches, config)
        if not included:
            return new_matches
        if dry_run:
            print(format_batch_alert(included, config, dry_run=True, overflow_count=overflow_count))
            print()
            logger.info("Dry run enabled; not sending batch alert or marking slots as seen")
            return new_matches
        if alert_channel is None:
            raise RuntimeError("No alert channel configured")
        alert_channel.send_batch(included, config)
        if config.slack_batch_mark_seen_after_send:
            store.mark_seen_many(included)
        return new_matches

    for tee_time in new_matches:
        if dry_run:
            print(format_alert(tee_time))
            print()
            continue

        if alert_channel is None:
            raise RuntimeError("No alert channel configured")

        alert_channel.send(tee_time)
        store.mark_seen(tee_time)

    if dry_run:
        logger.info("Dry run enabled; not sending alerts or marking slots as seen")

    return new_matches


def release_watch(
    config: WatchConfig,
    fetcher: TeeTimeFetcher,
    store: SeenTeeTimeStore,
    alert_channel: AlertChannel | None,
    dry_run: bool,
    monotonic_func=time_module.monotonic,
    sleep_func=time_module.sleep,
    jitter_func=random.uniform,
) -> int:
    started_at = monotonic_func()
    runs = 0
    logger.info(
        "Starting release-watch for %s seconds; dry_run=%s",
        config.release_watch_duration_seconds,
        dry_run,
    )

    while monotonic_func() - started_at < config.release_watch_duration_seconds:
        if config.release_watch_max_runs is not None and runs >= config.release_watch_max_runs:
            logger.info("Release-watch reached max run cap")
            break
        runs += 1
        try:
            check_once(config, fetcher, store, alert_channel, dry_run)
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in {401, 403}:
                raise AuthSessionFailure(
                    "ForeUp auth/session failed during release-watch. Run auth-check; no secrets were printed."
                ) from exc
            logger.warning("Release-watch transient HTTP error; status=%s", status_code)
        except requests.RequestException as exc:
            logger.warning("Release-watch transient network error: %s", type(exc).__name__)

        if monotonic_func() - started_at >= config.release_watch_duration_seconds:
            break
        sleep_seconds = config.release_watch_interval_seconds
        if config.release_watch_jitter_seconds > 0:
            sleep_seconds += jitter_func(0, config.release_watch_jitter_seconds)
        remaining_seconds = config.release_watch_duration_seconds - (monotonic_func() - started_at)
        sleep_func(min(sleep_seconds, max(0, remaining_seconds)))

    return runs


def run_forever(
    config: WatchConfig,
    fetcher: TeeTimeFetcher,
    store: SeenTeeTimeStore,
    alert_channel: AlertChannel | None,
    dry_run: bool,
) -> None:
    backoff_seconds = 0
    logger.info("Starting continuous monitor; dry_run=%s", dry_run)

    while True:
        try:
            new_matches = check_once(config, fetcher, store, alert_channel, dry_run)
            backoff_seconds = 0
            sleep_seconds = _next_interval_seconds(config)
            if new_matches:
                sleep_seconds = max(sleep_seconds, config.normal_poll_max_seconds)
                logger.info("New match found; slowing next poll to at least normal max interval")
        except KeyboardInterrupt:
            logger.info("Stopping monitor")
            raise
        except Exception as exc:
            logger.exception("Monitor check failed")
            if (
                not dry_run
                and isinstance(exc, requests.HTTPError)
                and exc.response is not None
                and exc.response.status_code in {401, 403}
            ):
                send_session_alert_once(
                    config,
                    store,
                    "foreup_auth_expired",
                    SESSION_EXPIRED_MESSAGE,
                )
            backoff_seconds = _backoff_seconds(config, backoff_seconds, exc)
            sleep_seconds = backoff_seconds

        logger.info("Sleeping for %s seconds", sleep_seconds)
        time_module.sleep(sleep_seconds)
