from __future__ import annotations

import argparse
import logging
import sys

import requests

from .alerts.base import AlertChannel
from .alerts.slack import SlackWebhookAlert
from .config import WatchConfig, load_config
from .db import build_state_store
from .diagnostics import print_auth_check, send_test_alert
from .fetchers.foreup_booking_times import AuthConfigurationError, ForeUpBookingTimesFetcher
from .scheduler import AuthSessionFailure, check_once, release_watch, run_forever
from .session_health import auth_config_warnings, session_watch_once


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

    subparsers.add_parser(
        "auth-check",
        help="Check local ForeUp auth/session config against the read-only availability endpoint",
    )
    subparsers.add_parser("test-alert", help="Send one Slack webhook test message")
    subparsers.add_parser(
        "session-watch",
        help="Run one read-only ForeUp session health check and alert on expiry",
    )
    subparsers.add_parser(
        "release-watch",
        help="Run a short read-only release-window polling loop and then exit",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    configure_logging(config.log_level)

    dry_run = bool(getattr(args, "dry_run", False) or config.dry_run)

    try:
        if args.command == "auth-check":
            print_auth_check(config, sys.stdout)
            return 0
        if args.command == "test-alert":
            send_test_alert(config.slack_webhook_url, sys.stdout)
            return 0
        if args.command == "session-watch":
            store = build_state_store(config)
            results = session_watch_once(config, store)
            for result in results:
                print(result)
            return 0

        for warning in auth_config_warnings(config):
            logging.warning("%s", warning)
        if config.foreup_use_auth and (not config.foreup_bearer_token or not config.foreup_cookie):
            print(
                "FOREUP_USE_AUTH=true requires FOREUP_BEARER_TOKEN and FOREUP_COOKIE. Values were not printed.",
                file=sys.stderr,
            )
            return 1

        fetcher = ForeUpBookingTimesFetcher.from_config(config)
        store = build_state_store(config)
        alert_channel = build_alert_channel(config, dry_run)

        if args.command == "check-once":
            check_once(config, fetcher, store, alert_channel, dry_run)
            return 0
        if args.command == "run":
            run_forever(config, fetcher, store, alert_channel, dry_run)
            return 0
        if args.command == "release-watch":
            release_watch(config, fetcher, store, alert_channel, dry_run)
            return 0
    except KeyboardInterrupt:
        return 130
    except (AuthConfigurationError, AuthSessionFailure) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        print(
            f"ForeUp availability request failed with HTTP {status_code}. "
            "Run `python -m src.main auth-check` for local auth/session guidance. "
            "No alerts were sent and no slots were marked seen.",
            file=sys.stderr,
        )
        return 1
    except requests.RequestException as exc:
        print(
            f"ForeUp availability request failed: {type(exc).__name__}. "
            "No alerts were sent and no slots were marked seen.",
            file=sys.stderr,
        )
        return 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
