from __future__ import annotations

import logging
from datetime import date, time
from typing import Any

from src.fetchers.base import TeeTimeFetcher
from src.models import TeeTime

logger = logging.getLogger(__name__)


class ManualPlaceholderFetcher(TeeTimeFetcher):
    """Mock fetcher used until a real read-only availability endpoint is wired in."""

    def __init__(self, booking_url: str) -> None:
        self.booking_url = booking_url

    def fetch(self, target_dates: list[date]) -> list[TeeTime]:
        logger.info("Using placeholder fetcher with mock tee times")
        slots: list[TeeTime] = []
        for target_date in target_dates:
            slots.extend(
                [
                    TeeTime(
                        date=target_date,
                        time=time(7, 24),
                        course="South",
                        players_available=2,
                        price="$85",
                        booking_url=self.booking_url,
                        source_id=f"mock-south-{target_date.isoformat()}-0724",
                    ),
                    TeeTime(
                        date=target_date,
                        time=time(12, 10),
                        course="North",
                        players_available=4,
                        price="$65",
                        booking_url=self.booking_url,
                        source_id=f"mock-north-{target_date.isoformat()}-1210",
                    ),
                ]
            )
        return slots


def fetch_from_official_availability_request() -> list[dict[str, Any]]:
    """Future hook for a lawful read-only official availability request.

    TODO:
    - Manually inspect Chrome DevTools Network while browsing the official site.
    - Copy only the read-only availability request, never login, booking, hold,
      CAPTCHA, payment, or form-submission requests.
    - Translate that availability request into a low-frequency Python request.
    - Normalize the response into TeeTime objects in ManualPlaceholderFetcher or a
      new dedicated fetcher class.
    - Keep headers and parameters minimal and respectful; do not bypass access
      controls or automate authenticated actions.
    """
    raise NotImplementedError(
        "Paste/translate a read-only official availability request here later."
    )

