from __future__ import annotations

from dataclasses import replace

from .config import WatchConfig
from .models import TeeTime


def score_tee_time(tee_time: TeeTime, config: WatchConfig) -> TeeTime:
    course = tee_time.course.strip().lower()
    holes = tee_time.holes

    if course == "south" and holes == 18 and tee_time.time <= config.priority_south_18_before:
        return replace(tee_time, priority_score=500, priority_label="Top priority: South 18 before 3:30 PM")
    if course == "south" and tee_time.time <= config.priority_south_any_before:
        return replace(tee_time, priority_score=400, priority_label="High priority: South before 4:30 PM")
    if course == "north" and holes == 18 and tee_time.time <= config.priority_north_18_before:
        return replace(tee_time, priority_score=300, priority_label="Priority: North 18 before 4:30 PM")
    if tee_time.time <= config.latest_time:
        return replace(tee_time, priority_score=200, priority_label="Standard match")
    return replace(tee_time, priority_score=100, priority_label="Later match")


def score_and_sort_tee_times(tee_times: list[TeeTime], config: WatchConfig) -> list[TeeTime]:
    scored = [score_tee_time(tee_time, config) for tee_time in tee_times]
    return sorted(scored, key=lambda tee_time: (-tee_time.priority_score, tee_time.date, tee_time.time))
