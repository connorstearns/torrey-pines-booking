from __future__ import annotations

import pytest

from src.fetchers.foreup_booking_times import (
    AuthConfigurationError,
    ForeUpBookingTimesFetcher,
)


def test_token_with_bearer_prefix_is_sanitized() -> None:
    fetcher = ForeUpBookingTimesFetcher(use_auth=True, bearer_token="Bearer token-value", cookie="a=b")

    assert fetcher._headers()["Authorization"] == "Bearer token-value"


def test_cookie_with_cookie_prefix_is_sanitized() -> None:
    fetcher = ForeUpBookingTimesFetcher(use_auth=True, bearer_token="token-value", cookie="Cookie: a=b")

    assert fetcher._headers()["Cookie"] == "a=b"


def test_trailing_whitespace_is_sanitized() -> None:
    fetcher = ForeUpBookingTimesFetcher(use_auth=True, bearer_token=" token-value ", cookie=" a=b ")

    assert fetcher._headers()["Authorization"] == "Bearer token-value"
    assert fetcher._headers()["Cookie"] == "a=b"


def test_newline_in_token_is_rejected_without_printing_secret() -> None:
    with pytest.raises(AuthConfigurationError) as exc:
        ForeUpBookingTimesFetcher(use_auth=True, bearer_token="secret\nvalue", cookie="a=b")

    assert "secret" not in str(exc.value)
    assert "Value was not printed" in str(exc.value)


def test_newline_in_cookie_is_rejected_without_printing_secret() -> None:
    with pytest.raises(AuthConfigurationError) as exc:
        ForeUpBookingTimesFetcher(use_auth=True, bearer_token="token", cookie="secret\rvalue")

    assert "secret" not in str(exc.value)
    assert "Value was not printed" in str(exc.value)
