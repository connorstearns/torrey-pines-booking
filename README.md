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
- Fetches read-only ForeUp booking time availability for Torrey Pines.

## What This Tool Does Not Do

- It does not auto-book tee times.
- It does not log in for you.
- It does not hold reservations.
- It does not submit reservation forms.
- It does not bypass CAPTCHA or access controls.
- It does not automate payment.
- It does not perform credential stuffing.
- It does not call `pending_reservation`, `refresh_pending_reservation`, `reservation`, `cart`, `checkout`, or `payment` endpoints.

If you later enable optional authenticated headers, keep them lawful, read-only, and explicitly limited to availability checks.

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
STATE_BACKEND=sqlite
FOREUP_USE_AUTH=false
FOREUP_BEARER_TOKEN=
FOREUP_COOKIE=
FOREUP_BASE_URL=https://foreupsoftware.com
FOREUP_TIMEOUT_SECONDS=10
SESSION_ALERT_COOLDOWN_HOURS=6
TOKEN_EXPIRY_WARNING_HOURS=24
TIMEZONE=America/Los_Angeles
WATCH_COURSES=North,South
TARGET_DATES=
EARLIEST_TIME=06:00
LATEST_TIME=12:00
MIN_PLAYERS=1
WATCH_HOLES=9,18
MAX_DAYS_AHEAD=7
DRY_RUN=true
DATABASE_PATH=torrey_tee_times.db
BOOKING_URL=https://www.sandiego.gov/torrey-pines
RELEASE_WATCH_DURATION_SECONDS=420
RELEASE_WATCH_INTERVAL_SECONDS=15
RELEASE_WATCH_JITTER_SECONDS=2
RELEASE_WATCH_MAX_RUNS=
PRIORITY_SOUTH_18_BEFORE=15:30
PRIORITY_SOUTH_ANY_BEFORE=16:30
PRIORITY_NORTH_18_BEFORE=16:30
```

`TARGET_DATES` is optional. If omitted, the monitor checks each date from today through `MAX_DAYS_AHEAD`. To pin specific dates, use:

```dotenv
TARGET_DATES=2026-06-20,2026-06-21
```

## ForeUp Availability Fetcher

The default fetcher uses this read-only availability endpoint:

```text
GET https://foreupsoftware.com/index.php/api/booking/times
```

Known Torrey Pines resident 0-7 day profiles:

| Course | course_id | schedule_id / teesheet_id | booking_class |
| --- | ---: | ---: | ---: |
| North | 19347 | 1468 | 1135 |
| South | 19347 | 1487 | 888 |

The fetcher sends one availability request per configured course profile per target date. It normalizes returned ForeUp items into `TeeTime` records using:

- `time` parsed from `YYYY-MM-DD HH:MM`
- `available_spots` as `players_available`
- `green_fee` as `price`, with 9-hole or 18-hole green fee fallback
- `teesheet_side_name` as side metadata
- a stable `source_id` from schedule, booking class, start time, and holes

Booking links are manual-only and use:

```text
https://foreupsoftware.com/index.php/booking/19347/{schedule_id}
```

The app has a request URL blocklist and refuses to call endpoints containing `pending_reservation`, `refresh_pending_reservation`, `reservation`, `cart`, `checkout`, or `payment`.

### Auth And Session Warning

By default, no auth headers, cookies, bearer tokens, or session values are sent:

```dotenv
FOREUP_USE_AUTH=false
```

If you set `FOREUP_USE_AUTH=true`, optional `FOREUP_BEARER_TOKEN` and `FOREUP_COOKIE` values are loaded only from environment variables. Do not commit `.env`, cookies, `PHPSESSID`, JWTs, bearer tokens, or personal data. Authenticated/session-based requests may carry account and policy risk; use them only for lawful read-only availability checks.

The unauthenticated local dry run may return `401 Unauthorized`. That means the read-only endpoint was reached, but ForeUp wants an authorized browser/session context. If you choose to use local authenticated requests, keep those values only in `.env`. Do not paste cookies or tokens into Codex prompts, chat messages, source code, README examples, commits, logs, screenshots, or issue text.

Session values may expire and need to be refreshed manually from your own browser session. Google Cloud deployment is not recommended yet because these values are browser/session-bound and should not be moved into cloud infrastructure until the local path is proven stable and you have a safer auth story.

## Slack Alerts

Create a Slack incoming webhook, then set:

```dotenv
SLACK_WEBHOOK_URL=<your Slack incoming webhook URL>
ALERT_CHANNEL=slack
```

Alert format:

```text
Torrey Pines tee time open:
Priority: Top priority: South 18 before 3:30 PM
Course: South
Date: 2026-06-20
Time: 07:24 PT
Players: 2
Holes: 18
Price: $85
Book manually: https://www.sandiego.gov/torrey-pines
```

Slack alerts use Block Kit with fallback text and a `Book manually` button. The button only opens the ForeUp booking page; it does not submit forms, hold tee times, create reservations, or call reservation endpoints.

## Run Locally

Recommended local setup order:

1. Create a personal Slack workspace, channel, and incoming webhook.
2. Put `SLACK_WEBHOOK_URL` in `.env`.
3. Run `python -m src.main test-alert`.
4. Add ForeUp auth values locally in `.env` only if needed.
5. Run `python -m src.main auth-check`.
6. Run `python -m src.main check-once --dry-run`.
7. Run `python -m src.main run --dry-run`.
8. Only after everything works, set `DRY_RUN=false` and run `python -m src.main run`.

Send one Slack test message:

```powershell
python -m src.main test-alert
```

Check ForeUp local auth/session status without sending alerts or marking slots seen:

```powershell
python -m src.main auth-check
```

Check the local ForeUp session and send Slack only if the session is invalid or the bearer token expires soon:

```powershell
python -m src.main session-watch
```

`session-watch` uses only the read-only ForeUp availability endpoint. If ForeUp returns `401` or `403`, it sends this Slack message at most once per cooldown window:

```text
ForeUp session expired. Refresh FOREUP_BEARER_TOKEN and FOREUP_COOKIE in local .env, then run python -m src.main auth-check.
```

The default cooldown is 6 hours. `auth-check` also decodes the local bearer token payload without verifying or printing the token and reports only expiration time, time remaining, and whether it expires soon. If token expiration is within 24 hours, it warns that the bearer token expires soon.

Dry-run once:

```powershell
python -m src.main check-once --dry-run
```

If ForeUp returns `401 Unauthorized`, the endpoint is reachable but requires a valid read-only browser session or other authorized context. Only add session values through `.env`, never in source code, and do not enable auth for anything beyond availability reads.

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

Run a short release-window watcher:

```powershell
python -m src.main release-watch
```

`release-watch` loops internally for a few minutes and exits. It uses the same read-only ForeUp availability endpoint, same filtering, same Firestore or SQLite dedupe, and the same dry-run rules as `check-once`.

## Priority Ranking

Matched tee times are scored and sorted before dry-run output or Slack alerts:

1. South, 18 holes, at or before `PRIORITY_SOUTH_18_BEFORE` default `15:30`.
2. South, any holes, at or before `PRIORITY_SOUTH_ANY_BEFORE` default `16:30`.
3. North, 18 holes, at or before `PRIORITY_NORTH_18_BEFORE` default `16:30`.
4. Any configured match at or before `LATEST_TIME`.
5. Later configured matches rank lower if `LATEST_TIME` is extended.

Priority labels are included in Slack alerts and dry-run output. Scoring does not affect tee-time identity or dedupe keys.

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

Keep request volume low. Use the release cadence only during a narrow expected release window, and prefer the normal cancellation cadence for all other monitoring. Do not reduce polling intervals unless you are certain the request volume remains respectful.

The run loop is sequential and does not create parallel ForeUp request bursts. It backs off on network errors, `401`, `403`, `429`, and server errors, and slows the next poll after a new match is found.

Release-watch defaults:

```dotenv
RELEASE_WATCH_DURATION_SECONDS=420
RELEASE_WATCH_INTERVAL_SECONDS=15
RELEASE_WATCH_JITTER_SECONDS=2
RELEASE_WATCH_MAX_RUNS=
```

Transient network and non-auth HTTP errors are logged with redacted messages and the loop continues. `401` or `403` auth/session failures stop the command with a non-zero exit code.

## Windows Task Scheduler

For local-only operation, run commands from your project directory with your virtual environment activated or use the virtual environment Python path directly. Create the `logs` folder first so output has somewhere local to go.

Normal monitoring example:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "cd C:\Users\conno\Documents\torrey-pines-booking; .\.venv\Scripts\python.exe -m src.main run *> .\logs\normal-watch.log"
```

Release-window watch example:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "cd C:\Users\conno\Documents\torrey-pines-booking; .\.venv\Scripts\python.exe -m src.main run *> .\logs\release-watch.log"
```

Suggested schedule:

- Normal watch: start at login or during the day, using the default 5-15 minute interval.
- Release watch: run only around the expected 6:58-7:05 PM Pacific window.

Logs should not print Slack webhook URLs, cookies, bearer tokens, or personal session values. Keep `.env` local and uncommitted.

## Google Cloud Run Jobs

Local runs use SQLite by default:

```dotenv
STATE_BACKEND=sqlite
```

Cloud Run Jobs use ephemeral containers, so SQLite files may disappear between scheduled executions. For Cloud Run Jobs, use Firestore for persistent seen-slot dedupe and session-alert cooldown state:

```dotenv
STATE_BACKEND=firestore
```

The Firestore backend uses:

- `torrey_seen_slots` for tee-time dedupe documents.
- `torrey_session_alerts` for session warning cooldown documents.

Seen-slot documents store only alert state such as `source_id`, `course`, `date`, `time`, `holes`, `players_available`, `first_seen_at`, and `alerted_at`. Session-alert documents store only alert keys and timestamps. Do not store Slack webhook URLs, ForeUp bearer tokens, ForeUp cookies, browser session values, or personal account data in Firestore.

Cloud setup outline:

1. Enable Firestore in the Google Cloud project.
2. Create or use the Artifact Registry Docker repository.
3. Build and push the container image with Cloud Build.
4. Run the Cloud Run Job service account with Firestore read/write access for the two collections above.
5. Set `STATE_BACKEND=firestore` in the Cloud Run Job environment.
6. Store Slack and ForeUp secrets only in a proper secret manager or local `.env` for local runs, never in source code or Firestore.
7. Keep the same conservative schedule and read-only endpoint restrictions used locally.

Cloud Build image command:

```bash
PROJECT_ID="lazydog-analytics"
REGION="us-west1"
REPO="torrey-pines"
IMAGE="torrey-monitor"

gcloud builds submit \
  --tag "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$IMAGE:latest"
```

Cloud Run Job notes:

- Image: `us-west1-docker.pkg.dev/lazydog-analytics/torrey-pines/torrey-monitor:latest`
- Normal monitor command: `python`
- Normal monitor args: `-m src.main check-once`
- Release-window command: `python`
- Release-window args: `-m src.main release-watch`
- Configure secrets and environment variables in Cloud Run, not in the repo or image.
- Keep `SLACK_WEBHOOK_URL`, `FOREUP_BEARER_TOKEN`, and `FOREUP_COOKIE` external through Cloud Run environment variables or Google Secret Manager.
- Do not commit `.env`, local databases, logs, or browser session values.

Suggested Cloud Scheduler jobs:

- Normal monitor, every 10 minutes: `*/10 * * * *`
- Release watch, once daily around 6:58 PM Pacific: `58 18 * * *`

Use the same container image for both Cloud Run Jobs and change only the command args. Keep `STATE_BACKEND=firestore` for Cloud Run Jobs so dedupe survives between executions.

## Tests

```powershell
pytest
```
