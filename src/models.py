from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Any


@dataclass(frozen=True, slots=True)
class TeeTime:
    date: date
    time: time
    course: str
    players_available: int
    holes: int | None = None
    side: str | None = None
    price: str | float | int | None = None
    booking_url: str | None = None
    source_id: str | None = None
    metadata: dict[str, Any] | None = None
    priority_score: int = 0
    priority_label: str = "Standard"

    @property
    def date_iso(self) -> str:
        return self.date.isoformat()

    @property
    def time_hhmm(self) -> str:
        return self.time.strftime("%H:%M")

    @property
    def dedupe_key(self) -> str:
        source_part = self.source_id or ""
        return "|".join(
            [
                self.date_iso,
                self.time_hhmm,
                self.course.strip().lower(),
                str(self.players_available),
                source_part,
            ]
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.date_iso,
            "time": self.time_hhmm,
            "course": self.course,
            "players_available": self.players_available,
            "holes": self.holes,
            "side": self.side,
            "price": self.price,
            "booking_url": self.booking_url,
            "source_id": self.source_id,
            "metadata": self.metadata or {},
            "priority_score": self.priority_score,
            "priority_label": self.priority_label,
        }
