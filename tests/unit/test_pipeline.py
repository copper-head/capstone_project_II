"""Unit tests for the pipeline orchestrator (14 tests).

Tests cover: full-flow success, empty parse, no-events extraction,
extraction failure, partial sync failure, all sync failures, dry-run,
duration tracking, create/update/delete action dispatch, speakers list,
owner forwarding, and current-datetime forwarding.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    )


def _make_settings() -> MagicMock:
    """Build a mock Settings object."""
    settings = MagicMock()
    settings.gemini_api_key = "fake-key"
    settings.timezone = "America/Vancouver"
    settings.google_account_email = "test@example.com"
    return settings


def _patch_pipeline_deps(
    parse_result: TranscriptParseResult | None = None,
    extraction_result: ExtractionResult | None = None,
    validated_events: list[ValidatedEvent] | None = None,
    settings: MagicMock | None = None,
    extract_side_effect: Exception | None = None,
    sync_side_effects: list[dict | Exception] | None = None,
):
    """Return a context manager that patches all pipeline external deps.

    Returns a dict of mocks keyed by name for assertions.
    """
    parse_result = parse_result or _make_parse_result()
    extraction_result = extraction_result or _make_extraction_result()
    validated_events = validated_events or [_make_validated_event()]
    settings = settings or _make_settings()

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

    mock_cal_cls = MagicMock(return_value=mock_client)
    mock_get_creds = MagicMock(return_value=mock_creds)

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
            self._patches = []
            self._started = []

        def __enter__(self):
            targets = [
                ("cal_ai.pipeline.parse_transcript_file", self.parse),
                ("cal_ai.pipeline.GeminiClient", self.gemini_cls),
                ("cal_ai.pipeline.load_settings", self.settings_fn),
                ("cal_ai.pipeline.get_calendar_credentials", self.get_creds),
                ("cal_ai.pipeline.GoogleCalendarClient", self.cal_cls),
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
        """Happy path: parse -> extract -> sync all succeed."""
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
        """Parser succeeds, LLM finds nothing -> no events, no calendar calls."""
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
        # Calendar client should never have been constructed.
        ctx.cal_cls.assert_not_called()

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

    def test_pipeline_dry_run_skips_calendar(self, tmp_path: Path) -> None:
        """dry_run=True -> calendar client methods never called."""
        transcript = tmp_path / "sample.txt"
        transcript.write_text("[Alice]: Hi\n")

        with _patch_pipeline_deps() as ctx:
            result = run_pipeline(
                transcript_path=transcript,
                owner="TestOwner",
                dry_run=True,
            )

        # Calendar client should not be constructed in dry-run.
        ctx.cal_cls.assert_not_called()
        ctx.get_creds.assert_not_called()
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
