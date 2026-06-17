from __future__ import annotations

import argparse
import logging
import sys

from .alerts.base import AlertChannel
from .alerts.slack import SlackWebhookAlert
from .config import WatchConfig, load_config
from .db import SeenTeeTimeStore
from .fetchers.manual_placeholder import ManualPlaceholderFetcher
from .scheduler import check_once, run_forever


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def build_alert_channel(config: WatchConfig, dry_run: bool) -> AlertChannel | None:
    if dry_run:
        return None
    if config.alert_channel == "slack":
        return SlackWebhookAlert(config.slack_webhook_url or "")
    raise ValueError(f"Unsupported ALERT_CHANNEL: {config.alert_channel}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Alert-only Torrey Pines tee time availability monitor."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run continuously")
    run_parser.add_argument("--dry-run", action="store_true", help="Print matches without alerts")

    check_parser = subparsers.add_parser("check-once", help="Check once and exit")
    check_parser.add_argument("--dry-run", action="store_true", help="Print matches without alerts")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    configure_logging(config.log_level)

    dry_run = bool(args.dry_run or config.dry_run)
    fetcher = ManualPlaceholderFetcher(config.booking_url)
    store = SeenTeeTimeStore(config.database_path)
    alert_channel = build_alert_channel(config, dry_run)

    try:
        if args.command == "check-once":
            check_once(config, fetcher, store, alert_channel, dry_run)
            return 0
        if args.command == "run":
            run_forever(config, fetcher, store, alert_channel, dry_run)
            return 0
    except KeyboardInterrupt:
        return 130

    return 2


if __name__ == "__main__":
    sys.exit(main())

