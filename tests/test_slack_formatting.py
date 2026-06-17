from __future__ import annotations

from datetime import date, time

from src.alerts.base import format_alert, slack_payload
from src.models import TeeTime


def _slot() -> TeeTime:
    return TeeTime(
        date=date(2026, 6, 20),
        time=time(15, 0),
        course="South",
        players_available=2,
        holes=18,
        side="Front",
        price=123,
        booking_url="https://foreupsoftware.com/index.php/booking/19347/1487",
        source_id="slot-1",
        priority_score=500,
        priority_label="Top priority: South 18 before 3:30 PM",
    )


def test_slack_alert_formatting_includes_actionable_fields() -> None:
    text = format_alert(_slot())

    assert "Priority: Top priority" in text
    assert "Course: South" in text
    assert "Date: 2026-06-20" in text
    assert "Time: 15:00 PT" in text
    assert "Players: 2" in text
    assert "Holes: 18" in text
    assert "https://foreupsoftware.com/index.php/booking/19347/1487" in text


def test_slack_payload_includes_book_manually_button() -> None:
    payload = slack_payload(_slot())

    assert "blocks" in payload
    assert payload["text"]
    assert payload["blocks"][2]["elements"][0]["text"]["text"] == "Book manually"
    assert payload["blocks"][2]["elements"][0]["url"] == "https://foreupsoftware.com/index.php/booking/19347/1487"
