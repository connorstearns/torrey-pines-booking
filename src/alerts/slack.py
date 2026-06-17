from __future__ import annotations

import logging

import requests

from src.alerts.base import AlertChannel, format_alert
from src.models import TeeTime

logger = logging.getLogger(__name__)


class SlackWebhookAlert(AlertChannel):
    def __init__(self, webhook_url: str, timeout_seconds: int = 10) -> None:
        if not webhook_url:
            raise ValueError("SLACK_WEBHOOK_URL is required for Slack alerts")
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds

    def send(self, tee_time: TeeTime) -> None:
        response = requests.post(
            self.webhook_url,
            json={"text": format_alert(tee_time)},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        logger.info(
            "Sent Slack alert for %s %s %s",
            tee_time.course,
            tee_time.date_iso,
            tee_time.time_hhmm,
        )

