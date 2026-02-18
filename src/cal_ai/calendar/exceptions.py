"""Custom exceptions and retry logic for Google Calendar API operations.

Defines a hierarchy of calendar-specific exceptions and a ``@with_retry``
decorator that handles transient failures (rate limits, expired tokens,
network errors) with exponential backoff.

Exception hierarchy::

    CalendarAPIError          (base for all Calendar API errors)
    +-- CalendarAuthError     (authentication / 401 failures)
    +-- CalendarRateLimitError (HTTP 429 rate-limit responses)
    +-- CalendarNotFoundError (HTTP 404 on update/delete)
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# ---------------------------------------------------------------------------
# Exception classes
# ---------------------------------------------------------------------------


class CalendarAPIError(Exception):
    """Base exception for Google Calendar API errors.

    Attributes:
        status_code: HTTP status code from the API, or ``None`` if the
            error did not originate from an HTTP response.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CalendarAuthError(CalendarAPIError):
    """Raised when Calendar API authentication fails.

    Covers HTTP 401 responses and token refresh failures.
    """

    def __init__(self, message: str = "Calendar authentication failed") -> None:
        super().__init__(message, status_code=401)


class CalendarRateLimitError(CalendarAPIError):
    """Raised when the Calendar API returns HTTP 429 (rate limit exceeded).

    The caller should back off before retrying.
    """

    def __init__(self, message: str = "Calendar API rate limit exceeded") -> None:
        super().__init__(message, status_code=429)


class CalendarNotFoundError(CalendarAPIError):
    """Raised when a Calendar resource is not found (HTTP 404).

    Typically occurs when updating or deleting an event that no longer exists.
    """

    def __init__(self, message: str = "Calendar resource not found") -> None:
        super().__init__(message, status_code=404)


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BASE_DELAY = 1.0  # seconds
_AUTH_RETRY_LIMIT = 1  # 401 gets one retry after token refresh


def _classify_http_error(error: HttpError) -> CalendarAPIError:
    """Map an ``HttpError`` to the appropriate calendar exception.

    Args:
        error: The ``googleapiclient.errors.HttpError`` to classify.

    Returns:
        A :class:`CalendarAPIError` subclass matching the HTTP status code.
    """
    status = error.resp.status

    if status == 404:
        return CalendarNotFoundError(str(error))
    if status == 429:
        return CalendarRateLimitError(str(error))
    if status == 401:
        return CalendarAuthError(str(error))
    return CalendarAPIError(str(error), status_code=status)


def with_retry(
    max_retries: int = _DEFAULT_MAX_RETRIES,
    base_delay: float = _DEFAULT_BASE_DELAY,
) -> Callable[[F], F]:
    """Decorator that retries Calendar API calls on transient failures.

    Retry policy:
    - **HTTP 429** (rate limit): exponential backoff, up to *max_retries*.
    - **HTTP 401** (auth expired): refresh credentials via
      ``self._refresh_credentials()`` (if available), retry once.
    - **Network errors** (``OSError``, ``TimeoutError``): exponential
      backoff, up to *max_retries*.
    - **HTTP 404**: raise :class:`CalendarNotFoundError` immediately (no retry).
    - Other HTTP errors: raise :class:`CalendarAPIError` immediately.

    The decorated function must be a method on an object. If the object
    has a ``_refresh_credentials`` method, it will be called on 401 errors
    before the single auth retry.

    Args:
        max_retries: Maximum number of retry attempts for rate-limit and
            network errors.  Defaults to 3.
        base_delay: Initial backoff delay in seconds.  Doubled on each
            subsequent retry.  Defaults to 1.0.

    Returns:
        A decorator that wraps the target function with retry logic.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            auth_retries = 0

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except HttpError as exc:
                    cal_error = _classify_http_error(exc)

                    # 404 -- never retry
                    if isinstance(cal_error, CalendarNotFoundError):
                        logger.error("Resource not found (404): %s", exc)
                        raise cal_error from exc

                    # 429 -- exponential backoff
                    if isinstance(cal_error, CalendarRateLimitError):
                        if attempt >= max_retries:
                            logger.error(
                                "Rate limit exceeded after %d retries: %s",
                                max_retries,
                                exc,
                            )
                            raise cal_error from exc
                        delay = base_delay * (2**attempt)
                        logger.warning(
                            "Rate limited (429), retrying in %.1fs (attempt %d/%d)",
                            delay,
                            attempt + 1,
                            max_retries,
                        )
                        time.sleep(delay)
                        continue

                    # 401 -- refresh credentials, retry once
                    if isinstance(cal_error, CalendarAuthError):
                        if auth_retries >= _AUTH_RETRY_LIMIT:
                            logger.error("Auth failed after token refresh: %s", exc)
                            raise cal_error from exc
                        auth_retries += 1
                        logger.warning("Auth expired (401), attempting token refresh")
                        # Try to refresh credentials if the method exists.
                        instance = args[0] if args else None
                        refresh = getattr(instance, "_refresh_credentials", None)
                        if callable(refresh):
                            try:
                                refresh()
                            except Exception as refresh_exc:
                                logger.error("Token refresh failed: %s", refresh_exc)
                                raise CalendarAuthError(
                                    f"Token refresh failed: {refresh_exc}"
                                ) from refresh_exc
                        else:
                            logger.warning("No _refresh_credentials method available")
                        continue

                    # Other HTTP errors -- no retry
                    logger.error("Calendar API error (HTTP %s): %s", cal_error.status_code, exc)
                    raise cal_error from exc

                except (OSError, TimeoutError) as exc:
                    if attempt >= max_retries:
                        logger.error(
                            "Network error after %d retries: %s",
                            max_retries,
                            exc,
                        )
                        raise CalendarAPIError(
                            f"Network error after {max_retries} retries: {exc}"
                        ) from exc
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "Network error, retrying in %.1fs (attempt %d/%d): %s",
                        delay,
                        attempt + 1,
                        max_retries,
                        exc,
                    )
                    time.sleep(delay)
                    continue

            # Should not be reached, but as a safety net:
            raise CalendarAPIError("Retry loop exhausted unexpectedly")  # pragma: no cover

        return wrapper  # type: ignore[return-value]

    return decorator
