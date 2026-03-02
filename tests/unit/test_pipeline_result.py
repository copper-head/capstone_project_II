"""Unit tests for PipelineResult new fields (memory_actions, extraction_usage_metadata).

Tests cover: default values for new fields, population of extraction_usage_metadata
in Stage 2, and population of memory_actions in Stage 4.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from cal_ai.memory.models import MemoryAction
from cal_ai.models.extraction import ExtractedEvent, ExtractionResult
from cal_ai.models.transcript import TranscriptParseResult, Utterance
from cal_ai.pipeline import PipelineResult, run_pipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_utterances() -> list[Utterance]:
    return [
        Utterance(speaker="Alice", text="Hello", line_number=1),
        Utterance(speaker="Bob", text="Hi there", line_number=2),
    ]


def _make_parse_result() -> TranscriptParseResult:
    return TranscriptParseResult(
        utterances=_make_utterances(),
        speakers=["Alice", "Bob"],
        warnings=[],
        source="test.txt",
    )


def _make_extracted_event() -> ExtractedEvent:
    return ExtractedEvent(
        title="Lunch",
        start_time="2026-02-19T12:00:00",
        end_time="2026-02-19T13:00:00",
        confidence="high",
        reasoning="Test event",
        action="create",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPipelineResultDefaults:
    """Tests for default values of new PipelineResult fields."""

    def test_memory_actions_default_empty(self) -> None:
        """memory_actions defaults to an empty list."""
        result = PipelineResult(transcript_path=Path("test.txt"))
        assert result.memory_actions == []

    def test_extraction_usage_metadata_default_empty(self) -> None:
        """extraction_usage_metadata defaults to an empty list."""
        result = PipelineResult(transcript_path=Path("test.txt"))
        assert result.extraction_usage_metadata == []

    def test_existing_fields_unchanged(self) -> None:
        """Existing fields still have correct defaults after new fields added."""
        result = PipelineResult(transcript_path=Path("test.txt"))
        assert result.events_extracted == []
        assert result.events_synced == []
        assert result.events_failed == []
        assert result.warnings == []
        assert result.memory_usage_metadata == []
        assert result.memories_added == 0


class TestExtractionUsageMetadata:
    """Tests for extraction_usage_metadata population in Stage 2."""

    def test_extraction_usage_populated(
        self,
        tmp_path: Path,
        monkeypatch_env: dict[str, str],
    ) -> None:
        """run_pipeline populates extraction_usage_metadata from ExtractionResult."""
        transcript = tmp_path / "test.txt"
        transcript.write_text("[Alice]: Hello\n[Bob]: Hi\n")

        mock_usage = MagicMock()
        mock_usage.prompt_token_count = 100
        mock_usage.candidates_token_count = 50

        extraction_result = ExtractionResult(
            events=[_make_extracted_event()],
            summary="Test extraction",
            usage_metadata=[mock_usage],
        )

        mock_gemini = MagicMock()
        mock_gemini.extract_events.return_value = extraction_result
        mock_gemini.validate_events.return_value = []

        with (
            patch("cal_ai.pipeline.parse_transcript_file", return_value=_make_parse_result()),
            patch("cal_ai.pipeline.load_settings") as mock_settings,
            patch("cal_ai.pipeline.MemoryStore"),
            patch("cal_ai.pipeline.format_memory_context", return_value=""),
            patch("cal_ai.pipeline.GeminiClient", return_value=mock_gemini),
            patch("cal_ai.pipeline._build_calendar_client", side_effect=Exception("no creds")),
            patch("cal_ai.pipeline.run_memory_write") as mock_mem_write,
        ):
            mock_settings.return_value = MagicMock(
                gemini_api_key="test-key",
                memory_db_path="test.db",
            )
            mock_mem_write.return_value = MagicMock(
                memories_added=0,
                memories_updated=0,
                memories_deleted=0,
                usage_metadata=[],
                actions=[],
            )

            result = run_pipeline(
                transcript_path=transcript,
                owner="Test User",
                dry_run=True,
            )

        assert len(result.extraction_usage_metadata) == 1
        assert result.extraction_usage_metadata[0].prompt_token_count == 100


class TestMemoryActions:
    """Tests for memory_actions population in Stage 4."""

    def test_memory_actions_populated(
        self,
        tmp_path: Path,
        monkeypatch_env: dict[str, str],
    ) -> None:
        """run_pipeline populates memory_actions from write_result.actions."""
        transcript = tmp_path / "test.txt"
        transcript.write_text("[Alice]: Hello\n[Bob]: Hi\n")

        extraction_result = ExtractionResult(
            events=[],
            summary="No events",
            usage_metadata=[],
        )

        mock_actions = [
            MemoryAction(
                action="ADD",
                category="preferences",
                key="lunch_time",
                new_value="noon",
                confidence="high",
                reasoning="Alice mentioned lunch preference",
            ),
        ]

        mock_gemini = MagicMock()
        mock_gemini.extract_events.return_value = extraction_result

        mock_write_result = MagicMock(
            memories_added=1,
            memories_updated=0,
            memories_deleted=0,
            usage_metadata=[],
            actions=mock_actions,
        )

        with (
            patch("cal_ai.pipeline.parse_transcript_file", return_value=_make_parse_result()),
            patch("cal_ai.pipeline.load_settings") as mock_settings,
            patch("cal_ai.pipeline.MemoryStore"),
            patch("cal_ai.pipeline.format_memory_context", return_value=""),
            patch("cal_ai.pipeline.GeminiClient", return_value=mock_gemini),
            patch("cal_ai.pipeline._build_calendar_client", side_effect=Exception("no creds")),
            patch("cal_ai.pipeline.run_memory_write", return_value=mock_write_result),
        ):
            mock_settings.return_value = MagicMock(
                gemini_api_key="test-key",
                memory_db_path="test.db",
            )

            result = run_pipeline(
                transcript_path=transcript,
                owner="Test User",
                dry_run=False,
            )

        assert len(result.memory_actions) == 1
        assert result.memory_actions[0].action == "ADD"
        assert result.memory_actions[0].key == "lunch_time"

    def test_memory_actions_empty_in_dry_run(
        self,
        tmp_path: Path,
        monkeypatch_env: dict[str, str],
    ) -> None:
        """In dry-run mode, memory_actions stays empty (Stage 4 skipped)."""
        transcript = tmp_path / "test.txt"
        transcript.write_text("[Alice]: Hello\n[Bob]: Hi\n")

        extraction_result = ExtractionResult(
            events=[],
            summary="No events",
            usage_metadata=[],
        )

        mock_gemini = MagicMock()
        mock_gemini.extract_events.return_value = extraction_result

        with (
            patch("cal_ai.pipeline.parse_transcript_file", return_value=_make_parse_result()),
            patch("cal_ai.pipeline.load_settings") as mock_settings,
            patch("cal_ai.pipeline.MemoryStore"),
            patch("cal_ai.pipeline.format_memory_context", return_value=""),
            patch("cal_ai.pipeline.GeminiClient", return_value=mock_gemini),
            patch("cal_ai.pipeline._build_calendar_client", side_effect=Exception("no creds")),
        ):
            mock_settings.return_value = MagicMock(
                gemini_api_key="test-key",
                memory_db_path="test.db",
            )

            result = run_pipeline(
                transcript_path=transcript,
                owner="Test User",
                dry_run=True,
            )

        assert result.memory_actions == []
