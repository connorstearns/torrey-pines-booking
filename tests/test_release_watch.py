from __future__ import annotations

from dataclasses import replace
from datetime import date, time

import pytest
import requests

from src.models import TeeTime
from src.scheduler import AuthSessionFailure, release_watch
from tests.test_scheduler import FakeAlert, _config


class RepeatingFetcher:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, target_dates):
        self.calls += 1
        return [TeeTime(date.today(), time(7, 30), "South", 2, holes=18, source_id="same-slot")]


class FailingOnceFetcher:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, target_dates):
        self.calls += 1
        if self.calls == 1:
            raise requests.ConnectionError("temporary")
        return []


class AuthFailFetcher:
    def fetch(self, target_dates):
        response = requests.Response()
        response.status_code = 401
        raise requests.HTTPError("auth failed", response=response)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class TrackingStore:
    def __init__(self) -> None:
        self.marked = []
        self.keys = set()

    def has_seen(self, tee_time):
        return tee_time.dedupe_key in self.keys

    def mark_seen(self, tee_time):
        self.marked.append(tee_time)
        self.keys.add(tee_time.dedupe_key)


def test_release_watch_respects_duration_interval_and_dedupes() -> None:
    clock = FakeClock()
    config = replace(
        _config(),
        release_watch_duration_seconds=31,
        release_watch_interval_seconds=15,
        release_watch_jitter_seconds=0,
    )
    store = TrackingStore()
    alert = FakeAlert()
    fetcher = RepeatingFetcher()

    runs = release_watch(config, fetcher, store, alert, dry_run=False, monotonic_func=clock.monotonic, sleep_func=clock.sleep)

    assert runs == 3
    assert fetcher.calls == 3
    assert len(alert.sent) == 1
    assert len(store.marked) == 1
    assert clock.sleeps == [15, 15, 1]


def test_release_watch_continues_on_transient_fetch_error() -> None:
    clock = FakeClock()
    config = replace(
        _config(),
        release_watch_duration_seconds=16,
        release_watch_interval_seconds=15,
        release_watch_jitter_seconds=0,
    )
    fetcher = FailingOnceFetcher()

    runs = release_watch(config, fetcher, TrackingStore(), FakeAlert(), dry_run=True, monotonic_func=clock.monotonic, sleep_func=clock.sleep)

    assert runs == 2
    assert fetcher.calls == 2


def test_release_watch_exits_on_auth_session_failure() -> None:
    with pytest.raises(AuthSessionFailure):
        release_watch(_config(), AuthFailFetcher(), TrackingStore(), FakeAlert(), dry_run=True)
