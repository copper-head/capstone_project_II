"""Tests for custom exceptions and the ``@with_retry`` decorator.

Covers the exception hierarchy in :mod:`cal_ai.calendar.exceptions` and the
``@with_retry`` decorator's handling of transient HTTP errors, auth failures,
network timeouts, and non-retryable 404 responses.

Test matrix (9 tests):

| Test | Scenario | Expected |
|---|---|---|
| test_api_rate_limit_429_retries | HTTP 429 once, then OK | Retries, succeeds on 2nd call |
| test_api_rate_limit_429_max_retries_exceeded | HTTP 429 four times | Raises CalendarRateLimitError |
| test_api_auth_expired_401_triggers_refresh | HTTP 401 once | Refreshes token, retries, succeeds |
| test_api_auth_expired_401_refresh_fails | HTTP 401, refresh fails | Raises CalendarAuthError |
| test_network_timeout_retries | Timeout once, then OK | Retries, succeeds |
| test_network_timeout_max_retries_exceeded | Timeout four times | Raises CalendarAPIError |
| test_event_not_found_404_on_delete | HTTP 404 on delete | Raises CalendarNotFoundError |
| test_event_not_found_404_on_update | HTTP 404 on update | Raises CalendarNotFoundError |
| test_invalid_event_data_raises_validation_error | start > end | Raises ValueError, no API call |
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from cal_ai.calendar.exceptions import (
    CalendarAPIError,
    CalendarAuthError,
    CalendarNotFoundError,
    CalendarRateLimitError,
    with_retry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_http_error(status: int) -> HttpError:
    """Create a ``googleapiclient.errors.HttpError`` with the given status code."""
    resp = Response({"status": str(status)})
    return HttpError(resp, b"simulated error")


class _FakeClient:
    """Minimal stand-in for ``GoogleCalendarClient`` used to test ``@with_retry``.

    The decorator expects the first positional arg (``self``) to optionally
    have a ``_refresh_credentials`` method.
    """

    def __init__(self, *, refresh_side_effect: Exception | None = None) -> None:
        self._refresh_called = 0
        self._refresh_side_effect = refresh_side_effect

    def _refresh_credentials(self) -> None:
        self._refresh_called += 1
        if self._refresh_side_effect is not None:
            raise self._refresh_side_effect


class _FakeClientNoRefresh:
    """Client without ``_refresh_credentials`` -- simulates missing hook."""


# ---------------------------------------------------------------------------
# Rate limit (429)
# ---------------------------------------------------------------------------


class TestApiRateLimit429Retries:
    """HTTP 429 once, then success on the next attempt."""

    def test_api_rate_limit_429_retries(self) -> None:
        """Decorator retries after a single 429 and returns success."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.0)
        def api_call(self_arg: object) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _make_http_error(429)
            return "ok"

        result = api_call(_FakeClient())

        assert result == "ok"
        assert call_count == 2


class TestApiRateLimit429MaxRetriesExceeded:
    """HTTP 429 on every attempt -- exceeds max retries."""

    def test_api_rate_limit_429_max_retries_exceeded(self) -> None:
        """CalendarRateLimitError is raised after exhausting all retries."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.0)
        def api_call(self_arg: object) -> str:
            nonlocal call_count
            call_count += 1
            raise _make_http_error(429)

        with pytest.raises(CalendarRateLimitError):
            api_call(_FakeClient())

        # 1 initial attempt + 3 retries = 4 total calls
        assert call_count == 4


# ---------------------------------------------------------------------------
# Auth expired (401)
# ---------------------------------------------------------------------------


class TestApiAuthExpired401TriggersRefresh:
    """HTTP 401 triggers _refresh_credentials, then retries successfully."""

    def test_api_auth_expired_401_triggers_refresh(self) -> None:
        """Token is refreshed and the retried call succeeds."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.0)
        def api_call(self_arg: object) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _make_http_error(401)
            return "refreshed-ok"

        client = _FakeClient()
        result = api_call(client)

        assert result == "refreshed-ok"
        assert call_count == 2
        assert client._refresh_called == 1


class TestApiAuthExpired401RefreshFails:
    """HTTP 401 triggers refresh, but refresh itself raises an error."""

    def test_api_auth_expired_401_refresh_fails(self) -> None:
        """CalendarAuthError is raised when token refresh fails."""

        @with_retry(max_retries=3, base_delay=0.0)
        def api_call(self_arg: object) -> str:
            raise _make_http_error(401)

        client = _FakeClient(refresh_side_effect=RuntimeError("refresh broken"))

        with pytest.raises(CalendarAuthError, match="refresh"):
            api_call(client)

        assert client._refresh_called == 1


# ---------------------------------------------------------------------------
# Network timeout / OSError
# ---------------------------------------------------------------------------


class TestNetworkTimeoutRetries:
    """Network timeout once, then success."""

    def test_network_timeout_retries(self) -> None:
        """Decorator retries after a single TimeoutError and succeeds."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.0)
        def api_call(self_arg: object) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("connection timed out")
            return "recovered"

        result = api_call(_FakeClient())

        assert result == "recovered"
        assert call_count == 2


class TestNetworkTimeoutMaxRetriesExceeded:
    """Network timeout on every attempt -- exceeds max retries."""

    def test_network_timeout_max_retries_exceeded(self) -> None:
        """CalendarAPIError is raised after exhausting all network retries."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.0)
        def api_call(self_arg: object) -> str:
            nonlocal call_count
            call_count += 1
            raise TimeoutError("connection timed out")

        with pytest.raises(CalendarAPIError, match="Network error"):
            api_call(_FakeClient())

        # 1 initial attempt + 3 retries = 4 total calls
        assert call_count == 4


# ---------------------------------------------------------------------------
# Not found (404) -- no retry
# ---------------------------------------------------------------------------


class TestEventNotFound404OnDelete:
    """HTTP 404 when deleting an event raises immediately (no retry)."""

    def test_event_not_found_404_on_delete(self) -> None:
        """CalendarNotFoundError is raised immediately without retry."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.0)
        def delete_call(self_arg: object) -> None:
            nonlocal call_count
            call_count += 1
            raise _make_http_error(404)

        with pytest.raises(CalendarNotFoundError):
            delete_call(_FakeClient())

        # 404 is never retried -- exactly 1 call.
        assert call_count == 1


class TestEventNotFound404OnUpdate:
    """HTTP 404 when updating an event raises immediately (no retry)."""

    def test_event_not_found_404_on_update(self) -> None:
        """CalendarNotFoundError is raised immediately without retry."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.0)
        def update_call(self_arg: object) -> None:
            nonlocal call_count
            call_count += 1
            raise _make_http_error(404)

        with pytest.raises(CalendarNotFoundError):
            update_call(_FakeClient())

        # 404 is never retried -- exactly 1 call.
        assert call_count == 1


# ---------------------------------------------------------------------------
# Validation: start_time > end_time
# ---------------------------------------------------------------------------


class TestInvalidEventDataRaisesValidationError:
    """start_time after end_time should fail before any API call."""

    def test_invalid_event_data_raises_validation_error(self) -> None:
        """Creating a ValidatedEvent with start > end raises ValueError."""
        from cal_ai.models.extraction import ValidatedEvent

        # Attempt to create an event where start is after end.
        # ValidatedEvent itself does not enforce this, so the validation
        # lives in the event_mapper or client layer.  We test that the
        # map_to_google_event function catches it.
        from cal_ai.calendar.event_mapper import map_to_google_event

        event = ValidatedEvent(
            title="Bad Event",
            start_time=datetime(2026, 3, 10, 12, 0),
            end_time=datetime(2026, 3, 10, 10, 0),  # end before start
            confidence="high",
            reasoning="test",
            assumptions=[],
            action="create",
        )

        with pytest.raises(ValueError, match="start_time.*end_time|end.*before.*start|end_time.*start_time"):
            map_to_google_event(event, "America/Vancouver", "owner@example.com")
