"""Unit tests for the demo output formatter (14 tests).

Tests cover: transcript info display, extracted event details, AI reasoning,
calendar operation markers, summary counts, zero-events message, dry-run
markers, failed event errors, assumptions rendering, pipeline duration,
matched event info for updates, matched event info for deletes, dry-run
update display, and dry-run delete display.
"""

from __future__ import annotations

from pathlib import Path

from cal_ai.demo_output import format_pipeline_result
from cal_ai.models.extraction import ExtractedEvent
from cal_ai.pipeline import EventSyncResult, FailedEvent, PipelineResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    title: str = "Lunch with Bob",
    action: str = "create",
    confidence: str = "high",
    start_time: str = "2026-02-19T12:00:00",
    end_time: str = "2026-02-19T13:00:00",
    location: str | None = "New place on 5th",
    attendees: list[str] | None = None,
    reasoning: str = "Alice explicitly proposes lunch on Thursday at noon and Bob confirms.",
    assumptions: list[str] | None = None,
) -> ExtractedEvent:
    """Build a stub ``ExtractedEvent`` with sensible defaults."""
    return ExtractedEvent(
        title=title,
        start_time=start_time,
        end_time=end_time,
        location=location,
        attendees=attendees or ["Alice", "Bob"],
        confidence=confidence,
        reasoning=reasoning,
        assumptions=assumptions or ["Duration assumed to be 1 hour"],
        action=action,
    )


def _make_sync_result(
    event: ExtractedEvent | None = None,
    action_taken: str = "created",
    calendar_event_id: str | None = "abc123",
    matched_event_title: str | None = None,
    matched_event_time: str | None = None,
) -> EventSyncResult:
    """Build a stub ``EventSyncResult``."""
    return EventSyncResult(
        event=event or _make_event(),
        action_taken=action_taken,
        calendar_event_id=calendar_event_id,
        success=True,
        matched_event_title=matched_event_title,
        matched_event_time=matched_event_time,
    )


def _make_failed_event(
    event: ExtractedEvent | None = None,
    error: str = "Calendar API timeout",
) -> FailedEvent:
    """Build a stub ``FailedEvent``."""
    return FailedEvent(
        event=event or _make_event(),
        error=error,
    )


def _make_result(
    transcript_path: str = "samples/simple_lunch.txt",
    speakers: list[str] | None = None,
    utterance_count: int = 3,
    events: list[ExtractedEvent] | None = None,
    synced: list[EventSyncResult] | None = None,
    failed: list[FailedEvent] | None = None,
    warnings: list[str] | None = None,
    duration: float = 2.3,
    dry_run: bool = False,
) -> PipelineResult:
    """Build a ``PipelineResult`` with sensible defaults for testing."""
    default_event = _make_event()
    default_events = events if events is not None else [default_event]

    if synced is None and not dry_run:
        synced = [_make_sync_result(event=e, action_taken="created") for e in default_events]
    elif synced is None and dry_run:
        synced = [
            EventSyncResult(
                event=e,
                action_taken=f"would_{e.action}",
                success=True,
            )
            for e in default_events
        ]

    return PipelineResult(
        transcript_path=Path(transcript_path),
        speakers_found=speakers or ["Alice", "Bob"],
        utterance_count=utterance_count,
        events_extracted=default_events,
        events_synced=synced or [],
        events_failed=failed or [],
        warnings=warnings or [],
        duration_seconds=duration,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDemoOutput:
    """Unit tests for ``cal_ai.demo_output.format_pipeline_result``."""

    def test_output_contains_transcript_info(self) -> None:
        """Stage 1 section contains file path, speakers, and utterance count."""
        result = _make_result(
            transcript_path="samples/simple_lunch.txt",
            speakers=["Alice", "Bob"],
            utterance_count=3,
        )

        output = format_pipeline_result(result)

        assert "STAGE 1: Transcript Loaded" in output
        assert "samples/simple_lunch.txt" in output
        assert "Alice" in output
        assert "Bob" in output
        assert "3 lines" in output

    def test_output_contains_extracted_events(self) -> None:
        """Stage 2 section contains event titles, times, and locations."""
        event_a = _make_event(
            title="Lunch with Bob",
            start_time="2026-02-19T12:00:00",
            end_time="2026-02-19T13:00:00",
            location="New place on 5th",
        )
        event_b = _make_event(
            title="Code Review",
            start_time="2026-02-20T14:00:00",
            end_time="2026-02-20T15:00:00",
            location="Meeting Room A",
        )
        result = _make_result(
            events=[event_a, event_b],
            synced=[
                _make_sync_result(event=event_a),
                _make_sync_result(event=event_b),
            ],
        )

        output = format_pipeline_result(result)

        assert "STAGE 2: Events Extracted" in output
        assert "Found 2 event(s)" in output
        assert "Lunch with Bob" in output
        assert "Code Review" in output
        assert "New place on 5th" in output
        assert "Meeting Room A" in output
        # Check time formatting -- the formatter converts ISO to human-readable.
        assert "12:00" in output
        assert "02:00" in output or "14:00" in output or "2:00" in output

    def test_output_contains_ai_reasoning(self) -> None:
        """Output contains the exact AI reasoning string for each event."""
        reasoning_text = "Alice explicitly proposes lunch on Thursday at noon and Bob confirms."
        event = _make_event(reasoning=reasoning_text)
        result = _make_result(events=[event])

        output = format_pipeline_result(result)

        assert "AI Reasoning:" in output
        assert reasoning_text in output

    def test_output_contains_calendar_operations(self) -> None:
        """Stage 3 section contains [CREATE] and [UPDATE] action markers."""
        event_create = _make_event(title="Lunch", action="create")
        event_update = _make_event(title="Standup", action="update")
        result = _make_result(
            events=[event_create, event_update],
            synced=[
                _make_sync_result(event=event_create, action_taken="created"),
                _make_sync_result(event=event_update, action_taken="updated"),
            ],
        )

        output = format_pipeline_result(result)

        assert "STAGE 3: Calendar Operations" in output
        assert "[CREATE]" in output
        assert "[UPDATE]" in output

    def test_output_contains_summary_counts(self) -> None:
        """Summary section contains correct event, synced, and failed tallies."""
        events = [
            _make_event(title="A"),
            _make_event(title="B"),
            _make_event(title="C"),
        ]
        synced = [
            _make_sync_result(event=events[0]),
            _make_sync_result(event=events[1]),
        ]
        failed = [_make_failed_event(event=events[2])]

        result = _make_result(
            events=events,
            synced=synced,
            failed=failed,
        )

        output = format_pipeline_result(result)

        assert "SUMMARY" in output
        assert "Events extracted: 3" in output
        assert "Successfully synced: 2" in output
        assert "Failed: 1" in output

    def test_output_zero_events_message(self) -> None:
        """Zero events produces 'No calendar events detected' message."""
        result = _make_result(
            events=[],
            synced=[],
            failed=[],
        )

        output = format_pipeline_result(result)

        assert "No calendar events detected in this conversation." in output

    def test_output_dry_run_shows_would_create(self) -> None:
        """Dry-run mode produces [DRY RUN] markers instead of [CREATE]."""
        event = _make_event(title="Lunch with Bob", action="create")
        result = _make_result(
            events=[event],
            dry_run=True,
        )

        output = format_pipeline_result(result)

        assert "[DRY RUN]" in output
        assert "Would create" in output
        assert '"Lunch with Bob"' in output
        # Should NOT contain the normal [CREATE] tag.
        assert "[CREATE]" not in output

    def test_output_failed_event_shows_error(self) -> None:
        """Failed sync event displays inline error message."""
        event = _make_event(title="Team Meeting")
        error_msg = "Calendar API returned 503 Service Unavailable"
        result = _make_result(
            events=[event],
            synced=[],
            failed=[_make_failed_event(event=event, error=error_msg)],
        )

        output = format_pipeline_result(result)

        assert "[FAILED]" in output
        assert '"Team Meeting"' in output
        assert error_msg in output

    def test_output_contains_assumptions(self) -> None:
        """Both assumption strings appear in the output."""
        assumptions = [
            "Duration assumed to be 1 hour",
            "Location inferred from prior context",
        ]
        event = _make_event(assumptions=assumptions)
        result = _make_result(events=[event])

        output = format_pipeline_result(result)

        assert "Assumptions:" in output
        assert "Duration assumed to be 1 hour" in output
        assert "Location inferred from prior context" in output

    def test_output_contains_duration(self) -> None:
        """Summary section contains the pipeline duration value."""
        result = _make_result(duration=2.3)

        output = format_pipeline_result(result)

        assert "Pipeline duration:" in output
        assert "2.3s" in output

    def test_output_update_shows_matched_event(self) -> None:
        """UPDATE action displays 'Matched existing: <title> at <time>'."""
        event = _make_event(title="Team Standup", action="update")
        result = _make_result(
            events=[event],
            synced=[
                _make_sync_result(
                    event=event,
                    action_taken="updated",
                    matched_event_title="Team Standup",
                    matched_event_time="2026-02-19T09:00:00",
                ),
            ],
        )

        output = format_pipeline_result(result)

        assert "[UPDATE]" in output
        assert "Matched existing: Team Standup at" in output
        assert "09:00 AM" in output

    def test_output_delete_shows_removing_event(self) -> None:
        """DELETE action displays 'Removing: <title> at <time>'."""
        event = _make_event(title="Code Review", action="delete")
        result = _make_result(
            events=[event],
            synced=[
                _make_sync_result(
                    event=event,
                    action_taken="deleted",
                    calendar_event_id=None,
                    matched_event_title="Code Review",
                    matched_event_time="2026-02-20T14:00:00",
                ),
            ],
        )

        output = format_pipeline_result(result)

        assert "[DELETE]" in output
        assert "Removing: Code Review at" in output
        assert "02:00 PM" in output

    def test_output_dry_run_update_shows_matched_event(self) -> None:
        """Dry-run UPDATE shows matched event info below the action line."""
        event = _make_event(title="Sprint Planning", action="update")
        result = _make_result(
            events=[event],
            synced=[
                EventSyncResult(
                    event=event,
                    action_taken="would_update",
                    success=True,
                    matched_event_title="Sprint Planning",
                    matched_event_time="2026-02-21T09:00:00",
                ),
            ],
            dry_run=True,
        )

        output = format_pipeline_result(result)

        assert "[DRY RUN]" in output
        assert "Would update" in output
        assert "Matched existing: Sprint Planning at" in output

    def test_output_dry_run_delete_shows_removing_event(self) -> None:
        """Dry-run DELETE shows removing info below the action line."""
        event = _make_event(title="Retrospective", action="delete")
        result = _make_result(
            events=[event],
            synced=[
                EventSyncResult(
                    event=event,
                    action_taken="would_delete",
                    success=True,
                    matched_event_title="Retrospective",
                    matched_event_time="2026-02-21T15:00:00",
                ),
            ],
            dry_run=True,
        )

        output = format_pipeline_result(result)

        assert "[DRY RUN]" in output
        assert "Would delete" in output
        assert "Removing: Retrospective at" in output
