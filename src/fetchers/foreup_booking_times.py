from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode, urljoin

import requests

from src.config import WatchConfig
from src.fetchers.base import TeeTimeFetcher
from src.models import TeeTime

logger = logging.getLogger(__name__)

BLOCKLISTED_URL_PARTS = (
    "pending_reservation",
    "refresh_pending_reservation",
    "reservation",
    "cart",
    "checkout",
    "payment",
)

COURSE_ID = 19347


@dataclass(frozen=True, slots=True)
class ForeUpCourseProfile:
    course: str
    schedule_id: int
    booking_class: int


RESIDENT_PROFILES = (
    ForeUpCourseProfile(course="North", schedule_id=1468, booking_class=1135),
    ForeUpCourseProfile(course="South", schedule_id=1487, booking_class=888),
)


class BlocklistedForeUpUrlError(ValueError):
    pass


class AuthConfigurationError(ValueError):
    pass


class ForeUpBookingTimesFetcher(TeeTimeFetcher):
    def __init__(
        self,
        base_url: str = "https://foreupsoftware.com",
        timeout_seconds: int = 10,
        use_auth: bool = False,
        bearer_token: str | None = None,
        cookie: str | None = None,
        watch_courses: set[str] | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.use_auth = use_auth
        self.bearer_token = _sanitize_bearer_token(bearer_token) if use_auth and bearer_token else bearer_token
        self.cookie = _sanitize_cookie(cookie) if use_auth and cookie else cookie
        self.watch_courses = {course.lower() for course in watch_courses or {"north", "south"}}
        self.session = session or requests.Session()

    @classmethod
    def from_config(cls, config: WatchConfig) -> "ForeUpBookingTimesFetcher":
        return cls(
            base_url=config.foreup_base_url,
            timeout_seconds=config.foreup_timeout_seconds,
            use_auth=config.foreup_use_auth,
            bearer_token=config.foreup_bearer_token,
            cookie=config.foreup_cookie,
            watch_courses=config.watch_courses,
        )

    def fetch(self, target_dates: list[date]) -> list[TeeTime]:
        slots: list[TeeTime] = []
        for target_date in target_dates:
            for profile in self._active_profiles():
                payload = self._fetch_profile_date(profile, target_date)
                slots.extend(self._normalize_response(payload, profile))
        return slots

    def _active_profiles(self) -> list[ForeUpCourseProfile]:
        return [
            profile
            for profile in RESIDENT_PROFILES
            if profile.course.lower() in self.watch_courses
        ]

    def _availability_url(self) -> str:
        url = urljoin(f"{self.base_url}/", "index.php/api/booking/times")
        self._ensure_url_allowed(url)
        return url

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "torrey-pines-alert-monitor/1.0",
        }
        if not self.use_auth:
            return headers

        if not self.bearer_token or not self.cookie:
            raise AuthConfigurationError(
                "FOREUP_USE_AUTH=true requires FOREUP_BEARER_TOKEN and FOREUP_COOKIE. "
                "Values were not printed."
            )
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    def _params(self, profile: ForeUpCourseProfile, target_date: date) -> list[tuple[str, str]]:
        all_schedule_ids = ["1487", "1468"]
        params = [
            ("time", "all"),
            ("date", target_date.strftime("%m-%d-%Y")),
            ("holes", "all"),
            ("players", "0"),
            ("booking_class", str(profile.booking_class)),
            ("schedule_id", str(profile.schedule_id)),
        ]
        params.extend(("schedule_ids[]", schedule_id) for schedule_id in all_schedule_ids)
        params.extend(
            [
                ("specials_only", "0"),
                ("api_key", ""),
            ]
        )
        return params

    def _fetch_profile_date(
        self, profile: ForeUpCourseProfile, target_date: date
    ) -> list[dict[str, Any]]:
        url = self._availability_url()
        params = self._params(profile, target_date)
        self._ensure_url_allowed(f"{url}?{urlencode(params)}")

        logger.info(
            "Fetching ForeUp availability for %s on %s",
            profile.course,
            target_date.isoformat(),
        )
        response = self.request_profile_date(profile, target_date)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            logger.warning("ForeUp response was not a list; ignoring payload")
            return []
        return [item for item in payload if isinstance(item, dict)]

    def request_profile_date(
        self, profile: ForeUpCourseProfile, target_date: date
    ) -> requests.Response:
        url = self._availability_url()
        params = self._params(profile, target_date)
        self._ensure_url_allowed(f"{url}?{urlencode(params)}")
        return self.session.get(
            url,
            params=params,
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )

    def _normalize_response(
        self, payload: list[dict[str, Any]], profile: ForeUpCourseProfile
    ) -> list[TeeTime]:
        slots: list[TeeTime] = []
        for item in payload:
            tee_time = self._normalize_item(item, profile)
            if tee_time is not None:
                slots.append(tee_time)
        return slots

    def _normalize_item(
        self, item: dict[str, Any], profile: ForeUpCourseProfile
    ) -> TeeTime | None:
        try:
            tee_at = datetime.strptime(str(item["time"]), "%Y-%m-%d %H:%M")
            schedule_id = int(item.get("schedule_id", item.get("teesheet_id")))
            booking_class_id = int(item["booking_class_id"])
            players_available = int(item["available_spots"])
            holes = _optional_int(item.get("holes"))
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping malformed ForeUp tee time item: %s", exc)
            return None

        if schedule_id != profile.schedule_id:
            logger.warning(
                "ForeUp item schedule_id %s did not match requested %s for %s",
                schedule_id,
                profile.schedule_id,
                profile.course,
            )
        if booking_class_id != profile.booking_class:
            logger.warning(
                "ForeUp item booking_class_id %s did not match requested %s for %s",
                booking_class_id,
                profile.booking_class,
                profile.course,
            )

        price = _price_for_holes(item, holes)
        source_id = "|".join(
            [
                str(schedule_id),
                str(booking_class_id),
                str(item.get("start_front") or item["time"]),
                str(holes or ""),
            ]
        )
        booking_url = f"{self.base_url}/index.php/booking/{COURSE_ID}/{profile.schedule_id}"
        self._ensure_url_allowed(booking_url)

        return TeeTime(
            date=tee_at.date(),
            time=tee_at.time(),
            course=profile.course,
            players_available=players_available,
            holes=holes,
            side=item.get("teesheet_side_name"),
            price=price,
            booking_url=booking_url,
            source_id=source_id,
            metadata={
                "available_spots_9": item.get("available_spots_9"),
                "available_spots_18": item.get("available_spots_18"),
                "schedule_name": item.get("schedule_name"),
                "rate_type": item.get("rate_type"),
            },
        )

    @staticmethod
    def _ensure_url_allowed(url: str) -> None:
        lowered = url.lower()
        for blocked in BLOCKLISTED_URL_PARTS:
            if blocked in lowered:
                raise BlocklistedForeUpUrlError(
                    f"Refusing to call blocklisted ForeUp endpoint containing {blocked!r}"
                )


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _price_for_holes(item: dict[str, Any], holes: int | None) -> Any:
    if item.get("green_fee") is not None:
        return item.get("green_fee")
    if holes == 9 and item.get("green_fee_9") is not None:
        return item.get("green_fee_9")
    if holes == 18 and item.get("green_fee_18") is not None:
        return item.get("green_fee_18")
    return item.get("green_fee_9") or item.get("green_fee_18")


def _reject_header_newlines(value: str, env_name: str) -> None:
    if "\r" in value or "\n" in value:
        raise AuthConfigurationError(f"{env_name} contains invalid newline characters. Value was not printed.")


def _sanitize_bearer_token(value: str) -> str:
    cleaned = value.strip()
    _reject_header_newlines(cleaned, "FOREUP_BEARER_TOKEN")
    if cleaned.lower().startswith("bearer "):
        cleaned = cleaned[7:].strip()
        _reject_header_newlines(cleaned, "FOREUP_BEARER_TOKEN")
    if not cleaned:
        raise AuthConfigurationError("FOREUP_BEARER_TOKEN is empty after sanitization. Value was not printed.")
    return cleaned


def _sanitize_cookie(value: str) -> str:
    cleaned = value.strip()
    _reject_header_newlines(cleaned, "FOREUP_COOKIE")
    if cleaned.lower().startswith("cookie:"):
        cleaned = cleaned.split(":", 1)[1].strip()
        _reject_header_newlines(cleaned, "FOREUP_COOKIE")
    if not cleaned:
        raise AuthConfigurationError("FOREUP_COOKIE is empty after sanitization. Value was not printed.")
    return cleaned
