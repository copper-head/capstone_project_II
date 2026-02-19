"""Integration tests for full CRUD flows (8 tests).

These tests wire the real transcript parser against real sample files but
mock the external services (Gemini LLM and Google Calendar API).  They
validate the complete CRUD intelligence pipeline -- calendar context
injection, LLM extraction with action decisions, ID-based sync dispatch,
404 fallback, and graceful degradation.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from cal_ai.calendar.context import CalendarContext
from cal_ai.calendar.exceptions import CalendarNotFoundError
from cal_ai.demo_output import format_pipeline_result
from cal_ai.models.extraction import ExtractedEvent, ExtractionResult, ValidatedEvent
from cal_ai.pipeline import run_pipeline

# ---------------------------------------------------------------------------
# Frozen reference datetime (all tests use the same "now")
# ---------------------------------------------------------------------------

FROZEN_NOW = datetime(2026, 2, 18, 10, 0, 0)

# ---------------------------------------------------------------------------
# Sample file paths
# ---------------------------------------------------------------------------

SAMPLES = Path("samples")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    title: str,
    action: str = "create",
    confidence: str = "high",
    start: str = "2026-02-19T12:00:00",
    end: str | None = "2026-02-19T13:00:00",
    location: str | None = None,
    attendees: list[str] | None = None,
    reasoning: str = "Extracted from conversation.",
    assumptions: list[str] | None = None,
    existing_event_id: int | None = None,
) -> ExtractedEvent:
    """Build a stub ``ExtractedEvent``."""
    return ExtractedEvent(
        title=title,
        start_time=start,
        end_time=end,
        location=location,
        attendees=attendees or [],
        confidence=confidence,
        reasoning=reasoning,
        assumptions=assumptions or [],
        action=action,
        existing_event_id=existing_event_id,
    )


def _make_validated(event: ExtractedEvent) -> ValidatedEvent:
    """Build a ``ValidatedEvent`` from an ``ExtractedEvent`` using the factory."""
    return ValidatedEvent.from_extracted(event)


def _make_extraction(events: list[ExtractedEvent]) -> ExtractionResult:
    """Wrap events in an ``ExtractionResult``."""
    return ExtractionResult(events=events, summary="Extracted events")


def _make_settings() -> MagicMock:
    """Build a mock Settings object with required attributes."""
    settings = MagicMock()
    settings.gemini_api_key = "fake-key"
    settings.timezone = "America/Vancouver"
    settings.google_account_email = "test@example.com"
    return settings


def _run_crud_e2e(
    sample_file: str,
    extracted_events: list[ExtractedEvent],
    *,
    owner: str = "Alice",
    dry_run: bool = False,
    calendar_context: CalendarContext | None = None,
    update_event_side_effect=None,
    delete_event_side_effect=None,
    context_side_effect: Exception | None = None,
):
    """Run the pipeline end-to-end with mocked LLM and calendar.

    The real ``parse_transcript_file`` reads the actual sample file.
    Everything else (settings, Gemini, calendar credentials, calendar
    client) is mocked.

    Unlike the base _run_e2e helper, this one supports:
    - Calendar context injection (with id_map and event_meta)
    - Direct update_event / delete_event side effects
    - Context fetch failure simulation

    Returns a tuple of ``(result, mocks)`` where *mocks* is a namespace
    with ``gemini``, ``client``, etc.
    """
    extraction = _make_extraction(extracted_events)
    validated = [_make_validated(e) for e in extracted_events]

    # -- Mock GeminiClient instance ----------------------------------------
    mock_gemini = MagicMock()
    mock_gemini.extract_events.return_value = extraction
    mock_gemini.validate_events.return_value = validated
    mock_gemini_cls = MagicMock(return_value=mock_gemini)

    # -- Mock settings -----------------------------------------------------
    mock_settings_fn = MagicMock(return_value=_make_settings())

    # -- Mock calendar credentials and client ------------------------------
    mock_get_creds = MagicMock(return_value=MagicMock())
    mock_client = MagicMock()
    mock_client.create_event.return_value = {"id": "evt-create-1"}
    mock_client.find_and_update_event.return_value = {"id": "evt-update-1"}
    mock_client.find_and_delete_event.return_value = True
    mock_client.update_event.return_value = {"id": "evt-updated-direct"}
    mock_client.delete_event.return_value = None

    # Apply per-method side effects if provided.
    if update_event_side_effect is not None:
        mock_client.update_event.side_effect = update_event_side_effect
    if delete_event_side_effect is not None:
        mock_client.delete_event.side_effect = delete_event_side_effect

    mock_cal_cls = MagicMock(return_value=mock_client)

    # -- Mock fetch_calendar_context -----------------------------------------
    cal_ctx = calendar_context or CalendarContext()
    mock_fetch_context = MagicMock()
    if context_side_effect is not None:
        mock_fetch_context.side_effect = context_side_effect
    else:
        mock_fetch_context.return_value = cal_ctx

    class _Mocks:
        gemini = mock_gemini
        gemini_cls = mock_gemini_cls
        client = mock_client
        cal_cls = mock_cal_cls
        fetch_context = mock_fetch_context

    with (
        patch("cal_ai.pipeline.GeminiClient", mock_gemini_cls),
        patch("cal_ai.pipeline.load_settings", mock_settings_fn),
        patch("cal_ai.pipeline.get_calendar_credentials", mock_get_creds),
        patch("cal_ai.pipeline.GoogleCalendarClient", mock_cal_cls),
        patch("cal_ai.pipeline.fetch_calendar_context", mock_fetch_context),
    ):
        result = run_pipeline(
            transcript_path=Path(sample_file),
            owner=owner,
            dry_run=dry_run,
            current_datetime=FROZEN_NOW,
        )

    return result, _Mocks()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCRUDFlows:
    """Integration tests for full CRUD flows with calendar context."""

    def test_create_only_flow(self) -> None:
        """Baseline: create-only flow with no existing events (no calendar context)."""
        events = [
            _make_event(
                title="Lunch with Bob",
                action="create",
                start="2026-02-19T12:00:00",
                end="2026-02-19T13:00:00",
                location="New place on 5th",
                attendees=["Alice", "Bob"],
                reasoning="Alice proposes lunch Thursday at noon, Bob confirms.",
            ),
        ]

        result, mocks = _run_crud_e2e("samples/simple_lunch.txt", events)

        # Verify extraction and sync.
        assert len(result.events_extracted) == 1
        assert result.events_extracted[0].action == "create"
        assert len(result.events_synced) == 1
        assert result.events_synced[0].action_taken == "created"

        # Verify create_event called, not update/delete.
        mocks.client.create_event.assert_called_once()
        mocks.client.update_event.assert_not_called()
        mocks.client.delete_event.assert_not_called()
        mocks.client.find_and_update_event.assert_not_called()
        mocks.client.find_and_delete_event.assert_not_called()

    def test_update_flow_with_existing_event_id(self) -> None:
        """Update flow: calendar has event, AI outputs update with existing_event_id."""
        cal_ctx = CalendarContext(
            events_text=(
                "[1] Team Standup"
                " | 2026-02-19T09:00:00 - 2026-02-19T09:30:00"
                " | Main conf room"
            ),
            id_map={1: "real-uuid-standup"},
            event_count=1,
            event_meta={1: {"title": "Team Standup", "start_time": "2026-02-19T09:00:00"}},
        )

        events = [
            _make_event(
                title="Team Standup",
                action="update",
                start="2026-02-19T10:00:00",
                end="2026-02-19T10:30:00",
                location="Main conf room",
                attendees=["Alice", "Bob"],
                reasoning="Alice asks to move standup from 9 AM to 10 AM.",
                existing_event_id=1,
            ),
        ]

        result, mocks = _run_crud_e2e(
            "samples/update_meeting.txt",
            events,
            calendar_context=cal_ctx,
        )

        # Verify correct dispatch: direct update_event with real UUID.
        assert len(result.events_synced) == 1
        assert result.events_synced[0].action_taken == "updated"
        assert result.events_synced[0].calendar_event_id == "evt-updated-direct"

        mocks.client.update_event.assert_called_once()
        call_args = mocks.client.update_event.call_args
        assert call_args[0][0] == "real-uuid-standup"  # First arg: real UUID
        mocks.client.find_and_update_event.assert_not_called()

        # Verify matched event info is populated.
        assert result.events_synced[0].matched_event_title == "Team Standup"
        assert result.events_synced[0].matched_event_time == "2026-02-19T09:00:00"

    def test_delete_flow_with_existing_event_id(self) -> None:
        """Delete flow: calendar has event, AI outputs delete with existing_event_id."""
        cal_ctx = CalendarContext(
            events_text="[1] Code Review | 2026-02-19T14:00:00 - 2026-02-19T15:00:00",
            id_map={1: "real-uuid-code-review"},
            event_count=1,
            event_meta={1: {"title": "Code Review", "start_time": "2026-02-19T14:00:00"}},
        )

        events = [
            _make_event(
                title="Code Review",
                action="delete",
                start="2026-02-19T14:00:00",
                end="2026-02-19T15:00:00",
                attendees=["Carol", "Dave"],
                reasoning="Carol cancels code review -- feature branch not ready.",
                existing_event_id=1,
            ),
        ]

        result, mocks = _run_crud_e2e(
            "samples/cancel_event.txt",
            events,
            owner="Carol",
            calendar_context=cal_ctx,
        )

        # Verify correct dispatch: direct delete_event with real UUID.
        assert len(result.events_synced) == 1
        assert result.events_synced[0].action_taken == "deleted"

        mocks.client.delete_event.assert_called_once_with("real-uuid-code-review")
        mocks.client.find_and_delete_event.assert_not_called()

        # Verify demo output contains [DELETE].
        output = format_pipeline_result(result)
        assert "[DELETE]" in output

    def test_mixed_crud_flow(self) -> None:
        """Mixed flow: single conversation produces create + update + delete."""
        cal_ctx = CalendarContext(
            events_text=(
                "[1] Sprint Planning | 2026-02-19T09:00:00 - 2026-02-19T10:00:00\n"
                "[2] Retrospective | 2026-02-20T15:00:00 - 2026-02-20T16:00:00"
            ),
            id_map={1: "real-uuid-sprint", 2: "real-uuid-retro"},
            event_count=2,
            event_meta={
                1: {"title": "Sprint Planning", "start_time": "2026-02-19T09:00:00"},
                2: {"title": "Retrospective", "start_time": "2026-02-20T15:00:00"},
            },
        )

        events = [
            _make_event(
                title="Design Review",
                action="create",
                start="2026-02-19T14:00:00",
                end="2026-02-19T15:00:00",
                location="Design lab",
                attendees=["Alice", "Bob", "Carol"],
                reasoning="Alice sets up a new design review on Wednesday.",
            ),
            _make_event(
                title="Sprint Planning",
                action="update",
                start="2026-02-20T10:00:00",
                end="2026-02-20T11:00:00",
                attendees=["Alice", "Bob", "Carol"],
                reasoning="Alice moves sprint planning from Thursday 9 AM to Friday 10 AM.",
                existing_event_id=1,
            ),
            _make_event(
                title="Retrospective",
                action="delete",
                start="2026-02-20T15:00:00",
                end="2026-02-20T16:00:00",
                attendees=["Alice", "Bob", "Carol"],
                reasoning="Alice cancels the Friday retrospective.",
                existing_event_id=2,
            ),
        ]

        result, mocks = _run_crud_e2e(
            "samples/mixed_crud.txt",
            events,
            calendar_context=cal_ctx,
        )

        # All 3 events should be synced.
        assert len(result.events_extracted) == 3
        assert len(result.events_synced) == 3
        assert len(result.events_failed) == 0

        # Verify correct dispatch per action.
        actions_taken = [s.action_taken for s in result.events_synced]
        assert actions_taken == ["created", "updated", "deleted"]

        mocks.client.create_event.assert_called_once()
        mocks.client.update_event.assert_called_once()
        mocks.client.delete_event.assert_called_once()

        # Verify direct ID calls used the correct UUIDs.
        update_call_args = mocks.client.update_event.call_args
        assert update_call_args[0][0] == "real-uuid-sprint"
        mocks.client.delete_event.assert_called_once_with("real-uuid-retro")

        # Verify demo output has all action tags.
        output = format_pipeline_result(result)
        assert "[CREATE]" in output
        assert "[UPDATE]" in output
        assert "[DELETE]" in output

    def test_update_404_fallback_to_create(self) -> None:
        """Fallback: update with 404 falls back to create."""
        cal_ctx = CalendarContext(
            events_text="[1] Team Standup | 2026-02-19T09:00:00 - 2026-02-19T09:30:00",
            id_map={1: "real-uuid-gone"},
            event_count=1,
            event_meta={1: {"title": "Team Standup", "start_time": "2026-02-19T09:00:00"}},
        )

        events = [
            _make_event(
                title="Team Standup",
                action="update",
                start="2026-02-19T10:00:00",
                end="2026-02-19T10:30:00",
                location="Main conf room",
                attendees=["Alice", "Bob"],
                reasoning="Alice asks to reschedule standup to 10 AM.",
                existing_event_id=1,
            ),
        ]

        result, mocks = _run_crud_e2e(
            "samples/update_meeting.txt",
            events,
            calendar_context=cal_ctx,
            update_event_side_effect=CalendarNotFoundError("Event not found"),
        )

        # update_event was attempted first (and raised 404).
        mocks.client.update_event.assert_called_once()
        call_args = mocks.client.update_event.call_args
        assert call_args[0][0] == "real-uuid-gone"

        # Fallback to create_event should have been invoked.
        mocks.client.create_event.assert_called_once()

        # Result should report "created" (the fallback action).
        assert len(result.events_synced) == 1
        assert result.events_synced[0].action_taken == "created"

        # Demo output should show [CREATE] (fallback).
        output = format_pipeline_result(result)
        assert "[CREATE]" in output

    def test_delete_404_idempotent_success(self) -> None:
        """Fallback: delete with 404 is treated as idempotent success."""
        cal_ctx = CalendarContext(
            events_text="[1] Code Review | 2026-02-19T14:00:00 - 2026-02-19T15:00:00",
            id_map={1: "real-uuid-already-gone"},
            event_count=1,
            event_meta={1: {"title": "Code Review", "start_time": "2026-02-19T14:00:00"}},
        )

        events = [
            _make_event(
                title="Code Review",
                action="delete",
                start="2026-02-19T14:00:00",
                end="2026-02-19T15:00:00",
                attendees=["Carol", "Dave"],
                reasoning="Carol cancels code review.",
                existing_event_id=1,
            ),
        ]

        result, mocks = _run_crud_e2e(
            "samples/cancel_event.txt",
            events,
            owner="Carol",
            calendar_context=cal_ctx,
            delete_event_side_effect=CalendarNotFoundError("Event not found"),
        )

        # delete_event was attempted.
        mocks.client.delete_event.assert_called_once_with("real-uuid-already-gone")

        # No failures -- 404 treated as idempotent success.
        assert len(result.events_failed) == 0
        assert len(result.events_synced) == 1
        assert result.events_synced[0].action_taken == "deleted"

    def test_no_context_graceful_degradation(self) -> None:
        """Graceful degradation: credentials fail, extraction proceeds without context."""
        events = [
            _make_event(
                title="Team Standup",
                action="update",
                start="2026-02-19T10:00:00",
                end="2026-02-19T10:30:00",
                attendees=["Alice", "Bob"],
                reasoning="Alice asks to move standup to 10 AM. "
                "No calendar context available.",
            ),
        ]

        result, mocks = _run_crud_e2e(
            "samples/update_meeting.txt",
            events,
            context_side_effect=RuntimeError("No credentials available"),
        )

        # Pipeline should still succeed (graceful degradation).
        assert len(result.events_extracted) == 1

        # Warning about context unavailability should be recorded.
        assert any("context unavailable" in w.lower() for w in result.warnings)

        # Calendar context should have been empty (no id_map).
        call_kwargs = mocks.gemini.extract_events.call_args
        assert call_kwargs.kwargs["calendar_context"] == ""

        # Without existing_event_id, update falls back to search-based method.
        mocks.client.find_and_update_event.assert_called_once()
        mocks.client.update_event.assert_not_called()

    def test_update_without_event_id_uses_search(self) -> None:
        """Update with no existing_event_id falls back to search-based method."""
        events = [
            _make_event(
                title="Team Standup",
                action="update",
                start="2026-02-19T10:00:00",
                end="2026-02-19T10:30:00",
                attendees=["Alice", "Bob"],
                reasoning="Alice moves standup to 10 AM. "
                "No existing event ID available.",
            ),
        ]

        result, mocks = _run_crud_e2e(
            "samples/update_meeting.txt",
            events,
        )

        # Search-based method used when no existing_event_id.
        mocks.client.find_and_update_event.assert_called_once()
        mocks.client.update_event.assert_not_called()

        assert len(result.events_synced) == 1
        assert result.events_synced[0].action_taken == "updated"

        # Verify demo output shows [UPDATE].
        output = format_pipeline_result(result)
        assert "[UPDATE]" in output
