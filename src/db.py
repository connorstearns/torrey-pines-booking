from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import WatchConfig
from .models import TeeTime


SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_tee_times (
    dedupe_key TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    course TEXT NOT NULL,
    players_available INTEGER NOT NULL,
    price TEXT,
    booking_url TEXT,
    source_id TEXT,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS session_alerts (
    alert_key TEXT PRIMARY KEY,
    last_sent_at TEXT NOT NULL
);
"""


class SeenTeeTimeStore:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        if self.database_path.parent != Path("."):
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.executescript(SCHEMA)

    def has_seen(self, tee_time: TeeTime) -> bool:
        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(
                    "SELECT 1 FROM seen_tee_times WHERE dedupe_key = ?",
                    (tee_time.dedupe_key,),
                ).fetchone()
        return row is not None

    def mark_seen(self, tee_time: TeeTime) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO seen_tee_times (
                        dedupe_key,
                        date,
                        time,
                        course,
                        players_available,
                        price,
                        booking_url,
                        source_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tee_time.dedupe_key,
                        tee_time.date_iso,
                        tee_time.time_hhmm,
                        tee_time.course,
                        tee_time.players_available,
                        None if tee_time.price is None else str(tee_time.price),
                        tee_time.booking_url,
                        tee_time.source_id,
                    ),
                )

    def mark_seen_many(self, tee_times: list[TeeTime]) -> None:
        for tee_time in tee_times:
            self.mark_seen(tee_time)

    def last_session_alert_at(self, alert_key: str) -> str | None:
        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(
                    "SELECT last_sent_at FROM session_alerts WHERE alert_key = ?",
                    (alert_key,),
                ).fetchone()
        return None if row is None else str(row["last_sent_at"])

    def mark_session_alert_sent(self, alert_key: str, sent_at_iso: str) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO session_alerts (alert_key, last_sent_at)
                    VALUES (?, ?)
                    ON CONFLICT(alert_key) DO UPDATE SET last_sent_at = excluded.last_sent_at
                    """,
                    (alert_key, sent_at_iso),
                )


class FirestoreSeenTeeTimeStore:
    seen_collection = "torrey_seen_slots"
    session_alert_collection = "torrey_session_alerts"

    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            try:
                from google.cloud import firestore
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "STATE_BACKEND=firestore requires google-cloud-firestore. "
                    "Install requirements.txt and configure Google credentials."
                ) from exc
            client = firestore.Client()
        self.client = client

    def has_seen(self, tee_time: TeeTime) -> bool:
        return bool(self._seen_doc(tee_time).get().exists)

    def mark_seen(self, tee_time: TeeTime) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        self._seen_doc(tee_time).set(
            {
                "source_id": tee_time.source_id,
                "course": tee_time.course,
                "date": tee_time.date_iso,
                "time": tee_time.time_hhmm,
                "holes": tee_time.holes,
                "players_available": tee_time.players_available,
                "first_seen_at": now_iso,
                "alerted_at": now_iso,
            },
            merge=True,
        )

    def mark_seen_many(self, tee_times: list[TeeTime]) -> None:
        for tee_time in tee_times:
            self.mark_seen(tee_time)

    def last_session_alert_at(self, alert_key: str) -> str | None:
        snapshot = self.client.collection(self.session_alert_collection).document(alert_key).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        value = data.get("last_sent_at") or data.get("alerted_at")
        return None if value is None else str(value)

    def mark_session_alert_sent(self, alert_key: str, sent_at_iso: str) -> None:
        self.client.collection(self.session_alert_collection).document(alert_key).set(
            {
                "alert_key": alert_key,
                "last_sent_at": sent_at_iso,
                "alerted_at": sent_at_iso,
            },
            merge=True,
        )

    def _seen_doc(self, tee_time: TeeTime) -> Any:
        document_id = _firestore_seen_document_id(tee_time)
        return self.client.collection(self.seen_collection).document(document_id)


def _firestore_seen_document_id(tee_time: TeeTime) -> str:
    candidate = tee_time.source_id or tee_time.dedupe_key
    if candidate and "/" not in candidate:
        return candidate
    return hashlib.sha256((candidate or tee_time.dedupe_key).encode("utf-8")).hexdigest()


def build_state_store(config: WatchConfig) -> SeenTeeTimeStore | FirestoreSeenTeeTimeStore:
    if config.state_backend == "sqlite":
        return SeenTeeTimeStore(config.database_path)
    if config.state_backend == "firestore":
        return FirestoreSeenTeeTimeStore()
    raise ValueError("STATE_BACKEND must be sqlite or firestore")
