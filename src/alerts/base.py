from __future__ import annotations

from abc import ABC, abstractmethod

from src.models import TeeTime


class AlertChannel(ABC):
    @abstractmethod
    def send(self, tee_time: TeeTime) -> None:
        """Send an alert for one tee time."""


def format_alert(tee_time: TeeTime) -> str:
    price = tee_time.price if tee_time.price is not None else "Unknown"
    booking_url = tee_time.booking_url or "Open the official booking site manually"
    return "\n".join(
        [
            "Torrey Pines tee time open:",
            f"Course: {tee_time.course}",
            f"Date: {tee_time.date_iso}",
            f"Time: {tee_time.time_hhmm}",
            f"Players: {tee_time.players_available}",
            f"Price: {price}",
            f"Book manually: {booking_url}",
        ]
    )

