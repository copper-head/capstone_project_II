"""Unit tests for the pipeline orchestrator (25 tests).

Tests cover: full-flow success, empty parse, no-events extraction,
extraction failure, partial sync failure, all sync failures, dry-run,
duration tracking, create/update/delete action dispatch, speakers list,
owner forwarding, current-datetime forwarding, calendar context passing,
graceful degradation on credential failure, id_map storage,
dry-run with context fetch, direct ID-based update/delete dispatch,
404 fallback on update (falls back to create), 404 fallback on delete
(idempotent success), fallback to search when existing_event_id not in
id_map, and id_map reverse lookup correctness.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from cal_ai.calendar.context import CalendarContext
from cal_ai.calendar.exceptions import CalendarNotFoundError
from cal_ai.exceptions import ExtractionError
from cal_ai.models.extraction import ExtractedEvent, ExtractionResult, ValidatedEvent
from cal_ai.models.transcript import TranscriptParseResult, Utterance
from cal_ai.pipeline import (
    run_pipeline,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_utterances(speakers: list[str] | None = None) -> list[Utterance]:
    """Build a list of stub utterances for the given speakers."""
    speakers = speakers or ["Alice", "Bob"]
    return [
        Utterance(speaker=s, text=f"Hello from {s}", line_number=i + 1)
        for i, s in enumerate(speakers)
    ]


def _make_parse_result(
    speakers: list[str] | None = None,
    utterances: list[Utterance] | None = None,
) -> TranscriptParseResult:
    """Build a stub ``TranscriptParseResult``."""
    speakers = speakers or ["Alice", "Bob"]
    utterances = utterances or _make_utterances(speakers)
    return TranscriptParseResult(
        utterances=utterances,
        speakers=speakers,
        warnings=[],
        source="test.txt",
    )


def _make_extracted_event(
    title: str = "Lunch with Bob",
    action: str = "create",
    confidence: str = "high",
    existing_event_id: int | None = None,
) -> ExtractedEvent:
    """Build a stub ``ExtractedEvent``."""
    return ExtractedEvent(
        title=title,
        start_time="2026-02-19T12:00:00",
        end_time="2026-02-19T13:00:00",
        location="Cafe",
        attendees=["Alice", "Bob"],
        confidence=confidence,
        reasoning="Alice proposed lunch and Bob confirmed.",
        assumptions=["Duration assumed 1 hour"],
        action=action,
        existing_event_id=existing_event_id,
    )


def _make_extraction_result(
    events: list[ExtractedEvent] | None = None,
) -> ExtractionResult:
    """Build a stub ``ExtractionResult``."""
    if events is None:
        events = [_make_extracted_event()]
    return ExtractionResult(events=events, summary="Extracted events")


def _make_validated_event(
    title: str = "Lunch with Bob",
    action: str = "create",
    existing_event_id: int | None = None,
) -> ValidatedEvent:
    """Build a stub ``ValidatedEvent``."""
    return ValidatedEvent(
        title=title,
        start_time=datetime(2026, 2, 19, 12, 0),
        end_time=datetime(2026, 2, 19, 13, 0),
        location="Cafe",
        attendees=["Alice", "Bob"],
        confidence="high",
        reasoning="Alice proposed lunch and Bob confirmed.",
        assumptions=["Duration assumed 1 hour"],
        action=action,
        existing_event_id=existing_event_id,
    )


def _make_settings() -> MagicMock:
    """Build a mock Settings object."""
    settings = MagicMock()
    settings.gemini_api_key = "fake-key"
    settings.timezone = "America/Vancouver"
    settings.google_account_email = "test@example.com"
    return settings


def _make_calendar_context(
    events_text: str = "",
    id_map: dict[int, str] | None = None,
    event_count: int = 0,
) -> CalendarContext:
    """Build a stub ``CalendarContext``."""
    return CalendarContext(
        events_text=events_text,
        id_map=id_map or {},
        event_count=event_count,
    )


def _patch_pipeline_deps(
    parse_result: TranscriptParseResult | None = None,
    extraction_result: ExtractionResult | None = None,
    validated_events: list[ValidatedEvent] | None = None,
    settings: MagicMock | None = None,
    extract_side_effect: Exception | None = None,
    sync_side_effects: list[dict | Exception] | None = None,
    calendar_context: CalendarContext | None = None,
    context_side_effect: Exception | None = None,
):
    """Return a context manager that patches all pipeline external deps.

    Returns a dict of mocks keyed by name for assertions.
    """
    parse_result = parse_result or _make_parse_result()
    extraction_result = extraction_result or _make_extraction_result()
    validated_events = validated_events or [_make_validated_event()]
    settings = settings or _make_settings()
    calendar_context = calendar_context or _make_calendar_context()

    mock_parse = MagicMock(return_value=parse_result)

    mock_gemini = MagicMock()
    if extract_side_effect:
        mock_gemini.extract_events.side_effect = extract_side_effect
    else:
        mock_gemini.extract_events.return_value = extraction_result
    mock_gemini.validate_events.return_value = validated_events

    mock_gemini_cls = MagicMock(return_value=mock_gemini)

    mock_settings = MagicMock(return_value=settings)

    mock_creds = MagicMock()
    mock_client = MagicMock()

    # Default sync behaviour: create returns {"id": "evt-1"}
    if sync_side_effects is not None:
        mock_client.create_event.side_effect = sync_side_effects
        mock_client.find_and_update_event.side_effect = sync_side_effects
        mock_client.find_and_delete_event.side_effect = sync_side_effects
    else:
        mock_client.create_event.return_value = {"id": "evt-1"}
        mock_client.find_and_update_event.return_value = {"id": "evt-2"}
        mock_client.find_and_delete_event.return_value = True
        mock_client.update_event.return_value = {"id": "evt-updated"}
        mock_client.delete_event.return_value = None

    mock_cal_cls = MagicMock(return_value=mock_client)
    mock_get_creds = MagicMock(return_value=mock_creds)

    # Calendar context mock
    mock_fetch_context = MagicMock()
    if context_side_effect:
        mock_fetch_context.side_effect = context_side_effect
    else:
        mock_fetch_context.return_value = calendar_context

    class _Ctx:
        """Holds all mocks for the patched pipeline dependencies."""

        def __init__(self):
            self.parse = mock_parse
            self.gemini = mock_gemini
            self.gemini_cls = mock_gemini_cls
            self.settings_fn = mock_settings
            self.settings = settings
            self.creds = mock_creds
            self.client = mock_client
            self.cal_cls = mock_cal_cls
            self.get_creds = mock_get_creds
            self.fetch_context = mock_fetch_context
            self._patches = []
            self._started = []

        def __enter__(self):
            targets = [
                ("cal_ai.pipeline.parse_transcript_file", self.parse),
                ("cal_ai.pipeline.GeminiClient", self.gemini_cls),
                ("cal_ai.pipeline.load_settings", self.settings_fn),
                ("cal_ai.pipeline.get_calendar_credentials", self.get_creds),
                ("cal_ai.pipeline.GoogleCalendarClient", self.cal_cls),
                ("cal_ai.pipeline.fetch_calendar_context", self.fetch_context),
            ]
            for target, mock_obj in targets:
                p = patch(target, mock_obj)
                self._patches.append(p)
                self._started.append(p.start())
            return self

        def __exit__(self, *args):
            for p in self._patches:
                p.stop()

    return _Ctx()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPipeline:
    """Unit tests for ``cal_ai.pipeline.run_pipeline``."""

    def test_pipeline_full_flow_success(self, tmp_path: Path) -> None:
        """Happy path: parse -> context fetch -> extract -> sync all succeed."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Hi\n[Bob]: Hello\n")

        events = [
            _make_extracted_event("Event A"),
            _make_extracted_event("Event B"),
        ]
        extraction = _make_extraction_result(events)
        validated = [
            _make_validated_event("Event A"),
            _make_validated_event("Event B"),
        ]

        with _patch_pipeline_deps(
            extraction_result=extraction,
            validated_events=validated,
        ):
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
            )

        assert result.utterance_count == 2
        assert len(result.events_extracted) == 2
        assert len(result.events_synced) == 2
        assert len(result.events_failed) == 0
        assert result.duration_seconds > 0

    def test_pipeline_parse_returns_empty(self, tmp_path: Path) -> None:
        """Parser returns 0 utterances -> utterance_count=0, no events."""
        transcript = tmp_path / "empty.txt"
        transcript.write_text("")

        empty_parse = TranscriptParseResult(
            utterances=[],
            speakers=[],
            warnings=[],
            source=str(transcript),
        )

        with _patch_pipeline_deps(parse_result=empty_parse) as ctx:
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
            )

        assert result.utterance_count == 0
        assert result.events_extracted == []
        # LLM should not be called when there are no utterances.
        ctx.gemini.extract_events.assert_not_called()

    def test_pipeline_extraction_returns_no_events(
        self, tmp_path: Path
    ) -> None:
        """Parser succeeds, LLM finds nothing -> no events, no sync calls."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Nice weather\n")

        extraction = _make_extraction_result(events=[])

        with _patch_pipeline_deps(extraction_result=extraction) as ctx:
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
            )

        assert result.events_extracted == []
        assert result.events_synced == []
        # Calendar client IS constructed for context fetch, but no sync calls.
        ctx.client.create_event.assert_not_called()

    def test_pipeline_extraction_failure_does_not_crash(
        self, tmp_path: Path
    ) -> None:
        """LLM raises ExtractionError -> pipeline returns 0 events, warning logged."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Hey\n")

        with _patch_pipeline_deps(
            extract_side_effect=ExtractionError("API down"),
        ):
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
            )

        assert result.events_extracted == []
        assert len(result.warnings) >= 1
        assert any("LLM extraction failed" in w for w in result.warnings)

    def test_pipeline_single_event_sync_failure_continues(
        self, tmp_path: Path
    ) -> None:
        """1 of 3 events fails sync -> 2 synced, 1 failed."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Hi\n")

        events = [
            _make_extracted_event("A"),
            _make_extracted_event("B"),
            _make_extracted_event("C"),
        ]
        extraction = _make_extraction_result(events)
        validated = [
            _make_validated_event("A"),
            _make_validated_event("B"),
            _make_validated_event("C"),
        ]

        with _patch_pipeline_deps(
            extraction_result=extraction,
            validated_events=validated,
        ) as ctx:
            # Second create call raises, first and third succeed.
            ctx.client.create_event.side_effect = [
                {"id": "evt-1"},
                RuntimeError("Calendar API error"),
                {"id": "evt-3"},
            ]
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
            )

        assert len(result.events_synced) == 2
        assert len(result.events_failed) == 1
        assert "Calendar API error" in result.events_failed[0].error

    def test_pipeline_all_events_sync_failure(self, tmp_path: Path) -> None:
        """All events fail sync -> events_synced empty, all in events_failed."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Hi\n")

        events = [
            _make_extracted_event("A"),
            _make_extracted_event("B"),
        ]
        extraction = _make_extraction_result(events)
        validated = [
            _make_validated_event("A"),
            _make_validated_event("B"),
        ]

        with _patch_pipeline_deps(
            extraction_result=extraction,
            validated_events=validated,
        ) as ctx:
            ctx.client.create_event.side_effect = RuntimeError("API down")
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
            )

        assert len(result.events_synced) == 0
        assert len(result.events_failed) == 2

    def test_pipeline_dry_run_skips_sync(self, tmp_path: Path) -> None:
        """dry_run=True -> calendar sync methods never called, context still fetched."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Hi\n")

        ctx_data = _make_calendar_context(
            events_text="[1] Standup | 2026-02-19T09:00 - 2026-02-19T10:00",
            id_map={1: "real-uuid-1"},
            event_count=1,
        )

        with _patch_pipeline_deps(calendar_context=ctx_data) as ctx:
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
                dry_run=True,
            )

        # Context should be fetched even in dry-run.
        ctx.fetch_context.assert_called_once()
        # Sync methods should NOT be called.
        ctx.client.create_event.assert_not_called()
        ctx.client.find_and_update_event.assert_not_called()
        ctx.client.find_and_delete_event.assert_not_called()
        # Events should still be extracted and listed as "would_*" synced.
        assert len(result.events_synced) >= 1
        for sync in result.events_synced:
            assert sync.action_taken.startswith("would_")

    def test_pipeline_records_duration(self, tmp_path: Path) -> None:
        """Duration tracking -> duration_seconds > 0."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Hi\n")

        with _patch_pipeline_deps():
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
                dry_run=True,
            )

        assert result.duration_seconds > 0

    def test_pipeline_handles_create_action(self, tmp_path: Path) -> None:
        """action='create' -> create_event called."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Hi\n")

        events = [_make_extracted_event("Lunch", action="create")]
        extraction = _make_extraction_result(events)
        validated = [_make_validated_event("Lunch", action="create")]

        with _patch_pipeline_deps(
            extraction_result=extraction,
            validated_events=validated,
        ) as ctx:
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
            )

        ctx.client.create_event.assert_called_once()
        assert result.events_synced[0].action_taken == "created"

    def test_pipeline_handles_delete_action(self, tmp_path: Path) -> None:
        """action='delete' -> find_and_delete_event called."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Cancel standup\n")

        events = [_make_extracted_event("Standup", action="delete")]
        extraction = _make_extraction_result(events)
        validated = [_make_validated_event("Standup", action="delete")]

        with _patch_pipeline_deps(
            extraction_result=extraction,
            validated_events=validated,
        ) as ctx:
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
            )

        ctx.client.find_and_delete_event.assert_called_once()
        assert result.events_synced[0].action_taken == "deleted"

    def test_pipeline_handles_update_action(self, tmp_path: Path) -> None:
        """action='update' -> find_and_update_event called."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Move standup to 10\n")

        events = [_make_extracted_event("Standup", action="update")]
        extraction = _make_extraction_result(events)
        validated = [_make_validated_event("Standup", action="update")]

        with _patch_pipeline_deps(
            extraction_result=extraction,
            validated_events=validated,
        ) as ctx:
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
            )

        ctx.client.find_and_update_event.assert_called_once()
        assert result.events_synced[0].action_taken == "updated"

    def test_pipeline_speakers_found_populated(self, tmp_path: Path) -> None:
        """Speaker list from parse -> speakers_found == ['Alice', 'Bob']."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Hi\n[Bob]: Hey\n")

        parse_result = _make_parse_result(speakers=["Alice", "Bob"])

        with _patch_pipeline_deps(parse_result=parse_result):
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
                dry_run=True,
            )

        assert result.speakers_found == ["Alice", "Bob"]

    def test_pipeline_passes_owner_to_extractor(
        self, tmp_path: Path
    ) -> None:
        """Owner forwarded -> extractor called with owner='TestOwner'."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Hi\n")

        with _patch_pipeline_deps() as ctx:
            run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
                dry_run=True,
            )

        call_kwargs = ctx.gemini.extract_events.call_args
        assert call_kwargs.kwargs["owner_name"] == "TestOwner"

    def test_pipeline_passes_current_datetime_to_extractor(
        self, tmp_path: Path
    ) -> None:
        """Datetime forwarded -> extractor called with frozen datetime."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Hi\n")

        frozen_dt = datetime(2026, 2, 18, 14, 30, 0)

        with _patch_pipeline_deps() as ctx:
            run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
                dry_run=True,
                current_datetime=frozen_dt,
            )

        call_kwargs = ctx.gemini.extract_events.call_args
        assert call_kwargs.kwargs["current_datetime"] == frozen_dt

    def test_pipeline_passes_calendar_context_to_extractor(
        self, tmp_path: Path
    ) -> None:
        """Calendar context text forwarded to extract_events call."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Hi\n")

        ctx_data = _make_calendar_context(
            events_text="[1] Standup | 2026-02-19T09:00 - 2026-02-19T10:00",
            id_map={1: "real-uuid-1"},
            event_count=1,
        )

        with _patch_pipeline_deps(calendar_context=ctx_data) as ctx:
            run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
                dry_run=True,
            )

        call_kwargs = ctx.gemini.extract_events.call_args
        assert call_kwargs.kwargs["calendar_context"] == ctx_data.events_text

    def test_pipeline_stores_id_map(self, tmp_path: Path) -> None:
        """id_map from calendar context stored in PipelineResult."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Hi\n")

        expected_map = {1: "uuid-aaa", 2: "uuid-bbb"}
        ctx_data = _make_calendar_context(
            events_text="[1] A | ... \n[2] B | ...",
            id_map=expected_map,
            event_count=2,
        )

        with _patch_pipeline_deps(calendar_context=ctx_data):
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
                dry_run=True,
            )

        assert result.id_map == expected_map

    def test_pipeline_graceful_degradation_no_credentials(
        self, tmp_path: Path
    ) -> None:
        """Credential failure -> extract without context, warning recorded."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Hi\n")

        with _patch_pipeline_deps() as ctx:
            # Make credential fetch raise so calendar client construction fails.
            ctx.get_creds.side_effect = RuntimeError("No credentials")
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
                dry_run=True,
            )

        # Pipeline should still succeed (graceful degradation).
        assert len(result.events_extracted) >= 1
        # Warning about context unavailability should be recorded.
        assert any("context unavailable" in w.lower() for w in result.warnings)
        # Calendar context should be empty (default).
        call_kwargs = ctx.gemini.extract_events.call_args
        assert call_kwargs.kwargs["calendar_context"] == ""

    def test_pipeline_context_fetch_failure_degrades_gracefully(
        self, tmp_path: Path
    ) -> None:
        """fetch_calendar_context raises -> extract without context, warning."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Hi\n")

        with _patch_pipeline_deps() as ctx:
            ctx.fetch_context.side_effect = RuntimeError("API timeout")
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
                dry_run=True,
            )

        # Pipeline should still succeed.
        assert len(result.events_extracted) >= 1
        assert any("context unavailable" in w.lower() for w in result.warnings)
        call_kwargs = ctx.gemini.extract_events.call_args
        assert call_kwargs.kwargs["calendar_context"] == ""

    # ------------------------------------------------------------------
    # ID-based sync dispatch tests
    # ------------------------------------------------------------------

    def test_pipeline_update_with_existing_event_id_calls_update_event(
        self, tmp_path: Path
    ) -> None:
        """update + existing_event_id -> direct update_event(real_id, event)."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Move standup to 10\n")

        events = [_make_extracted_event("Standup", action="update", existing_event_id=1)]
        extraction = _make_extraction_result(events)
        validated = [_make_validated_event("Standup", action="update", existing_event_id=1)]
        ctx_data = _make_calendar_context(
            events_text="[1] Standup | ...",
            id_map={1: "real-uuid-standup"},
            event_count=1,
        )

        with _patch_pipeline_deps(
            extraction_result=extraction,
            validated_events=validated,
            calendar_context=ctx_data,
        ) as ctx:
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
            )

        # Direct update_event should be called with the real UUID.
        ctx.client.update_event.assert_called_once_with(
            "real-uuid-standup", validated[0]
        )
        # Search-based method should NOT be called.
        ctx.client.find_and_update_event.assert_not_called()
        assert result.events_synced[0].action_taken == "updated"
        assert result.events_synced[0].calendar_event_id == "evt-updated"

    def test_pipeline_delete_with_existing_event_id_calls_delete_event(
        self, tmp_path: Path
    ) -> None:
        """delete + existing_event_id -> direct delete_event(real_id)."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Cancel standup\n")

        events = [_make_extracted_event("Standup", action="delete", existing_event_id=2)]
        extraction = _make_extraction_result(events)
        validated = [_make_validated_event("Standup", action="delete", existing_event_id=2)]
        ctx_data = _make_calendar_context(
            events_text="[2] Standup | ...",
            id_map={2: "real-uuid-standup-2"},
            event_count=1,
        )

        with _patch_pipeline_deps(
            extraction_result=extraction,
            validated_events=validated,
            calendar_context=ctx_data,
        ) as ctx:
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
            )

        # Direct delete_event should be called with the real UUID.
        ctx.client.delete_event.assert_called_once_with("real-uuid-standup-2")
        # Search-based method should NOT be called.
        ctx.client.find_and_delete_event.assert_not_called()
        assert result.events_synced[0].action_taken == "deleted"

    def test_pipeline_update_404_falls_back_to_create(
        self, tmp_path: Path
    ) -> None:
        """update + existing_event_id + 404 -> fallback to create_event."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Move standup to 10\n")

        events = [_make_extracted_event("Standup", action="update", existing_event_id=1)]
        extraction = _make_extraction_result(events)
        validated = [_make_validated_event("Standup", action="update", existing_event_id=1)]
        ctx_data = _make_calendar_context(
            events_text="[1] Standup | ...",
            id_map={1: "real-uuid-gone"},
            event_count=1,
        )

        with _patch_pipeline_deps(
            extraction_result=extraction,
            validated_events=validated,
            calendar_context=ctx_data,
        ) as ctx:
            # update_event raises 404 -> should fallback to create.
            ctx.client.update_event.side_effect = CalendarNotFoundError(
                "Event not found"
            )
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
            )

        # update_event was attempted first.
        ctx.client.update_event.assert_called_once_with("real-uuid-gone", validated[0])
        # Fallback to create_event.
        ctx.client.create_event.assert_called_once_with(validated[0])
        # Action should report "created" (the fallback).
        assert result.events_synced[0].action_taken == "created"

    def test_pipeline_delete_404_treated_as_success(
        self, tmp_path: Path
    ) -> None:
        """delete + existing_event_id + 404 -> idempotent success (deleted)."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Cancel standup\n")

        events = [_make_extracted_event("Standup", action="delete", existing_event_id=3)]
        extraction = _make_extraction_result(events)
        validated = [_make_validated_event("Standup", action="delete", existing_event_id=3)]
        ctx_data = _make_calendar_context(
            events_text="[3] Standup | ...",
            id_map={3: "real-uuid-already-gone"},
            event_count=1,
        )

        with _patch_pipeline_deps(
            extraction_result=extraction,
            validated_events=validated,
            calendar_context=ctx_data,
        ) as ctx:
            # delete_event raises 404 -> should be treated as success.
            ctx.client.delete_event.side_effect = CalendarNotFoundError(
                "Event not found"
            )
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
            )

        ctx.client.delete_event.assert_called_once_with("real-uuid-already-gone")
        # No failure -- treated as idempotent delete.
        assert len(result.events_failed) == 0
        assert result.events_synced[0].action_taken == "deleted"

    def test_pipeline_update_no_existing_id_uses_search(
        self, tmp_path: Path
    ) -> None:
        """update + no existing_event_id -> find_and_update_event (search)."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Move standup to 10\n")

        events = [_make_extracted_event("Standup", action="update")]
        extraction = _make_extraction_result(events)
        validated = [_make_validated_event("Standup", action="update")]

        with _patch_pipeline_deps(
            extraction_result=extraction,
            validated_events=validated,
        ) as ctx:
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
            )

        # Search-based method used when no existing_event_id.
        ctx.client.find_and_update_event.assert_called_once()
        ctx.client.update_event.assert_not_called()
        assert result.events_synced[0].action_taken == "updated"

    def test_pipeline_delete_no_existing_id_uses_search(
        self, tmp_path: Path
    ) -> None:
        """delete + no existing_event_id -> find_and_delete_event (search)."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Cancel standup\n")

        events = [_make_extracted_event("Standup", action="delete")]
        extraction = _make_extraction_result(events)
        validated = [_make_validated_event("Standup", action="delete")]

        with _patch_pipeline_deps(
            extraction_result=extraction,
            validated_events=validated,
        ) as ctx:
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
            )

        ctx.client.find_and_delete_event.assert_called_once()
        ctx.client.delete_event.assert_not_called()
        assert result.events_synced[0].action_taken == "deleted"

    def test_pipeline_existing_id_not_in_id_map_falls_back_to_search(
        self, tmp_path: Path
    ) -> None:
        """existing_event_id=99 not in id_map -> fallback to search method."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Move standup to 10\n")

        # Event references id=99, but id_map only has id=1.
        events = [_make_extracted_event("Standup", action="update", existing_event_id=99)]
        extraction = _make_extraction_result(events)
        validated = [_make_validated_event("Standup", action="update", existing_event_id=99)]
        ctx_data = _make_calendar_context(
            events_text="[1] Other | ...",
            id_map={1: "real-uuid-other"},
            event_count=1,
        )

        with _patch_pipeline_deps(
            extraction_result=extraction,
            validated_events=validated,
            calendar_context=ctx_data,
        ) as ctx:
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
            )

        # Should fall back to search-based method since id=99 not in map.
        ctx.client.find_and_update_event.assert_called_once()
        ctx.client.update_event.assert_not_called()
        assert result.events_synced[0].action_taken == "updated"
