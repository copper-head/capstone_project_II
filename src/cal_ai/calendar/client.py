"""Google Calendar CRUD client with duplicate and conflict detection.

Provides :class:`GoogleCalendarClient`, a high-level wrapper around the
Google Calendar API that handles:

- **Create** -- insert events with duplicate and conflict checking.
- **Read** -- list events within a time range with pagination.
- **Update** -- update by event ID, or search-then-update by title and time.
- **Delete** -- delete by event ID, or search-then-delete by title and time.

Duplicate detection prevents inserting the same event twice (same title,
overlapping time).  Conflict detection warns about scheduling overlaps
but does not block creation.

All API calls are wrapped with the :func:`~cal_ai.calendar.exceptions.with_retry`
decorator for automatic retry on transient failures.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime, timedelta
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from cal_ai.calendar.event_mapper import map_to_google_event
from cal_ai.calendar.exceptions import with_retry
from cal_ai.models.extraction import ValidatedEvent

logger = logging.getLogger(__name__)

# Default time window used when listing events for duplicate/conflict checks.
_SEARCH_WINDOW = timedelta(hours=24)

# Google Calendar API calendar identifier for the primary calendar.
_PRIMARY_CALENDAR = "primary"


class GoogleCalendarClient:
    """High-level client for Google Calendar CRUD operations.

    Wraps the ``googleapiclient`` service resource and adds:

    - Duplicate detection before creating events.
    - Conflict detection (logged as warnings) before creating events.
    - Search-based update and delete by title and time window.
    - Automatic retry via ``@with_retry`` on all API methods.

    Args:
        credentials: Valid Google OAuth 2.0 credentials.
        timezone: IANA timezone string (e.g. ``"America/Vancouver"``).
        owner_email: The Google account email of the calendar owner.
        service: Optional pre-built ``googleapiclient`` service resource.
            If ``None``, one is built from *credentials*.  Pass a mock here
            in tests.
    """

    def __init__(
        self,
        credentials: Credentials,
        timezone: str,
        owner_email: str,
        service: Any | None = None,
    ) -> None:
        self._credentials = credentials
        self._timezone = timezone
        self._owner_email = owner_email
        self._service = service or build("calendar", "v3", credentials=credentials)

    # ------------------------------------------------------------------
    # Credential refresh hook (used by @with_retry on 401)
    # ------------------------------------------------------------------

    def _refresh_credentials(self) -> None:
        """Refresh the OAuth 2.0 credentials.

        Called automatically by the ``@with_retry`` decorator when the API
        returns HTTP 401.  Rebuilds the service resource with the refreshed
        credentials.
        """
        from google.auth.transport.requests import Request

        self._credentials.refresh(Request())
        self._service = build("calendar", "v3", credentials=self._credentials)
        logger.info("Credentials refreshed and service rebuilt")

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @with_retry()
    def create_event(self, event: ValidatedEvent) -> dict | None:
        """Create a new event on Google Calendar.

        Before inserting, checks for duplicates (same title + overlapping
        time).  If a duplicate is found the event is skipped.  Scheduling
        conflicts are logged as warnings but do not block creation.

        Args:
            event: The validated event to create.

        Returns:
            The API response ``dict`` for the created event, or ``None``
            if the event was skipped as a duplicate.
        """
        body = map_to_google_event(event, self._timezone, self._owner_email)

        # Fetch existing events in the surrounding time window for checks.
        window_start = event.start_time - _SEARCH_WINDOW
        window_end = event.end_time + _SEARCH_WINDOW
        existing = self._list_events_raw(window_start, window_end)

        # Duplicate check.
        duplicate = self._is_duplicate(event, existing)
        if duplicate is not None:
            logger.info(
                "Skipping duplicate event '%s' (matches existing '%s')",
                event.title,
                duplicate.get("summary", "?"),
            )
            return None

        # Conflict check (warn only).
        conflicts = self._find_conflicts(event, existing)
        if conflicts:
            titles = [c.get("summary", "?") for c in conflicts]
            logger.warning(
                "Event '%s' conflicts with %d existing event(s): %s",
                event.title,
                len(conflicts),
                ", ".join(titles),
            )

        result = (
            self._service.events()
            .insert(calendarId=_PRIMARY_CALENDAR, body=body)
            .execute()
        )
        logger.info(
            "Created event '%s' (id=%s)",
            event.title,
            result.get("id", "?"),
        )
        return result

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @with_retry()
    def list_events(
        self,
        time_min: datetime,
        time_max: datetime,
    ) -> list[dict]:
        """List events within a time range.

        Handles pagination automatically, fetching all pages of results.

        Args:
            time_min: Start of the time range (inclusive).
            time_max: End of the time range (exclusive).

        Returns:
            A list of Google Calendar event resource dicts.
        """
        events = self._list_events_raw(time_min, time_max)
        logger.info(
            "Listed %d event(s) between %s and %s",
            len(events),
            time_min.isoformat(),
            time_max.isoformat(),
        )
        return events

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    @with_retry()
    def update_event(self, event_id: str, event: ValidatedEvent) -> dict:
        """Update an existing event by its ID.

        Args:
            event_id: The Google Calendar event ID.
            event: The validated event containing the updated data.

        Returns:
            The API response ``dict`` for the updated event.

        Raises:
            CalendarNotFoundError: If the event ID does not exist.
        """
        body = map_to_google_event(event, self._timezone, self._owner_email)
        result = (
            self._service.events()
            .update(calendarId=_PRIMARY_CALENDAR, eventId=event_id, body=body)
            .execute()
        )
        logger.info("Updated event '%s' (id=%s)", event.title, event_id)
        return result

    @with_retry()
    def find_and_update_event(self, event: ValidatedEvent) -> dict | None:
        """Search for an existing event by title and time, then update it.

        Looks for events with a matching title (case-insensitive) that
        overlap with the event's time range.  If a match is found, it is
        updated with the new event data.

        Args:
            event: The validated event containing the updated data and
                search criteria (title + time).

        Returns:
            The API response ``dict`` for the updated event, or ``None``
            if no matching event was found.
        """
        window_start = event.start_time - _SEARCH_WINDOW
        window_end = event.end_time + _SEARCH_WINDOW
        existing = self._list_events_raw(window_start, window_end)

        match = self._find_by_title_and_time(event, existing)
        if match is None:
            logger.warning(
                "No existing event found matching '%s' for update",
                event.title,
            )
            return None

        body = map_to_google_event(event, self._timezone, self._owner_email)
        result = (
            self._service.events()
            .update(
                calendarId=_PRIMARY_CALENDAR,
                eventId=match["id"],
                body=body,
            )
            .execute()
        )
        logger.info(
            "Found and updated event '%s' (id=%s)",
            event.title,
            match["id"],
        )
        return result

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    @with_retry()
    def delete_event(self, event_id: str) -> None:
        """Delete an event by its ID.

        Args:
            event_id: The Google Calendar event ID.

        Raises:
            CalendarNotFoundError: If the event ID does not exist.
        """
        self._service.events().delete(
            calendarId=_PRIMARY_CALENDAR, eventId=event_id
        ).execute()
        logger.info("Deleted event (id=%s)", event_id)

    @with_retry()
    def find_and_delete_event(self, event: ValidatedEvent) -> bool:
        """Search for an existing event by title and time, then delete it.

        Looks for events with a matching title (case-insensitive) that
        overlap with the event's time range.

        Args:
            event: The validated event containing the search criteria
                (title + time).

        Returns:
            ``True`` if a matching event was found and deleted, ``False``
            if no match was found.
        """
        window_start = event.start_time - _SEARCH_WINDOW
        window_end = event.end_time + _SEARCH_WINDOW
        existing = self._list_events_raw(window_start, window_end)

        match = self._find_by_title_and_time(event, existing)
        if match is None:
            logger.warning(
                "No existing event found matching '%s' for delete",
                event.title,
            )
            return False

        self._service.events().delete(
            calendarId=_PRIMARY_CALENDAR, eventId=match["id"]
        ).execute()
        logger.info(
            "Found and deleted event '%s' (id=%s)",
            event.title,
            match["id"],
        )
        return True

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    @staticmethod
    def _is_duplicate(
        event: ValidatedEvent,
        existing_events: list[dict],
    ) -> dict | None:
        """Check whether *event* is a duplicate of any existing event.

        A duplicate is defined as an existing event with:

        - The **same title** (case-insensitive comparison), AND
        - **Overlapping time** (``event_a.start < event_b.end AND
          event_b.start < event_a.end``).

        Same title with different time, or different title with the same
        time, are NOT considered duplicates.

        Args:
            event: The candidate event to check.
            existing_events: List of Google Calendar event resource dicts.

        Returns:
            The first matching existing event ``dict``, or ``None`` if no
            duplicate is found.
        """
        for existing in existing_events:
            existing_title = existing.get("summary", "")
            if existing_title.lower() != event.title.lower():
                continue

            # Parse existing event times.
            ex_start, ex_end = _parse_event_times(existing)
            if ex_start is None or ex_end is None:
                continue

            # Overlap check: a.start < b.end AND b.start < a.end
            if event.start_time < ex_end and ex_start < event.end_time:
                return existing

        return None

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    @staticmethod
    def _find_conflicts(
        event: ValidatedEvent,
        existing_events: list[dict],
    ) -> list[dict]:
        """Find all existing events that conflict with *event*.

        A conflict is any existing event with overlapping time, regardless
        of title.  This differs from duplicate detection which also
        requires a title match.

        Adjacent events (where one ends exactly when the other starts)
        are NOT considered conflicts.

        Args:
            event: The candidate event to check.
            existing_events: List of Google Calendar event resource dicts.

        Returns:
            A list of conflicting existing event dicts (may be empty).
        """
        conflicts: list[dict] = []

        for existing in existing_events:
            ex_start, ex_end = _parse_event_times(existing)
            if ex_start is None or ex_end is None:
                continue

            # Strict overlap: a.start < b.end AND b.start < a.end
            if event.start_time < ex_end and ex_start < event.end_time:
                conflicts.append(existing)

        return conflicts

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _list_events_raw(
        self,
        time_min: datetime,
        time_max: datetime,
    ) -> list[dict]:
        """Fetch events from the API with pagination.

        This is the low-level paginated fetch used by all methods that need
        to read existing events.  It is NOT decorated with ``@with_retry``
        because the public callers already have retry.

        Args:
            time_min: Start of the time range.
            time_max: End of the time range.

        Returns:
            A flat list of event resource dicts from all pages.
        """
        all_events: list[dict] = []
        page_token: str | None = None

        while True:
            response = (
                self._service.events()
                .list(
                    calendarId=_PRIMARY_CALENDAR,
                    timeMin=time_min.isoformat() + "Z",
                    timeMax=time_max.isoformat() + "Z",
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=page_token,
                )
                .execute()
            )

            items = response.get("items", [])
            all_events.extend(items)

            page_token = response.get("nextPageToken")
            if page_token is None:
                break

        return all_events

    @staticmethod
    def _find_by_title_and_time(
        event: ValidatedEvent,
        existing_events: list[dict],
    ) -> dict | None:
        """Find an existing event matching by title and overlapping time.

        Used by ``find_and_update_event`` and ``find_and_delete_event`` to
        locate the target event.

        Args:
            event: The event with title and time to match.
            existing_events: List of Google Calendar event resource dicts.

        Returns:
            The first matching event, or ``None``.
        """
        for existing in existing_events:
            existing_title = existing.get("summary", "")
            if existing_title.lower() != event.title.lower():
                continue

            ex_start, ex_end = _parse_event_times(existing)
            if ex_start is None or ex_end is None:
                continue

            if event.start_time < ex_end and ex_start < event.end_time:
                return existing

        return None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _parse_event_times(
    event_dict: dict,
) -> tuple[datetime | None, datetime | None]:
    """Extract start and end datetimes from a Google Calendar event dict.

    Handles both ``dateTime`` (timed events) and ``date`` (all-day events)
    fields in the Google Calendar API response.

    Args:
        event_dict: A Google Calendar event resource dict.

    Returns:
        A ``(start, end)`` tuple.  Either value may be ``None`` if the
        corresponding field is missing or cannot be parsed.
    """
    start_str = None
    end_str = None

    start_obj = event_dict.get("start", {})
    end_obj = event_dict.get("end", {})

    start_str = start_obj.get("dateTime") or start_obj.get("date")
    end_str = end_obj.get("dateTime") or end_obj.get("date")

    start_dt = None
    end_dt = None

    if start_str is not None:
        with contextlib.suppress(ValueError):
            start_dt = datetime.fromisoformat(start_str)
            # Strip tzinfo so comparisons with naive ValidatedEvent datetimes work.
            if start_dt.tzinfo is not None:
                start_dt = start_dt.replace(tzinfo=None)

    if end_str is not None:
        with contextlib.suppress(ValueError):
            end_dt = datetime.fromisoformat(end_str)
            if end_dt.tzinfo is not None:
                end_dt = end_dt.replace(tzinfo=None)

    return start_dt, end_dt
