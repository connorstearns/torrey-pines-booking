from __future__ import annotations

from dataclasses import replace
from datetime import date, time
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.config import WatchConfig
from src.db import FirestoreSeenTeeTimeStore, SeenTeeTimeStore, build_state_store
from src.models import TeeTime
from src.scheduler import check_once


class FakeSnapshot:
    def __init__(self, data=None) -> None:
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class FakeDocument:
    def __init__(self) -> None:
        self.data = None

    def get(self):
        return FakeSnapshot(self.data)

    def set(self, data, merge=False):
        if merge and self.data:
            self.data = {**self.data, **data}
        else:
            self.data = data


class FakeCollection:
    def __init__(self) -> None:
        self.docs = {}

    def document(self, document_id):
        self.docs.setdefault(document_id, FakeDocument())
        return self.docs[document_id]


class FakeFirestoreClient:
    def __init__(self) -> None:
        self.collections = {}

    def collection(self, name):
        self.collections.setdefault(name, FakeCollection())
        return self.collections[name]


class FakeFetcher:
    def fetch(self, target_dates):
        return [
            TeeTime(
                date=date.today(),
                time=time(7, 30),
                course="South",
                players_available=2,
                holes=18,
                source_id="slot-123",
            )
        ]


class FakeAlert:
    def __init__(self) -> None:
        self.sent = []

    def send(self, tee_time):
        self.sent.append(tee_time)


def _config(state_backend: str = "sqlite") -> WatchConfig:
    return WatchConfig(
        state_backend=state_backend,
        slack_webhook_url=None,
        alert_channel="slack",
        timezone=ZoneInfo("America/Los_Angeles"),
        watch_courses={"south"},
        watch_holes={18},
        target_dates=[date.today()],
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
        log_level="INFO",
        foreup_base_url="https://foreupsoftware.com",
        foreup_timeout_seconds=10,
        foreup_use_auth=False,
        foreup_bearer_token=None,
        foreup_cookie=None,
        session_alert_cooldown_hours=6,
        token_expiry_warning_hours=24,
    )


def test_sqlite_backend_still_works() -> None:
    data_dir = Path.cwd() / ".test-data"
    data_dir.mkdir(exist_ok=True)
    database_path = data_dir / f"{uuid4()}.db"
    store = SeenTeeTimeStore(database_path)
    tee_time = TeeTime(date(2026, 6, 20), time(7, 30), "South", 2, source_id="slot-1")

    assert not store.has_seen(tee_time)
    store.mark_seen(tee_time)
    assert store.has_seen(tee_time)
    database_path.unlink(missing_ok=True)


def test_firestore_backend_interface_is_used_when_configured(monkeypatch) -> None:
    created = {}

    class FakeFirestoreStore:
        def __init__(self):
            created["used"] = True

    monkeypatch.setattr("src.db.FirestoreSeenTeeTimeStore", FakeFirestoreStore)

    store = build_state_store(_config("firestore"))

    assert isinstance(store, FakeFirestoreStore)
    assert created["used"]


def test_firestore_seen_slot_store_writes_expected_fields() -> None:
    client = FakeFirestoreClient()
    store = FirestoreSeenTeeTimeStore(client=client)
    tee_time = TeeTime(
        date=date(2026, 6, 20),
        time=time(7, 30),
        course="South",
        players_available=2,
        holes=18,
        source_id="slot-123",
    )

    assert not store.has_seen(tee_time)
    store.mark_seen(tee_time)

    data = client.collections["torrey_seen_slots"].docs["slot-123"].data
    assert data["source_id"] == "slot-123"
    assert data["course"] == "South"
    assert data["date"] == "2026-06-20"
    assert data["time"] == "07:30"
    assert data["holes"] == 18
    assert data["players_available"] == 2
    assert "first_seen_at" in data
    assert "alerted_at" in data
    assert store.has_seen(tee_time)


def test_firestore_session_alert_state_uses_expected_collection_and_doc() -> None:
    client = FakeFirestoreClient()
    store = FirestoreSeenTeeTimeStore(client=client)

    store.mark_session_alert_sent("foreup_auth_expired", "2026-06-20T00:00:00+00:00")

    data = client.collections["torrey_session_alerts"].docs["foreup_auth_expired"].data
    assert data["alert_key"] == "foreup_auth_expired"
    assert store.last_session_alert_at("foreup_auth_expired") == "2026-06-20T00:00:00+00:00"


def test_dry_run_does_not_write_seen_slots() -> None:
    client = FakeFirestoreClient()
    store = FirestoreSeenTeeTimeStore(client=client)
    alert = FakeAlert()

    matches = check_once(_config(), FakeFetcher(), store, alert, dry_run=True)

    assert len(matches) == 1
    assert alert.sent == []
    doc = client.collections["torrey_seen_slots"].docs["slot-123"]
    assert doc.data is None


def test_live_mode_writes_seen_slots_after_successful_alert() -> None:
    client = FakeFirestoreClient()
    store = FirestoreSeenTeeTimeStore(client=client)
    alert = FakeAlert()
    config = replace(_config(), dry_run=False)

    matches = check_once(config, FakeFetcher(), store, alert, dry_run=False)

    assert len(matches) == 1
    assert len(alert.sent) == 1
    assert client.collections["torrey_seen_slots"].docs["slot-123"].data["source_id"] == "slot-123"
