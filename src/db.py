from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

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
                connection.execute(SCHEMA)

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
