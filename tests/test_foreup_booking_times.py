from __future__ import annotations

from datetime import date

import pytest

from src.fetchers.foreup_booking_times import (
    BlocklistedForeUpUrlError,
    ForeUpBookingTimesFetcher,
    ForeUpCourseProfile,
)


SAMPLE_ITEM = {
    "time": "2026-06-20 16:57",
    "start_front": 202606201657,
    "course_id": 19347,
    "course_name": "Torrey Pines Golf Course",
    "schedule_id": 1468,
    "teesheet_id": 1468,
    "schedule_name": "Torrey Pines North",
    "teesheet_side_name": "Front",
    "reround_teesheet_side_name": "Back",
    "available_spots": 1,
    "available_spots_9": 1,
    "available_spots_18": 0,
    "allowed_group_sizes": ["1", "2", "3", "4"],
    "holes": 9,
    "booking_class_id": 1135,
    "green_fee": 123,
    "green_fee_9": 123,
    "green_fee_18": 0,
    "cart_fee": 0,
    "rate_type": "walking",
    "require_credit_card": False,
    "pay_online": "no",
}


class FakeResponse:
    def __init__(self, payload) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload) -> None:
        self.payload = payload
        self.calls = []

    def get(self, url, params, headers, timeout):
        self.calls.append(
            {"url": url, "params": params, "headers": headers, "timeout": timeout}
        )
        return FakeResponse(self.payload)


def test_parses_provided_response_fixture() -> None:
    fetcher = ForeUpBookingTimesFetcher(session=FakeSession([]))
    profile = ForeUpCourseProfile(course="North", schedule_id=1468, booking_class=1135)

    slots = fetcher._normalize_response([SAMPLE_ITEM], profile)

    assert len(slots) == 1


def test_normalizes_date_time() -> None:
    fetcher = ForeUpBookingTimesFetcher(session=FakeSession([]))
    profile = ForeUpCourseProfile(course="North", schedule_id=1468, booking_class=1135)

    slot = fetcher._normalize_response([SAMPLE_ITEM], profile)[0]

    assert slot.date_iso == "2026-06-20"
    assert slot.time_hhmm == "16:57"


def test_north_profile_mapping() -> None:
    fetcher = ForeUpBookingTimesFetcher(session=FakeSession([]))
    profile = ForeUpCourseProfile(course="North", schedule_id=1468, booking_class=1135)

    slot = fetcher._normalize_response([SAMPLE_ITEM], profile)[0]

    assert slot.course == "North"
    assert slot.booking_url == "https://foreupsoftware.com/index.php/booking/19347/1468"
    assert slot.source_id == "1468|1135|202606201657|9"


def test_available_spots_mapping() -> None:
    fetcher = ForeUpBookingTimesFetcher(session=FakeSession([]))
    profile = ForeUpCourseProfile(course="North", schedule_id=1468, booking_class=1135)

    slot = fetcher._normalize_response([SAMPLE_ITEM], profile)[0]

    assert slot.players_available == 1
    assert slot.metadata == {
        "available_spots_9": 1,
        "available_spots_18": 0,
        "schedule_name": "Torrey Pines North",
        "rate_type": "walking",
    }


def test_green_fee_mapping() -> None:
    fetcher = ForeUpBookingTimesFetcher(session=FakeSession([]))
    profile = ForeUpCourseProfile(course="North", schedule_id=1468, booking_class=1135)

    slot = fetcher._normalize_response([SAMPLE_ITEM], profile)[0]

    assert slot.price == 123
    assert slot.holes == 9
    assert slot.side == "Front"


def test_fetch_empty_response() -> None:
    session = FakeSession([])
    fetcher = ForeUpBookingTimesFetcher(session=session)

    assert fetcher.fetch([date(2026, 6, 20)]) == []
    assert len(session.calls) == 2
    assert ("schedule_ids[]", "1487") in session.calls[0]["params"]
    assert ("schedule_ids[]", "1468") in session.calls[0]["params"]


def test_malformed_missing_fields_are_skipped() -> None:
    fetcher = ForeUpBookingTimesFetcher(session=FakeSession([]))
    profile = ForeUpCourseProfile(course="North", schedule_id=1468, booking_class=1135)

    assert fetcher._normalize_response([{"time": "2026-06-20 16:57"}], profile) == []


def test_blocklisted_url_protection() -> None:
    with pytest.raises(BlocklistedForeUpUrlError):
        ForeUpBookingTimesFetcher._ensure_url_allowed(
            "https://foreupsoftware.com/index.php/api/booking/pending_reservation"
        )


def test_auth_headers_not_sent_unless_enabled() -> None:
    session = FakeSession([])
    fetcher = ForeUpBookingTimesFetcher(
        session=session,
        bearer_token="secret-token",
        cookie="session-cookie-value",
    )

    fetcher.fetch([date(2026, 6, 20)])

    assert "Authorization" not in session.calls[0]["headers"]
    assert "Cookie" not in session.calls[0]["headers"]


def test_auth_headers_are_loaded_from_environment_config_when_enabled() -> None:
    session = FakeSession([])
    fetcher = ForeUpBookingTimesFetcher(
        session=session,
        use_auth=True,
        bearer_token="secret-token",
        cookie="session-cookie-value",
        watch_courses={"north"},
    )

    fetcher.fetch([date(2026, 6, 20)])

    assert session.calls[0]["headers"]["Authorization"] == "Bearer secret-token"
    assert session.calls[0]["headers"]["Cookie"] == "session-cookie-value"
