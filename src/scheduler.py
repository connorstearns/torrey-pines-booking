from __future__ import annotations

import logging
import random
import time as time_module
from datetime import datetime, time

import requests

from .alerts.base import AlertChannel, format_alert
from .config import WatchConfig
from .db import SeenTeeTimeStore
from .fetchers.base import TeeTimeFetcher
from .filters import filter_tee_times
from .models import TeeTime

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
    matching = filter_tee_times(fetched, config)
    new_matches = [tee_time for tee_time in matching if not store.has_seen(tee_time)]

    logger.info(
        "Fetched %s slots, %s matched filters, %s new",
        len(fetched),
        len(matching),
        len(new_matches),
    )

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
            backoff_seconds = _backoff_seconds(config, backoff_seconds, exc)
            sleep_seconds = backoff_seconds

        logger.info("Sleeping for %s seconds", sleep_seconds)
        time_module.sleep(sleep_seconds)
