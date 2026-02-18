"""Tests for the Google Calendar CRUD client and sync orchestrator.

Covers :class:`~cal_ai.calendar.client.GoogleCalendarClient` methods for
create, read, update, delete operations, as well as duplicate detection,
conflict detection, and the :func:`~cal_ai.calendar.sync.sync_events`
orchestrator.

Test matrix (24 tests):

Create Operations (5):
| test_create_event_success | Happy path create | insert() called, response returned |
| test_create_event_minimal_fields | No location/attendees | insert() called |
| test_create_event_with_attendees | Attendees in event | Attendees in API body |
| test_create_event_skipped_when_duplicate | Duplicate detected | insert() NOT called |
| test_create_event_with_conflict_warning | Time conflict exists | insert() called, warning |

Read Operations (3):
| test_list_events_returns_results | Events in range | Correct list returned |
| test_list_events_empty_range | No events | Empty list |
| test_list_events_pagination | nextPageToken present | Multiple pages fetched |

Update Operations (3):
| test_update_event_success | Update by ID | update() called |
| test_find_and_update_event_found | Search + update | Matching event updated |
| test_find_and_update_event_not_found | No match | update() NOT called, None |

Delete Operations (3):
| test_delete_event_success | Delete by ID | delete() called |
| test_find_and_delete_event_found | Search + delete | True returned |
| test_find_and_delete_event_not_found | No match | False returned |

Duplicate Detection (5):
| test_duplicate_detected_same_title_overlapping_time | Same title + overlap | Returns existing |
| test_no_duplicate_same_title_different_time | Same title, no overlap | Returns None |
| test_no_duplicate_different_title_same_time | Different title, same time | Returns None |
| test_duplicate_detection_case_insensitive | "Lunch" vs "lunch" | Detected |
| test_duplicate_detection_partial_overlap | Same title, partial overlap | Detected |

Conflict Detection (4):
| test_conflict_detected_overlapping_time | Different title, overlap | Returns conflict |
| test_no_conflict_adjacent_events | Back-to-back | No conflict |
| test_no_conflict_non_overlapping | Separate times | No conflict |
| test_multiple_conflicts_detected | Overlaps with 2+ events | All returned |
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from cal_ai.calendar.client import GoogleCalendarClient
from cal_ai.calendar.sync import sync_events
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


def _make_google_event(
    summary: str,
    start: datetime,
    end: datetime,
    event_id: str = "evt-1",
) -> dict:
    """Build a dict resembling a Google Calendar API event resource."""
    return {
        "id": event_id,
        "summary": summary,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }


def _build_mock_service(
    *,
    list_items: list[dict] | None = None,
    list_pages: list[dict] | None = None,
    insert_return: dict | None = None,
    update_return: dict | None = None,
) -> MagicMock:
    """Create a mock Google Calendar API service resource.

    Args:
        list_items: Items returned by a single-page list() call.
        list_pages: Multiple page responses for pagination tests.
        insert_return: Response for events().insert().execute().
        update_return: Response for events().update().execute().
    """
    service = MagicMock()
    events = service.events.return_value

    # List pagination support.
    if list_pages is not None:
        execute_calls = [MagicMock(return_value=page) for page in list_pages]
        events.list.return_value.execute = MagicMock(side_effect=[p() for p in execute_calls])
        # Actually, we need the list mock to return an object whose execute() returns pages
        # in sequence.
        side_effects = list(list_pages)
        events.list.return_value.execute = MagicMock(side_effect=side_effects)
    elif list_items is not None:
        events.list.return_value.execute.return_value = {
            "items": list_items,
        }
    else:
        events.list.return_value.execute.return_value = {"items": []}

    # Insert
    if insert_return is not None:
        events.insert.return_value.execute.return_value = insert_return
    else:
        events.insert.return_value.execute.return_value = {"id": "new-evt-1"}

    # Update
    if update_return is not None:
        events.update.return_value.execute.return_value = update_return
    else:
        events.update.return_value.execute.return_value = {"id": "evt-1"}

    # Delete
    events.delete.return_value.execute.return_value = None

    return service


def _make_client(service: MagicMock) -> GoogleCalendarClient:
    """Create a GoogleCalendarClient with a mock service."""
    creds = MagicMock()
    return GoogleCalendarClient(
        credentials=creds,
        timezone=TIMEZONE,
        owner_email=OWNER_EMAIL,
        service=service,
    )


# ===========================================================================
# Create Operations (5 tests)
# ===========================================================================


class TestCreateEventSuccess:
    """Happy path: create event inserts into Google Calendar."""

    def test_create_event_success(self) -> None:
        """insert() is called and the API response dict is returned."""
        service = _build_mock_service(
            insert_return={"id": "new-1", "summary": "Team Standup"},
        )
        client = _make_client(service)
        event = _make_event()

        result = client.create_event(event)

        assert result is not None
        assert result["id"] == "new-1"
        service.events.return_value.insert.assert_called_once()


class TestCreateEventMinimalFields:
    """Create event with no location or attendees."""

    def test_create_event_minimal_fields(self) -> None:
        """insert() is called even when optional fields are absent."""
        service = _build_mock_service()
        client = _make_client(service)
        event = _make_event(location=None, attendees=[])

        result = client.create_event(event)

        assert result is not None
        service.events.return_value.insert.assert_called_once()
        # Verify the body passed to insert() does not contain location
        call_kwargs = service.events.return_value.insert.call_args
        body = call_kwargs[1]["body"] if "body" in call_kwargs[1] else call_kwargs[0][1]
        assert "location" not in body


class TestCreateEventWithAttendees:
    """Create event with attendees in the event."""

    def test_create_event_with_attendees(self) -> None:
        """Attendees appear in the API body passed to insert()."""
        service = _build_mock_service()
        client = _make_client(service)
        event = _make_event(attendees=[OWNER_EMAIL, "Bob"])

        result = client.create_event(event)

        assert result is not None
        call_kwargs = service.events.return_value.insert.call_args
        body = call_kwargs[1]["body"]
        assert "attendees" in body
        assert {"email": OWNER_EMAIL} in body["attendees"]


class TestCreateEventSkippedWhenDuplicate:
    """Duplicate event detected -- insert() should NOT be called."""

    def test_create_event_skipped_when_duplicate(self) -> None:
        """When a duplicate exists, create_event returns None and skips insert."""
        existing = _make_google_event(
            summary="Team Standup",
            start=datetime(2026, 3, 10, 9, 0),
            end=datetime(2026, 3, 10, 10, 0),
        )
        service = _build_mock_service(list_items=[existing])
        client = _make_client(service)
        event = _make_event()

        result = client.create_event(event)

        assert result is None
        service.events.return_value.insert.assert_not_called()


class TestCreateEventWithConflictWarning:
    """Time conflict exists but creation should proceed with a warning."""

    def test_create_event_with_conflict_warning(self) -> None:
        """insert() is called despite time conflict; warning is logged."""
        # Conflict: different title, overlapping time.
        existing = _make_google_event(
            summary="Different Meeting",
            start=datetime(2026, 3, 10, 9, 30),
            end=datetime(2026, 3, 10, 10, 30),
        )
        service = _build_mock_service(list_items=[existing])
        client = _make_client(service)
        event = _make_event()

        with patch("cal_ai.calendar.client.logger") as mock_logger:
            result = client.create_event(event)

        assert result is not None
        service.events.return_value.insert.assert_called_once()
        # A warning should have been logged about the conflict.
        mock_logger.warning.assert_called()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "conflicts" in warning_msg.lower() or "conflict" in warning_msg.lower()


# ===========================================================================
# Read Operations (3 tests)
# ===========================================================================


class TestListEventsReturnsResults:
    """Events exist in the time range."""

    def test_list_events_returns_results(self) -> None:
        """list_events returns the correct list of event dicts."""
        items = [
            _make_google_event(
                "Event A", datetime(2026, 3, 10, 9, 0), datetime(2026, 3, 10, 10, 0),
            ),
            _make_google_event(
                "Event B", datetime(2026, 3, 10, 11, 0), datetime(2026, 3, 10, 12, 0),
            ),
        ]
        service = _build_mock_service(list_items=items)
        client = _make_client(service)

        result = client.list_events(
            time_min=datetime(2026, 3, 10, 0, 0),
            time_max=datetime(2026, 3, 11, 0, 0),
        )

        assert len(result) == 2
        assert result[0]["summary"] == "Event A"
        assert result[1]["summary"] == "Event B"


class TestListEventsEmptyRange:
    """No events in the time range."""

    def test_list_events_empty_range(self) -> None:
        """An empty list is returned when no events match."""
        service = _build_mock_service(list_items=[])
        client = _make_client(service)

        result = client.list_events(
            time_min=datetime(2026, 3, 10, 0, 0),
            time_max=datetime(2026, 3, 11, 0, 0),
        )

        assert result == []


class TestListEventsPagination:
    """Multiple pages of results are fetched via nextPageToken."""

    def test_list_events_pagination(self) -> None:
        """All pages are combined into a single list."""
        page1 = {
            "items": [
                _make_google_event(
                    "P1", datetime(2026, 3, 10, 9, 0), datetime(2026, 3, 10, 10, 0),
                ),
            ],
            "nextPageToken": "token-page2",
        }
        page2 = {
            "items": [
                _make_google_event(
                    "P2", datetime(2026, 3, 10, 11, 0), datetime(2026, 3, 10, 12, 0),
                ),
            ],
        }
        service = _build_mock_service(list_pages=[page1, page2])
        client = _make_client(service)

        result = client.list_events(
            time_min=datetime(2026, 3, 10, 0, 0),
            time_max=datetime(2026, 3, 11, 0, 0),
        )

        assert len(result) == 2
        summaries = [e["summary"] for e in result]
        assert "P1" in summaries
        assert "P2" in summaries


# ===========================================================================
# Update Operations (3 tests)
# ===========================================================================


class TestUpdateEventSuccess:
    """Update an event by ID."""

    def test_update_event_success(self) -> None:
        """update() is called with the correct event ID and returns the API response."""
        service = _build_mock_service(
            update_return={"id": "evt-42", "summary": "Updated Standup"},
        )
        client = _make_client(service)
        event = _make_event(title="Updated Standup")

        result = client.update_event("evt-42", event)

        assert result["id"] == "evt-42"
        service.events.return_value.update.assert_called_once()
        call_kwargs = service.events.return_value.update.call_args[1]
        assert call_kwargs["eventId"] == "evt-42"


class TestFindAndUpdateEventFound:
    """Search by title and time finds a match, then updates it."""

    def test_find_and_update_event_found(self) -> None:
        """Matching event is found and updated; API response is returned."""
        existing = _make_google_event(
            summary="Team Standup",
            start=datetime(2026, 3, 10, 9, 0),
            end=datetime(2026, 3, 10, 10, 0),
            event_id="existing-1",
        )
        service = _build_mock_service(
            list_items=[existing],
            update_return={"id": "existing-1", "summary": "Team Standup"},
        )
        client = _make_client(service)
        event = _make_event()

        result = client.find_and_update_event(event)

        assert result is not None
        assert result["id"] == "existing-1"
        service.events.return_value.update.assert_called_once()
        call_kwargs = service.events.return_value.update.call_args[1]
        assert call_kwargs["eventId"] == "existing-1"


class TestFindAndUpdateEventNotFound:
    """No matching event found -- update should not be called."""

    def test_find_and_update_event_not_found(self) -> None:
        """Returns None and update() is not called when no match exists."""
        service = _build_mock_service(list_items=[])
        client = _make_client(service)
        event = _make_event()

        result = client.find_and_update_event(event)

        assert result is None
        service.events.return_value.update.assert_not_called()


# ===========================================================================
# Delete Operations (3 tests)
# ===========================================================================


class TestDeleteEventSuccess:
    """Delete an event by ID."""

    def test_delete_event_success(self) -> None:
        """delete() is called with the correct event ID."""
        service = _build_mock_service()
        client = _make_client(service)

        client.delete_event("evt-99")

        service.events.return_value.delete.assert_called_once()
        call_kwargs = service.events.return_value.delete.call_args[1]
        assert call_kwargs["eventId"] == "evt-99"


class TestFindAndDeleteEventFound:
    """Search by title and time finds a match, then deletes it."""

    def test_find_and_delete_event_found(self) -> None:
        """Matching event is found and deleted; returns True."""
        existing = _make_google_event(
            summary="Team Standup",
            start=datetime(2026, 3, 10, 9, 0),
            end=datetime(2026, 3, 10, 10, 0),
            event_id="del-1",
        )
        service = _build_mock_service(list_items=[existing])
        client = _make_client(service)
        event = _make_event()

        result = client.find_and_delete_event(event)

        assert result is True
        service.events.return_value.delete.assert_called_once()
        call_kwargs = service.events.return_value.delete.call_args[1]
        assert call_kwargs["eventId"] == "del-1"


class TestFindAndDeleteEventNotFound:
    """No matching event found -- delete should not be called."""

    def test_find_and_delete_event_not_found(self) -> None:
        """Returns False and delete() is not called when no match exists."""
        service = _build_mock_service(list_items=[])
        client = _make_client(service)
        event = _make_event()

        result = client.find_and_delete_event(event)

        assert result is False
        service.events.return_value.delete.assert_not_called()


# ===========================================================================
# Duplicate Detection (5 tests)
# ===========================================================================


class TestDuplicateDetectedSameTitleOverlappingTime:
    """Same title and overlapping time -- duplicate."""

    def test_duplicate_detected_same_title_overlapping_time(self) -> None:
        """Returns the existing event when title matches and times overlap."""
        existing = _make_google_event(
            summary="Team Standup",
            start=datetime(2026, 3, 10, 9, 0),
            end=datetime(2026, 3, 10, 10, 0),
        )
        event = _make_event()

        result = GoogleCalendarClient._is_duplicate(event, [existing])

        assert result is not None
        assert result["summary"] == "Team Standup"


class TestNoDuplicateSameTitleDifferentTime:
    """Same title but completely non-overlapping time -- not a duplicate."""

    def test_no_duplicate_same_title_different_time(self) -> None:
        """Returns None when the title matches but times do not overlap."""
        existing = _make_google_event(
            summary="Team Standup",
            start=datetime(2026, 3, 11, 9, 0),  # next day
            end=datetime(2026, 3, 11, 10, 0),
        )
        event = _make_event()

        result = GoogleCalendarClient._is_duplicate(event, [existing])

        assert result is None


class TestNoDuplicateDifferentTitleSameTime:
    """Different title but same time -- not a duplicate (it is a conflict)."""

    def test_no_duplicate_different_title_same_time(self) -> None:
        """Returns None when the time overlaps but the title is different."""
        existing = _make_google_event(
            summary="Lunch Break",
            start=datetime(2026, 3, 10, 9, 0),
            end=datetime(2026, 3, 10, 10, 0),
        )
        event = _make_event()

        result = GoogleCalendarClient._is_duplicate(event, [existing])

        assert result is None


class TestDuplicateDetectionCaseInsensitive:
    """Title comparison is case-insensitive."""

    def test_duplicate_detection_case_insensitive(self) -> None:
        """'team standup' matches 'Team Standup' as a duplicate."""
        existing = _make_google_event(
            summary="team standup",  # lowercase
            start=datetime(2026, 3, 10, 9, 0),
            end=datetime(2026, 3, 10, 10, 0),
        )
        event = _make_event(title="Team Standup")

        result = GoogleCalendarClient._is_duplicate(event, [existing])

        assert result is not None


class TestDuplicateDetectionPartialOverlap:
    """Same title with partial time overlap -- still a duplicate."""

    def test_duplicate_detection_partial_overlap(self) -> None:
        """Partial overlap (event starts during existing event) is detected."""
        existing = _make_google_event(
            summary="Team Standup",
            start=datetime(2026, 3, 10, 9, 30),  # starts 30 min after new event
            end=datetime(2026, 3, 10, 10, 30),   # ends 30 min after new event
        )
        event = _make_event()  # 9:00-10:00

        result = GoogleCalendarClient._is_duplicate(event, [existing])

        assert result is not None


# ===========================================================================
# Conflict Detection (4 tests)
# ===========================================================================


class TestConflictDetectedOverlappingTime:
    """Different title, overlapping time -- conflict."""

    def test_conflict_detected_overlapping_time(self) -> None:
        """Returns the conflicting event when times overlap regardless of title."""
        existing = _make_google_event(
            summary="Lunch Break",
            start=datetime(2026, 3, 10, 9, 30),
            end=datetime(2026, 3, 10, 10, 30),
        )
        event = _make_event()  # 9:00-10:00

        conflicts = GoogleCalendarClient._find_conflicts(event, [existing])

        assert len(conflicts) == 1
        assert conflicts[0]["summary"] == "Lunch Break"


class TestNoConflictAdjacentEvents:
    """Back-to-back events (end == start) are not conflicts."""

    def test_no_conflict_adjacent_events(self) -> None:
        """No conflict when one event ends exactly when another starts."""
        # Existing ends at 9:00, new event starts at 9:00
        existing = _make_google_event(
            summary="Early Meeting",
            start=datetime(2026, 3, 10, 8, 0),
            end=datetime(2026, 3, 10, 9, 0),  # ends exactly when new event starts
        )
        event = _make_event()  # 9:00-10:00

        conflicts = GoogleCalendarClient._find_conflicts(event, [existing])

        assert len(conflicts) == 0


class TestNoConflictNonOverlapping:
    """Completely separate times -- no conflict."""

    def test_no_conflict_non_overlapping(self) -> None:
        """No conflict when events are in completely separate time slots."""
        existing = _make_google_event(
            summary="Afternoon Call",
            start=datetime(2026, 3, 10, 14, 0),
            end=datetime(2026, 3, 10, 15, 0),
        )
        event = _make_event()  # 9:00-10:00

        conflicts = GoogleCalendarClient._find_conflicts(event, [existing])

        assert len(conflicts) == 0


class TestMultipleConflictsDetected:
    """Event overlaps with multiple existing events."""

    def test_multiple_conflicts_detected(self) -> None:
        """All conflicting events are returned, not just the first."""
        existing1 = _make_google_event(
            summary="Meeting A",
            start=datetime(2026, 3, 10, 9, 0),
            end=datetime(2026, 3, 10, 9, 30),
            event_id="c1",
        )
        existing2 = _make_google_event(
            summary="Meeting B",
            start=datetime(2026, 3, 10, 9, 45),
            end=datetime(2026, 3, 10, 10, 15),
            event_id="c2",
        )
        event = _make_event()  # 9:00-10:00

        conflicts = GoogleCalendarClient._find_conflicts(event, [existing1, existing2])

        assert len(conflicts) == 2
        summaries = {c["summary"] for c in conflicts}
        assert summaries == {"Meeting A", "Meeting B"}


# ===========================================================================
# Sync Orchestration (5 tests)
# ===========================================================================


class TestSyncEventsDispatchesCreate:
    """sync_events dispatches action='create' to create_event."""

    def test_sync_events_dispatches_create(self) -> None:
        """create_event is called for events with action='create'."""
        service = _build_mock_service()
        client = _make_client(service)
        events = [_make_event(action="create")]

        result = sync_events(events, client)

        assert result.created == 1
        service.events.return_value.insert.assert_called_once()


class TestSyncEventsDispatchesUpdate:
    """sync_events dispatches action='update' to find_and_update_event."""

    def test_sync_events_dispatches_update(self) -> None:
        """find_and_update_event is called for events with action='update'."""
        existing = _make_google_event(
            summary="Team Standup",
            start=datetime(2026, 3, 10, 9, 0),
            end=datetime(2026, 3, 10, 10, 0),
            event_id="upd-1",
        )
        service = _build_mock_service(
            list_items=[existing],
            update_return={"id": "upd-1", "summary": "Team Standup"},
        )
        client = _make_client(service)
        events = [_make_event(action="update")]

        result = sync_events(events, client)

        assert result.updated == 1
        service.events.return_value.update.assert_called_once()


class TestSyncEventsDispatchesDelete:
    """sync_events dispatches action='delete' to find_and_delete_event."""

    def test_sync_events_dispatches_delete(self) -> None:
        """find_and_delete_event is called for events with action='delete'."""
        existing = _make_google_event(
            summary="Team Standup",
            start=datetime(2026, 3, 10, 9, 0),
            end=datetime(2026, 3, 10, 10, 0),
            event_id="del-1",
        )
        service = _build_mock_service(list_items=[existing])
        client = _make_client(service)
        events = [_make_event(action="delete")]

        result = sync_events(events, client)

        assert result.deleted == 1
        service.events.return_value.delete.assert_called_once()


class TestSyncEventsReturnsSummary:
    """Mixed actions produce correct SyncResult counts."""

    def test_sync_events_returns_summary(self) -> None:
        """SyncResult correctly counts creates, updates, and deletes."""
        existing = _make_google_event(
            summary="Team Standup",
            start=datetime(2026, 3, 10, 9, 0),
            end=datetime(2026, 3, 10, 10, 0),
            event_id="mix-1",
        )
        service = _build_mock_service(
            list_items=[existing],
            update_return={"id": "mix-1", "summary": "Team Standup"},
        )
        client = _make_client(service)

        events = [
            _make_event(title="Create Event", action="create",
                        start_time=datetime(2026, 3, 11, 9, 0),
                        end_time=datetime(2026, 3, 11, 10, 0)),
            _make_event(title="Team Standup", action="update"),
            _make_event(title="Team Standup", action="delete"),
        ]

        result = sync_events(events, client)

        assert result.created == 1
        assert result.updated == 1
        assert result.deleted == 1
        assert result.total_processed == 3


class TestSyncEventsContinuesOnPartialFailure:
    """One event fails but others are still processed."""

    def test_sync_events_continues_on_partial_failure(self) -> None:
        """Processing continues for remaining events after one fails."""
        service = _build_mock_service()
        client = _make_client(service)

        # First event will fail (set insert to raise), second should succeed.
        call_count = 0
        def side_effect_insert(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Simulated API failure")
            return {"id": "new-2"}

        service.events.return_value.insert.return_value.execute = MagicMock(
            side_effect=side_effect_insert
        )

        events = [
            _make_event(title="Failing Event", action="create",
                        start_time=datetime(2026, 3, 11, 9, 0),
                        end_time=datetime(2026, 3, 11, 10, 0)),
            _make_event(title="Good Event", action="create",
                        start_time=datetime(2026, 3, 12, 9, 0),
                        end_time=datetime(2026, 3, 12, 10, 0)),
        ]

        result = sync_events(events, client)

        assert result.created == 1
        assert len(result.failures) == 1
        assert result.failures[0]["event"] == "Failing Event"
