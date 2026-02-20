"""Integration tests for the end-to-end pipeline (9 tests).

These tests wire the real transcript parser against real sample files but
mock the external services (Gemini LLM and Google Calendar API).  This
validates that the full pipeline -- file I/O, parsing, event extraction,
calendar sync, and demo output -- hangs together correctly.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from cal_ai.calendar.context import CalendarContext
from cal_ai.demo_output import format_pipeline_result
from cal_ai.exceptions import ExtractionError
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


def _run_e2e(
    sample_file: str,
    extracted_events: list[ExtractedEvent],
    *,
    owner: str = "Alice",
    dry_run: bool = False,
    extract_side_effect: Exception | None = None,
    create_side_effect=None,
    delete_side_effect=None,
    update_side_effect=None,
):
    """Run the pipeline end-to-end with mocked LLM and calendar.

    The real ``parse_transcript_file`` reads the actual sample file.
    Everything else (settings, Gemini, calendar credentials, calendar
    client) is mocked.

    Returns a tuple of ``(result, mocks)`` where *mocks* is a namespace
    with ``gemini``, ``client``, etc.
    """
    extraction = _make_extraction(extracted_events)
    validated = [_make_validated(e) for e in extracted_events]

    # -- Mock GeminiClient instance ----------------------------------------
    mock_gemini = MagicMock()
    if extract_side_effect is not None:
        mock_gemini.extract_events.side_effect = extract_side_effect
    else:
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

    # Apply per-method side effects if provided.
    if create_side_effect is not None:
        mock_client.create_event.side_effect = create_side_effect
    if delete_side_effect is not None:
        mock_client.find_and_delete_event.side_effect = delete_side_effect
    if update_side_effect is not None:
        mock_client.find_and_update_event.side_effect = update_side_effect

    mock_cal_cls = MagicMock(return_value=mock_client)

    # -- Mock fetch_calendar_context -----------------------------------------
    mock_fetch_context = MagicMock(return_value=CalendarContext())

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


class TestEndToEnd:
    """Integration tests for the full conversation-to-calendar pipeline."""

    def test_e2e_simple_lunch(self) -> None:
        """Full pipeline on simple_lunch.txt: 1 event extracted and synced."""
        events = [
            _make_event(
                title="Lunch with Bob",
                start="2026-02-19T12:00:00",
                end="2026-02-19T13:00:00",
                location="New place on 5th",
                attendees=["Alice", "Bob"],
                reasoning="Alice proposes lunch Thursday at noon, Bob confirms.",
            ),
        ]

        result, mocks = _run_e2e("samples/crud/simple_lunch.txt", events)

        assert result.utterance_count > 0
        assert len(result.speakers_found) >= 2
        assert "Alice" in result.speakers_found
        assert "Bob" in result.speakers_found
        assert len(result.events_extracted) == 1
        assert len(result.events_synced) == 1
        assert len(result.events_failed) == 0
        assert result.events_synced[0].action_taken == "created"
        mocks.client.create_event.assert_called_once()

    def test_e2e_multiple_events(self) -> None:
        """Full pipeline on multiple_events.txt: 3 events extracted and synced."""
        events = [
            _make_event(
                title="Daily Standup",
                start="2026-02-19T09:00:00",
                end="2026-02-19T09:30:00",
                location="Main conference room",
                attendees=["Alice", "Bob", "Carol"],
                reasoning="Bob confirms standup tomorrow at 9 AM.",
            ),
            _make_event(
                title="Code Review",
                start="2026-02-20T14:00:00",
                end="2026-02-20T15:00:00",
                location="Small meeting room",
                attendees=["Alice", "Carol"],
                reasoning="Carol suggests Wednesday at 2 PM for code review.",
            ),
            _make_event(
                title="Lunch at Thai Place",
                start="2026-02-21T12:30:00",
                end="2026-02-21T13:30:00",
                location="Thai place on Main Street",
                attendees=["Bob", "Carol"],
                reasoning="Bob and Carol agree on Friday lunch at 12:30.",
            ),
        ]

        result, mocks = _run_e2e("samples/multi_speaker/multiple_events.txt", events)

        assert result.utterance_count > 0
        assert len(result.events_extracted) == 3
        assert len(result.events_synced) == 3
        assert len(result.events_failed) == 0
        assert mocks.client.create_event.call_count == 3

    def test_e2e_cancellation(self) -> None:
        """Full pipeline on cancellation.txt: delete_event called, [DELETE] in output."""
        events = [
            _make_event(
                title="Meeting with Bob",
                action="delete",
                start="2026-02-20T10:00:00",
                end="2026-02-20T11:00:00",
                attendees=["Alice", "Bob"],
                reasoning="Alice explicitly cancels the Friday meeting.",
            ),
        ]

        result, mocks = _run_e2e("samples/crud/cancellation.txt", events)

        assert len(result.events_extracted) == 1
        assert result.events_extracted[0].action == "delete"
        assert len(result.events_synced) == 1
        assert result.events_synced[0].action_taken == "deleted"
        mocks.client.find_and_delete_event.assert_called_once()

        # Verify the demo output contains [DELETE].
        output = format_pipeline_result(result)
        assert "[DELETE]" in output

    def test_e2e_ambiguous_time(self) -> None:
        """Full pipeline on ambiguous_time.txt: low confidence event with assumptions."""
        events = [
            _make_event(
                title="Product Roadmap Planning",
                confidence="low",
                start="2026-02-26T14:00:00",
                end="2026-02-26T16:00:00",
                attendees=["Alice", "Bob"],
                reasoning="Alice and Bob discuss meeting next week but the time is vague.",
                assumptions=[
                    "Assumed Thursday afternoon based on general preference",
                    "Assumed 2-hour duration based on 'couple of hours' mention",
                ],
            ),
        ]

        result, _ = _run_e2e("samples/realistic/ambiguous_time.txt", events)

        assert len(result.events_extracted) == 1
        extracted = result.events_extracted[0]
        assert extracted.confidence == "low"
        assert len(extracted.assumptions) > 0

        # Verify the demo output shows assumptions.
        output = format_pipeline_result(result)
        assert "Assumptions:" in output

    def test_e2e_no_events(self) -> None:
        """Full pipeline on no_events.txt: 0 events, 'No calendar events detected'."""
        result, mocks = _run_e2e("samples/adversarial/no_events.txt", [])

        assert result.utterance_count > 0
        assert len(result.events_extracted) == 0
        assert len(result.events_synced) == 0
        assert len(result.events_failed) == 0

        # Calendar client is constructed for context fetch, but no sync calls.
        mocks.client.create_event.assert_not_called()
        mocks.client.find_and_update_event.assert_not_called()
        mocks.client.find_and_delete_event.assert_not_called()

        # Demo output should contain the "no events" message.
        output = format_pipeline_result(result)
        assert "No calendar events detected" in output

    def test_e2e_complex_multi_speaker(self) -> None:
        """Full pipeline on complex.txt: multiple events, mixed actions."""
        events = [
            _make_event(
                title="Sprint Retrospective",
                start="2026-02-23T10:00:00",
                end="2026-02-23T11:00:00",
                location="Large conference room",
                attendees=["Alice", "Bob", "Carol", "Dave"],
                reasoning="Dave books the retrospective for Monday at 10.",
            ),
            _make_event(
                title="Design Review",
                start="2026-02-24T15:00:00",
                end="2026-02-24T16:00:00",
                location="Design lab",
                attendees=["Bob", "Carol"],
                reasoning="Bob and Carol agree on Tuesday at 3 PM.",
            ),
            _make_event(
                title="Quarterly All-Hands",
                action="update",
                start="2026-02-25T13:00:00",
                end="2026-02-25T14:00:00",
                attendees=["Alice", "Bob", "Carol"],
                reasoning="Alice reminds the team about the Wednesday all-hands.",
            ),
            _make_event(
                title="Budget Proposal Sync",
                start="2026-02-26T09:30:00",
                end="2026-02-26T10:30:00",
                location="Alice's office",
                attendees=["Alice", "Bob"],
                reasoning="Alice and Bob agree on Thursday at 9:30.",
            ),
        ]

        result, mocks = _run_e2e("samples/multi_speaker/complex.txt", events)

        assert len(result.speakers_found) >= 3
        assert len(result.events_extracted) == 4
        # 3 creates + 1 update = 4 synced
        assert len(result.events_synced) == 4
        assert len(result.events_failed) == 0

        # Verify mixed actions: 3 creates and 1 update.
        mocks.client.create_event.assert_called()
        mocks.client.find_and_update_event.assert_called_once()

        # Check demo output has both [CREATE] and [UPDATE].
        output = format_pipeline_result(result)
        assert "[CREATE]" in output
        assert "[UPDATE]" in output

    def test_e2e_partial_sync_failure(self) -> None:
        """One calendar sync fails, others succeed; failed event has error."""
        events = [
            _make_event(
                title="Event A",
                start="2026-02-19T09:00:00",
                end="2026-02-19T10:00:00",
            ),
            _make_event(
                title="Event B",
                start="2026-02-19T11:00:00",
                end="2026-02-19T12:00:00",
            ),
            _make_event(
                title="Event C",
                start="2026-02-19T14:00:00",
                end="2026-02-19T15:00:00",
            ),
        ]

        # Second create call raises, first and third succeed.
        result, _ = _run_e2e(
            "samples/crud/simple_lunch.txt",
            events,
            create_side_effect=[
                {"id": "evt-1"},
                RuntimeError("Calendar API quota exceeded"),
                {"id": "evt-3"},
            ],
        )

        assert len(result.events_extracted) == 3
        assert len(result.events_synced) == 2
        assert len(result.events_failed) == 1
        assert "Calendar API quota exceeded" in result.events_failed[0].error

    def test_e2e_llm_failure_graceful_exit(self) -> None:
        """LLM service down: 0 events, error message, pipeline does not crash."""
        result, mocks = _run_e2e(
            "samples/crud/simple_lunch.txt",
            [],  # won't matter -- extract_events will raise
            extract_side_effect=ExtractionError("Gemini API 503: Service Unavailable"),
        )

        assert len(result.events_extracted) == 0
        assert len(result.events_synced) == 0
        assert len(result.events_failed) == 0
        # A warning should have been logged about the LLM failure.
        assert len(result.warnings) >= 1
        assert any("LLM extraction failed" in w for w in result.warnings)

        # Calendar client is constructed for context fetch, but no sync calls.
        mocks.client.create_event.assert_not_called()
        mocks.client.find_and_update_event.assert_not_called()
        mocks.client.find_and_delete_event.assert_not_called()

    def test_e2e_output_structure_has_all_stages(self) -> None:
        """Demo output contains 'STAGE 1', 'STAGE 2', 'STAGE 3', and 'SUMMARY'."""
        events = [
            _make_event(
                title="Lunch with Bob",
                start="2026-02-19T12:00:00",
                end="2026-02-19T13:00:00",
                location="New place on 5th",
                attendees=["Alice", "Bob"],
                reasoning="Alice proposes lunch and Bob confirms.",
            ),
        ]

        result, _ = _run_e2e("samples/crud/simple_lunch.txt", events)

        output = format_pipeline_result(result)

        assert "STAGE 1" in output
        assert "STAGE 2" in output
        assert "STAGE 3" in output
        assert "SUMMARY" in output
