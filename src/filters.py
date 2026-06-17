from __future__ import annotations

from datetime import datetime

from .config import WatchConfig
from .models import TeeTime


def matches_watch_config(tee_time: TeeTime, config: WatchConfig) -> bool:
    today = datetime.now(config.timezone).date()
    latest_allowed_date = today.fromordinal(today.toordinal() + config.max_days_ahead)

    return (
        tee_time.course.strip().lower() in config.watch_courses
        and tee_time.date in config.target_dates
        and today <= tee_time.date <= latest_allowed_date
        and config.earliest_time <= tee_time.time <= config.latest_time
        and tee_time.players_available >= config.min_players
    )


def filter_tee_times(tee_times: list[TeeTime], config: WatchConfig) -> list[TeeTime]:
    return [tee_time for tee_time in tee_times if matches_watch_config(tee_time, config)]

