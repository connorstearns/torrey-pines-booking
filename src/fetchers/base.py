from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from src.models import TeeTime


class TeeTimeFetcher(ABC):
    @abstractmethod
    def fetch(self, target_dates: list[date]) -> list[TeeTime]:
        """Return normalized tee time slots for the requested dates."""

