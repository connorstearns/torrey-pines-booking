from __future__ import annotations

from datetime import date, time
from pathlib import Path
from uuid import uuid4

from src.db import SeenTeeTimeStore
from src.models import TeeTime


def _db_path() -> Path:
    data_dir = Path.cwd() / ".test-data"
    data_dir.mkdir(exist_ok=True)
    return data_dir / f"{uuid4()}.db"


def test_seen_store_marks_and_detects_seen_slots() -> None:
    database_path = _db_path()
    store = SeenTeeTimeStore(database_path)
    tee_time = TeeTime(
        date=date(2026, 6, 20),
        time=time(7, 24),
        course="South",
        players_available=2,
        price="$85",
        booking_url="https://example.com",
        source_id="slot-1",
    )

    assert not store.has_seen(tee_time)

    store.mark_seen(tee_time)

    assert store.has_seen(tee_time)
    database_path.unlink(missing_ok=True)


def test_seen_store_dedupe_key_prevents_duplicate_alerts() -> None:
    database_path = _db_path()
    store = SeenTeeTimeStore(database_path)
    tee_time = TeeTime(date(2026, 6, 20), time(7, 24), "South", 2, source_id="slot-1")
    duplicate = TeeTime(date(2026, 6, 20), time(7, 24), "South", 2, source_id="slot-1")

    store.mark_seen(tee_time)
    store.mark_seen(duplicate)

    assert store.has_seen(duplicate)
    database_path.unlink(missing_ok=True)
