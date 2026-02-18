"""Tests for the Google Calendar event mapper.

Covers the ``map_to_google_event`` function which converts
:class:`~cal_ai.models.extraction.ValidatedEvent` instances into Google
Calendar API event body dicts.

Test matrix (7 tests):

| Test | Scenario | Expected |
|---|---|---|
| test_map_full_event | All fields populated | Correct Google Calendar dict |
| test_map_minimal_event_no_location_no_attendees | Required fields only | No location/attendees in output |
| test_map_event_default_end_time | end_time defaulted to start+1hr | end = start + 1 hour |
| test_map_event_with_attendees | Attendees list with owner | Owner mapped to email, others in description |
| test_map_event_description_includes_reasoning | Reasoning + assumptions | Both in description field |
| test_map_event_timezone_applied | Configured timezone | start/end timeZone matches config |
| test_map_event_iso_format | Datetime serialization | ISO 8601 format |
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cal_ai.calendar.event_mapper import map_to_google_event
from cal_ai.models.extraction import ValidatedEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TIMEZONE = "America/Vancouver"
OWNER_EMAIL = "owner@example.com"


def _make_event(**overrides: object) -> ValidatedEvent:
    """Create a ValidatedEvent with sensible defaults, applying *overrides*."""
    defaults: dict = {
        "title": "Team Standup",
        "start_time": datetime(2026, 3, 10, 9, 0),
        "end_time": datetime(2026, 3, 10, 10, 0),
        "location": "Room 301",
        "attendees": [OWNER_EMAIL, "Alice"],
        "confidence": "high",
        "reasoning": "Daily standup mentioned at 9 AM.",
        "assumptions": ["Assuming 1-hour duration"],
        "action": "create",
    }
    defaults.update(overrides)
    return ValidatedEvent(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMapFullEvent:
    """All fields populated -- the happy path."""

    def test_map_full_event(self) -> None:
        """A fully populated ValidatedEvent produces a complete Google Calendar body."""
        event = _make_event()
        body = map_to_google_event(event, TIMEZONE, OWNER_EMAIL)

        assert body["summary"] == "Team Standup"
        assert body["location"] == "Room 301"
        assert body["start"]["timeZone"] == TIMEZONE
        assert body["end"]["timeZone"] == TIMEZONE
        assert body["start"]["dateTime"] == event.start_time.isoformat()
        assert body["end"]["dateTime"] == event.end_time.isoformat()
        assert "Reasoning:" in body["description"]
        assert "Assumptions:" in body["description"]
        # Owner should be an attendee entry with email
        assert {"email": OWNER_EMAIL} in body["attendees"]


class TestMapMinimalEvent:
    """Only required fields -- no location or attendees."""

    def test_map_minimal_event_no_location_no_attendees(self) -> None:
        """An event with no location and no attendees omits those keys from the body."""
        event = _make_event(location=None, attendees=[])
        body = map_to_google_event(event, TIMEZONE, OWNER_EMAIL)

        assert "location" not in body
        assert "attendees" not in body
        assert body["summary"] == "Team Standup"
        assert "start" in body
        assert "end" in body


class TestMapEventDefaultEndTime:
    """end_time was defaulted to start + 1 hour by ValidatedEvent."""

    def test_map_event_default_end_time(self) -> None:
        """When end_time equals start_time + 1 hour (the default), it maps correctly."""
        start = datetime(2026, 3, 10, 14, 0)
        end = start + timedelta(hours=1)
        event = _make_event(start_time=start, end_time=end)
        body = map_to_google_event(event, TIMEZONE, OWNER_EMAIL)

        assert body["start"]["dateTime"] == start.isoformat()
        assert body["end"]["dateTime"] == end.isoformat()
        # Verify the 1-hour gap is preserved
        parsed_start = datetime.fromisoformat(body["start"]["dateTime"])
        parsed_end = datetime.fromisoformat(body["end"]["dateTime"])
        assert parsed_end - parsed_start == timedelta(hours=1)


class TestMapEventWithAttendees:
    """Attendees list -- owner mapped to email, others to display names in description."""

    def test_map_event_with_attendees(self) -> None:
        """Owner appears as a Google Calendar attendee; others appear in description."""
        event = _make_event(attendees=[OWNER_EMAIL, "Bob", "Charlie"])
        body = map_to_google_event(event, TIMEZONE, OWNER_EMAIL)

        # Owner mapped to attendee entry with email
        assert {"email": OWNER_EMAIL} in body["attendees"]
        # Non-owner names should NOT be in the attendees list
        attendee_emails = [a["email"] for a in body["attendees"]]
        assert len(attendee_emails) == 1
        assert attendee_emails[0] == OWNER_EMAIL
        # Non-owner names appear in the description body
        assert "Bob" in body["description"]
        assert "Charlie" in body["description"]
        assert "Other attendees:" in body["description"]


class TestMapEventDescriptionIncludesReasoning:
    """Description field includes LLM reasoning and assumptions."""

    def test_map_event_description_includes_reasoning(self) -> None:
        """Both reasoning and assumptions are present in the event description."""
        event = _make_event(
            reasoning="Extracted from meeting invite discussion.",
            assumptions=["Duration assumed 1 hour", "Location assumed Room 301"],
        )
        body = map_to_google_event(event, TIMEZONE, OWNER_EMAIL)

        description = body["description"]
        assert "Reasoning: Extracted from meeting invite discussion." in description
        assert "Duration assumed 1 hour" in description
        assert "Location assumed Room 301" in description
        assert "Assumptions:" in description


class TestMapEventTimezoneApplied:
    """Timezone from configuration is applied to start and end."""

    def test_map_event_timezone_applied(self) -> None:
        """Both start and end carry the configured IANA timezone string."""
        tz = "Europe/Berlin"
        event = _make_event()
        body = map_to_google_event(event, tz, OWNER_EMAIL)

        assert body["start"]["timeZone"] == tz
        assert body["end"]["timeZone"] == tz


class TestMapEventIsoFormat:
    """Datetime serialization uses ISO 8601."""

    def test_map_event_iso_format(self) -> None:
        """start and end dateTime values are valid ISO 8601 strings."""
        event = _make_event(
            start_time=datetime(2026, 12, 25, 15, 30, 0),
            end_time=datetime(2026, 12, 25, 16, 30, 0),
        )
        body = map_to_google_event(event, TIMEZONE, OWNER_EMAIL)

        # Verify ISO 8601 format by round-tripping through fromisoformat
        start_str = body["start"]["dateTime"]
        end_str = body["end"]["dateTime"]
        assert datetime.fromisoformat(start_str) == event.start_time
        assert datetime.fromisoformat(end_str) == event.end_time
        # ISO 8601 uses "T" separator
        assert "T" in start_str
        assert "T" in end_str
