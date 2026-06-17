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
    lines = [
        "Torrey Pines tee time open:",
        f"Priority: {tee_time.priority_label}",
        f"Course: {tee_time.course}",
        f"Date: {tee_time.date_iso}",
        f"Time: {tee_time.time_hhmm} PT",
        f"Players: {tee_time.players_available}",
    ]
    if tee_time.holes is not None:
        lines.append(f"Holes: {tee_time.holes}")
    if tee_time.side:
        lines.append(f"Side: {tee_time.side}")
    lines.extend([f"Price: {price}", f"Book manually: {booking_url}"])
    return "\n".join(lines)


def slack_payload(tee_time: TeeTime) -> dict:
    fallback = format_alert(tee_time)
    booking_url = tee_time.booking_url or "https://foreupsoftware.com"
    fields = [
        {"type": "mrkdwn", "text": f"*Priority:*\n{tee_time.priority_label}"},
        {"type": "mrkdwn", "text": f"*Course:*\n{tee_time.course}"},
        {"type": "mrkdwn", "text": f"*Date:*\n{tee_time.date_iso}"},
        {"type": "mrkdwn", "text": f"*Time:*\n{tee_time.time_hhmm} PT"},
        {"type": "mrkdwn", "text": f"*Players:*\n{tee_time.players_available}"},
    ]
    if tee_time.holes is not None:
        fields.append({"type": "mrkdwn", "text": f"*Holes:*\n{tee_time.holes}"})
    if tee_time.side:
        fields.append({"type": "mrkdwn", "text": f"*Side:*\n{tee_time.side}"})
    if tee_time.price is not None:
        fields.append({"type": "mrkdwn", "text": f"*Price:*\n{tee_time.price}"})

    return {
        "text": fallback,
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": "Torrey Pines tee time open"}},
            {"type": "section", "fields": fields},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Book manually"},
                        "url": booking_url,
                    }
                ],
            },
        ],
    }
