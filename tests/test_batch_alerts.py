from __future__ import annotations

from dataclasses import replace
from datetime import date, time

import pytest

from src.alerts.batch import (
    build_slack_batch_payload,
    format_batch_alert,
    group_tee_times_by_date_and_hour,
    included_batch_slots,
)
from src.models import TeeTime
from src.scheduler import check_once, release_watch
from tests.test_release_watch import FakeClock
from tests.test_scheduler import _config


class BatchFetcher:
    def __init__(self, slots) -> None:
        self.slots = slots
        self.calls = 0

    def fetch(self, target_dates):
        self.calls += 1
        return self.slots


class TrackingStore:
    def __init__(self) -> None:
        self.marked = []
        self.seen = set()

    def has_seen(self, tee_time):
        return tee_time.dedupe_key in self.seen

    def mark_seen(self, tee_time):
        self.marked.append(tee_time)
        self.seen.add(tee_time.dedupe_key)

    def mark_seen_many(self, tee_times):
        for tee_time in tee_times:
            self.mark_seen(tee_time)


class BatchAlert:
    def __init__(self, fail: bool = False) -> None:
        self.sent = []
        self.batches = []
        self.fail = fail

    def send(self, tee_time):
        self.sent.append(tee_time)

    def send_batch(self, tee_times, config):
        if self.fail:
            raise RuntimeError("slack failed")
        self.batches.append(list(tee_times))


def _slot(day: date, tee_time: time, course: str, holes: int, source_id: str, score: int, label: str) -> TeeTime:
    return TeeTime(
        date=day,
        time=tee_time,
        course=course,
        players_available=1,
        holes=holes,
        side="Front",
        price=123,
        booking_url="https://foreupsoftware.com/index.php/booking/19347/1487",
        source_id=source_id,
        priority_score=score,
        priority_label=label,
    )


def _batch_config(**kwargs):
    return replace(_config(), slack_alert_mode="batch", **kwargs)


def test_batch_grouping_by_hour() -> None:
    slots = [
        _slot(date(2026, 6, 20), time(15, 18), "South", 18, "a", 500, "Top priority"),
        _slot(date(2026, 6, 20), time(15, 50), "South", 9, "b", 400, "High priority"),
        _slot(date(2026, 6, 20), time(16, 10), "North", 18, "c", 300, "Priority"),
    ]

    grouped = group_tee_times_by_date_and_hour(slots, _config().timezone)

    assert list(grouped[date(2026, 6, 20)].keys()) == [15, 16]


def test_batch_grouping_by_date_then_hour() -> None:
    slots = [
        _slot(date(2026, 6, 20), time(15, 18), "South", 18, "a", 500, "Top priority"),
        _slot(date(2026, 6, 21), time(14, 18), "South", 18, "b", 500, "Top priority"),
    ]

    text = format_batch_alert(slots, _config())

    assert "*Sat Jun 20*" in text
    assert "*Sun Jun 21*" in text
    assert "*3 PM*" in text
    assert "*2 PM*" in text


def test_priority_sorting_within_bucket() -> None:
    slots = [
        _slot(date(2026, 6, 20), time(15, 50), "North", 18, "a", 300, "Priority"),
        _slot(date(2026, 6, 20), time(15, 18), "South", 18, "b", 500, "Top priority"),
    ]

    grouped = group_tee_times_by_date_and_hour(slots, _config().timezone)

    assert grouped[date(2026, 6, 20)][15][0].source_id == "b"


def test_batch_max_slots_truncation_and_overflow_not_marked_seen() -> None:
    config = _batch_config(slack_batch_max_slots=1)
    slots = [
        _slot(date.today(), time(7, 0), "South", 18, "a", 500, "Top priority"),
        _slot(date.today(), time(8, 0), "South", 18, "b", 500, "Top priority"),
    ]
    store = TrackingStore()
    alert = BatchAlert()

    check_once(config, BatchFetcher(slots), store, alert, dry_run=False)

    assert len(alert.batches[0]) == 1
    assert [slot.source_id for slot in store.marked] == ["a"]


def test_included_slots_marked_seen_only_after_successful_send() -> None:
    config = _batch_config()
    slots = [_slot(date.today(), time(7, 0), "South", 18, "a", 500, "Top priority")]
    store = TrackingStore()

    check_once(config, BatchFetcher(slots), store, BatchAlert(), dry_run=False)

    assert [slot.source_id for slot in store.marked] == ["a"]


def test_slack_failure_marks_no_slots_seen() -> None:
    config = _batch_config()
    slots = [_slot(date.today(), time(7, 0), "South", 18, "a", 500, "Top priority")]
    store = TrackingStore()

    with pytest.raises(RuntimeError):
        check_once(config, BatchFetcher(slots), store, BatchAlert(fail=True), dry_run=False)

    assert store.marked == []


def test_batch_dry_run_sends_no_slack_and_marks_none_seen() -> None:
    config = _batch_config()
    slots = [_slot(date.today(), time(7, 0), "South", 18, "a", 500, "Top priority")]
    store = TrackingStore()
    alert = BatchAlert()

    check_once(config, BatchFetcher(slots), store, alert, dry_run=True)

    assert alert.batches == []
    assert store.marked == []


def test_single_mode_preserves_one_alert_per_slot() -> None:
    config = _config()
    slots = [
        _slot(date.today(), time(7, 0), "South", 18, "a", 500, "Top priority"),
        _slot(date.today(), time(8, 0), "South", 18, "b", 500, "Top priority"),
    ]
    alert = BatchAlert()

    check_once(config, BatchFetcher(slots), TrackingStore(), alert, dry_run=False)

    assert len(alert.sent) == 2
    assert alert.batches == []


def test_batch_message_includes_required_fields() -> None:
    slot = _slot(date(2026, 6, 20), time(15, 18), "South", 18, "a", 500, "Top priority")

    text = format_batch_alert([slot], _config())
    payload = build_slack_batch_payload([slot], _config())

    assert "Top priority" in text
    assert "South" in text
    assert "3:18 PM" in text
    assert "1 spot" in text
    assert "18 holes" in text
    assert "https://foreupsoftware.com/index.php/booking/19347/1487" in text
    assert "Book manually" in text
    assert "Book manually only" in payload["text"]


def test_release_watch_uses_batch_mode_without_duplicate_alerts() -> None:
    clock = FakeClock()
    config = _batch_config(
        release_watch_duration_seconds=16,
        release_watch_interval_seconds=15,
        release_watch_jitter_seconds=0,
    )
    slot = _slot(date.today(), time(7, 0), "South", 18, "a", 500, "Top priority")
    store = TrackingStore()
    alert = BatchAlert()

    release_watch(config, BatchFetcher([slot]), store, alert, dry_run=False, monotonic_func=clock.monotonic, sleep_func=clock.sleep)

    assert len(alert.batches) == 1
    assert len(store.marked) == 1


def test_no_secrets_in_batch_message() -> None:
    slot = _slot(date.today(), time(7, 0), "South", 18, "a", 500, "Top priority")
    text = format_batch_alert([slot], _config())

    assert "hooks.slack.com" not in text
    assert "PHPSESSID" not in text
    assert "Bearer " not in text


def test_batch_include_standard_matches_false_filters_lower_priority() -> None:
    config = _batch_config(slack_batch_include_standard_matches=False)
    slots = [
        _slot(date.today(), time(7, 0), "North", 18, "a", 300, "Priority"),
        _slot(date.today(), time(8, 0), "North", 9, "b", 200, "Standard match"),
    ]

    included, overflow = included_batch_slots(slots, config)

    assert [slot.source_id for slot in included] == ["a"]
    assert overflow == 0
