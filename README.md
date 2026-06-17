# Torrey Pines Tee Time Alerts

Alert-only Python monitor for Torrey Pines tee time availability.

This project checks configured dates, courses, time windows, and player counts, then sends a notification when a new matching opening appears. It is intentionally built for manual booking: alerts include a booking link, and you click through yourself.

## What This Tool Does

- Checks a configurable set of Torrey Pines target dates.
- Normalizes tee time slots into a consistent schema.
- Filters by course, tee time window, minimum players, and maximum days ahead.
- Stores seen tee times in SQLite so the same slot does not alert repeatedly.
- Sends Slack webhook alerts.
- Supports dry-run mode for local testing without sending alerts.
- Provides a placeholder fetcher with mock data until you wire in a lawful read-only availability request.

## What This Tool Does Not Do

- It does not auto-book tee times.
- It does not log in for you.
- It does not hold reservations.
- It does not submit reservation forms.
- It does not bypass CAPTCHA or access controls.
- It does not automate payment.
- It does not perform credential stuffing.

If you later add an authenticated method, keep it lawful, read-only, and explicitly limited to availability checks.

## Setup

Requires Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with your watch settings and Slack webhook.

## Configuration

Key `.env` values:

```dotenv
SLACK_WEBHOOK_URL=
ALERT_CHANNEL=slack
TIMEZONE=America/Los_Angeles
WATCH_COURSES=North,South
TARGET_DATES=
EARLIEST_TIME=06:00
LATEST_TIME=11:00
MIN_PLAYERS=1
MAX_DAYS_AHEAD=7
DRY_RUN=true
DATABASE_PATH=torrey_tee_times.db
BOOKING_URL=https://www.sandiego.gov/torrey-pines
```

`TARGET_DATES` is optional. If omitted, the monitor checks each date from today through `MAX_DAYS_AHEAD`. To pin specific dates, use:

```dotenv
TARGET_DATES=2026-06-20,2026-06-21
```

## Slack Alerts

Create a Slack incoming webhook, then set:

```dotenv
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
ALERT_CHANNEL=slack
```

Alert format:

```text
Torrey Pines tee time open:
Course: South
Date: 2026-06-20
Time: 07:24
Players: 2
Price: $85
Book manually: https://www.sandiego.gov/torrey-pines
```

## Run Locally

Dry-run once:

```powershell
python -m src.main check-once --dry-run
```

Send real alerts once after setting `DRY_RUN=false` in `.env`:

```powershell
python -m src.main check-once
```

Run continuously using configured cadence after setting `DRY_RUN=false` in `.env`:

```powershell
python -m src.main run
```

Run continuously without sending alerts:

```powershell
python -m src.main run --dry-run
```

## Polling Cadence

The scheduler supports two watch modes:

- Normal cancellation watch: default 5-15 minutes.
- Release watch: default 10-20 seconds only inside a narrow release window.

These are configurable in `.env`:

```dotenv
NORMAL_POLL_MIN_SECONDS=300
NORMAL_POLL_MAX_SECONDS=900
RELEASE_POLL_MIN_SECONDS=10
RELEASE_POLL_MAX_SECONDS=20
RELEASE_WINDOW_START=18:58
RELEASE_WINDOW_END=19:05
```

Keep request volume low. Use the release cadence only during a narrow expected release window, and prefer the normal cancellation cadence for all other monitoring.

## Replacing the Placeholder Fetcher

For now, `src/fetchers/manual_placeholder.py` returns mock tee times and includes:

```python
fetch_from_official_availability_request()
```

Later, you can replace the placeholder by copying the read-only availability request you observe in Chrome DevTools and translating it into Python. Only use availability endpoints. Do not automate login, booking, reservation holds, CAPTCHA, form submission, or payment.

Recommended approach:

1. Open the official booking site manually in Chrome.
2. Use DevTools Network to identify a read-only availability request.
3. Translate only that request into `fetch_from_official_availability_request()`.
4. Normalize the response into `TeeTime` objects.
5. Keep polling intervals conservative.

## Tests

```powershell
pytest
```
