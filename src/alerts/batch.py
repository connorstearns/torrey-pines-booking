from __future__ import annotations

from collections import OrderedDict
from datetime import date

from src.config import WatchConfig
from src.models import TeeTime


def included_batch_slots(tee_times: list[TeeTime], config: WatchConfig) -> tuple[list[TeeTime], int]:
    candidates = tee_times
    if not config.slack_batch_include_standard_matches:
        candidates = [tee_time for tee_time in candidates if tee_time.priority_score >= 300]
    included = candidates[: config.slack_batch_max_slots]
    overflow_count = max(0, len(candidates) - len(included))
    return included, overflow_count


def group_tee_times_by_date_and_hour(
    tee_times: list[TeeTime], timezone
) -> "OrderedDict[date, OrderedDict[int, list[TeeTime]]]":
    grouped: "OrderedDict[date, OrderedDict[int, list[TeeTime]]]" = OrderedDict()
    for tee_time in tee_times:
        grouped.setdefault(tee_time.date, OrderedDict())
        grouped[tee_time.date].setdefault(tee_time.time.hour, [])
        grouped[tee_time.date][tee_time.time.hour].append(tee_time)

    for hourly in grouped.values():
        for hour, slots in hourly.items():
            hourly[hour] = sorted(slots, key=_bucket_sort_key)
    return grouped


def format_batch_alert(tee_times: list[TeeTime], config: WatchConfig, dry_run: bool = False, overflow_count: int = 0) -> str:
    lines = [
        "Torrey Pines tee times found",
        f"Found {len(tee_times)} new matching tee times.",
        f"Window: {config.earliest_time.strftime('%H:%M')}-{config.latest_time.strftime('%H:%M')}",
        f"Courses: {', '.join(sorted(course.title() for course in config.watch_courses))}",
        f"Dry run: {str(dry_run).lower()}",
        "",
    ]
    grouped = group_tee_times_by_date_and_hour(tee_times, config.timezone)
    include_dates = len(grouped) > 1
    for tee_date, hourly in grouped.items():
        if include_dates:
            lines.append(f"*{tee_date.strftime('%a %b %d')}*")
        for hour, slots in hourly.items():
            lines.append(f"*{_friendly_hour(hour)}*")
            for tee_time in slots:
                lines.append(_format_slot_line(tee_time, include_dates=False))
            lines.append("")
    if overflow_count:
        lines.append(f"+ {overflow_count} more matching tee times not shown.")
    lines.append("Book manually only. This alert does not reserve or hold tee times.")
    return "\n".join(lines).strip()


def build_slack_batch_payload(
    tee_times: list[TeeTime], config: WatchConfig, dry_run: bool = False, overflow_count: int = 0
) -> dict:
    text = format_batch_alert(tee_times, config, dry_run=dry_run, overflow_count=overflow_count)
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "Torrey Pines tee times found"}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Found *{len(tee_times)}* new matching tee times.\n"
                    f"Window: `{config.earliest_time.strftime('%H:%M')}-{config.latest_time.strftime('%H:%M')}`\n"
                    f"Courses: {', '.join(sorted(course.title() for course in config.watch_courses))}\n"
                    f"Dry run: `{str(dry_run).lower()}`"
                ),
            },
        },
    ]
    grouped = group_tee_times_by_date_and_hour(tee_times, config.timezone)
    include_dates = len(grouped) > 1
    for tee_date, hourly in grouped.items():
        if include_dates:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*{tee_date.strftime('%a %b %d')}*"}})
        for hour, slots in hourly.items():
            lines = [f"*{_friendly_hour(hour)}*"]
            lines.extend(_format_slot_line(tee_time, include_dates=False) for tee_time in slots)
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}})
    footer = "Book manually only. This alert does not reserve or hold tee times."
    if overflow_count:
        footer = f"+ {overflow_count} more matching tee times not shown.\n{footer}"
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": footer}]})
    return {"text": text, "blocks": blocks}


def _bucket_sort_key(tee_time: TeeTime) -> tuple[int, int, str, object]:
    course_rank = 0 if tee_time.course.strip().lower() == "south" else 1
    return (-tee_time.priority_score, course_rank, tee_time.course, tee_time.time)


def _friendly_hour(hour: int) -> str:
    suffix = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    return f"{display_hour} {suffix}"


def _friendly_time(tee_time: TeeTime) -> str:
    suffix = "AM" if tee_time.time.hour < 12 else "PM"
    display_hour = tee_time.time.hour % 12 or 12
    return f"{display_hour}:{tee_time.time.minute:02d} {suffix}"


def _format_slot_line(tee_time: TeeTime, include_dates: bool) -> str:
    parts = [
        f"- {tee_time.priority_label}",
        tee_time.course,
    ]
    if include_dates:
        parts.append(tee_time.date.strftime("%a %b %d"))
    parts.extend(
        [
            _friendly_time(tee_time),
            f"{tee_time.holes} holes" if tee_time.holes is not None else "holes unknown",
            f"{tee_time.players_available} {'spot' if tee_time.players_available == 1 else 'spots'}",
        ]
    )
    if tee_time.side:
        parts.append(tee_time.side)
    if tee_time.price is not None:
        parts.append(str(tee_time.price))
    if tee_time.booking_url:
        parts.append(f"<{tee_time.booking_url}|Book manually>")
    else:
        parts.append("Book manually")
    return " - ".join(parts)
