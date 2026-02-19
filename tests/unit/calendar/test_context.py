"""Tests for the calendar context fetcher and ID remapping module.

Covers :class:`~cal_ai.calendar.context.CalendarContext` and
:func:`~cal_ai.calendar.context.fetch_calendar_context`:

Test matrix (8 tests):

Normal Fetch (3):
| test_fetch_with_events             | Multi events  | Text + ID map |
| test_events_sorted_chronologically | Wrong order   | Sorted output |
| test_event_with_location           | Has location  | In output     |

Empty Calendar (1):
| test_fetch_empty_calendar          | No events     | count=0       |

Fetch Error (1):
| test_fetch_error_returns_empty     | API error     | Empty + warn  |

ID Mapping (2):
| test_id_map_integers_start_at_one  | Multi events  | Keys 1,2,3    |
| test_id_map_reverse_lookup         | Known IDs     | Correct UUID  |

Edge Cases (1):
| test_all_day_event_formatting      | All-day event | Date field OK |
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from cal_ai.calendar.context import fetch_calendar_context

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TIMEZONE = "America/Vancouver"
OWNER_EMAIL = "owner@example.com"


def _make_google_event(
    summary: str,
    start: datetime,
    end: datetime,
    event_id: str = "evt-1",
    location: str | None = None,
) -> dict:
    """Build a dict resembling a Google Calendar API event resource."""
    event: dict = {
        "id": event_id,
        "summary": summary,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    if location is not None:
        event["location"] = location
    return event


def _make_all_day_event(
    summary: str,
    date: str,
    event_id: str = "evt-allday",
) -> dict:
    """Build a dict resembling a Google Calendar all-day event."""
    return {
        "id": event_id,
        "summary": summary,
        "start": {"date": date},
        "end": {"date": date},
    }


def _make_mock_client(
    events: list[dict] | None = None,
    error: Exception | None = None,
) -> MagicMock:
    """Create a mock GoogleCalendarClient.

    Args:
        events: Events to return from list_events().
        error: Exception to raise from list_events().
    """
    client = MagicMock()
    if error is not None:
        client.list_events.side_effect = error
    elif events is not None:
        client.list_events.return_value = events
    else:
        client.list_events.return_value = []
    return client


# ===========================================================================
# Normal Fetch (3 tests)
# ===========================================================================


class TestFetchWithEvents:
    """Multiple events returned from calendar."""

    def test_fetch_with_events(self) -> None:
        """Formatted text contains all events, event_count is correct."""
        events = [
            _make_google_event(
                "Team Standup",
                datetime(2026, 3, 10, 9, 0),
                datetime(2026, 3, 10, 10, 0),
                event_id="gcal-abc",
            ),
            _make_google_event(
                "Lunch with Alice",
                datetime(2026, 3, 10, 12, 0),
                datetime(2026, 3, 10, 13, 0),
                event_id="gcal-def",
            ),
        ]
        client = _make_mock_client(events=events)
        now = datetime(2026, 3, 10, 0, 0)

        ctx = fetch_calendar_context(client, now)

        assert ctx.event_count == 2
        assert "Team Standup" in ctx.events_text
        assert "Lunch with Alice" in ctx.events_text
        assert "[1]" in ctx.events_text
        assert "[2]" in ctx.events_text


class TestEventsSortedChronologically:
    """Events are sorted by start time regardless of API order."""

    def test_events_sorted_chronologically(self) -> None:
        """Later event appears after earlier event in formatted text."""
        events = [
            _make_google_event(
                "Afternoon Meeting",
                datetime(2026, 3, 10, 14, 0),
                datetime(2026, 3, 10, 15, 0),
                event_id="gcal-later",
            ),
            _make_google_event(
                "Morning Standup",
                datetime(2026, 3, 10, 9, 0),
                datetime(2026, 3, 10, 10, 0),
                event_id="gcal-earlier",
            ),
        ]
        client = _make_mock_client(events=events)
        now = datetime(2026, 3, 10, 0, 0)

        ctx = fetch_calendar_context(client, now)

        lines = ctx.events_text.strip().split("\n")
        assert len(lines) == 2
        # Morning event should be first (ID 1), afternoon second (ID 2).
        assert "Morning Standup" in lines[0]
        assert "[1]" in lines[0]
        assert "Afternoon Meeting" in lines[1]
        assert "[2]" in lines[1]
        # ID map should reflect sorted order.
        assert ctx.id_map[1] == "gcal-earlier"
        assert ctx.id_map[2] == "gcal-later"


class TestEventWithLocation:
    """Event with a location field includes it in the formatted line."""

    def test_event_with_location(self) -> None:
        """Location appears as the third pipe-separated segment."""
        events = [
            _make_google_event(
                "Coffee Chat",
                datetime(2026, 3, 10, 10, 0),
                datetime(2026, 3, 10, 11, 0),
                event_id="gcal-loc",
                location="Starbucks on Main St",
            ),
        ]
        client = _make_mock_client(events=events)
        now = datetime(2026, 3, 10, 0, 0)

        ctx = fetch_calendar_context(client, now)

        assert "Starbucks on Main St" in ctx.events_text
        # The format should have three pipe-separated parts.
        assert ctx.events_text.count("|") == 2


# ===========================================================================
# Empty Calendar (1 test)
# ===========================================================================


class TestFetchEmptyCalendar:
    """Calendar has no events in the window."""

    def test_fetch_empty_calendar(self) -> None:
        """Returns empty context with event_count=0."""
        client = _make_mock_client(events=[])
        now = datetime(2026, 3, 10, 0, 0)

        ctx = fetch_calendar_context(client, now)

        assert ctx.event_count == 0
        assert ctx.events_text == ""
        assert ctx.id_map == {}


# ===========================================================================
# Fetch Error (1 test)
# ===========================================================================


class TestFetchErrorReturnsEmpty:
    """API raises an exception during fetch."""

    def test_fetch_error_returns_empty(self) -> None:
        """Returns empty context and logs a warning on fetch failure."""
        client = _make_mock_client(error=RuntimeError("Network timeout"))
        now = datetime(2026, 3, 10, 0, 0)

        with patch("cal_ai.calendar.context.logger") as mock_logger:
            ctx = fetch_calendar_context(client, now)

        assert ctx.event_count == 0
        assert ctx.events_text == ""
        assert ctx.id_map == {}
        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "failed" in warning_msg.lower() or "Failed" in warning_msg


# ===========================================================================
# ID Mapping (2 tests)
# ===========================================================================


class TestIdMapIntegersStartAtOne:
    """Integer IDs in the map start at 1 and are sequential."""

    def test_id_map_integers_start_at_one(self) -> None:
        """id_map keys are 1, 2, 3 for three events."""
        events = [
            _make_google_event(
                f"Event {i}",
                datetime(2026, 3, 10, 8 + i, 0),
                datetime(2026, 3, 10, 9 + i, 0),
                event_id=f"gcal-{i}",
            )
            for i in range(3)
        ]
        client = _make_mock_client(events=events)
        now = datetime(2026, 3, 10, 0, 0)

        ctx = fetch_calendar_context(client, now)

        assert set(ctx.id_map.keys()) == {1, 2, 3}


class TestIdMapReverseLookup:
    """id_map allows reverse lookup from integer to Google Calendar UUID."""

    def test_id_map_reverse_lookup(self) -> None:
        """id_map[n] returns the correct Google Calendar event UUID."""
        events = [
            _make_google_event(
                "Alpha",
                datetime(2026, 3, 10, 9, 0),
                datetime(2026, 3, 10, 10, 0),
                event_id="uuid-alpha-123",
            ),
            _make_google_event(
                "Beta",
                datetime(2026, 3, 10, 11, 0),
                datetime(2026, 3, 10, 12, 0),
                event_id="uuid-beta-456",
            ),
        ]
        client = _make_mock_client(events=events)
        now = datetime(2026, 3, 10, 0, 0)

        ctx = fetch_calendar_context(client, now)

        # Alpha is chronologically first, Beta second.
        assert ctx.id_map[1] == "uuid-alpha-123"
        assert ctx.id_map[2] == "uuid-beta-456"


# ===========================================================================
# Edge Cases (1 test)
# ===========================================================================


class TestAllDayEventFormatting:
    """All-day events use the 'date' field instead of 'dateTime'."""

    def test_all_day_event_formatting(self) -> None:
        """All-day event is formatted correctly with date strings."""
        events = [
            _make_all_day_event("Company Holiday", "2026-03-15", event_id="gcal-allday"),
        ]
        client = _make_mock_client(events=events)
        now = datetime(2026, 3, 10, 0, 0)

        ctx = fetch_calendar_context(client, now)

        assert ctx.event_count == 1
        assert "Company Holiday" in ctx.events_text
        assert "2026-03-15" in ctx.events_text
        assert ctx.id_map[1] == "gcal-allday"
