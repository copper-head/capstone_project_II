"""Unit tests for web response schema models.

Tests cover: dataclass-to-Pydantic conversion, Path serialization, nested
model conversion, memory action mapping, token usage aggregation with cost
calculation, and graceful handling of missing usage metadata.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from cal_ai.memory.models import MemoryAction
from cal_ai.models.extraction import ExtractedEvent
from cal_ai.pipeline import EventSyncResult, FailedEvent, PipelineResult
from cal_ai.web.schemas import (
    EventResponse,
    FailedEventResponse,
    MemoryActionResponse,
    MemoryResponse,
    PipelineResultResponse,
    SyncResultResponse,
    TokenUsageResponse,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_extracted_event(**overrides: object) -> ExtractedEvent:
    """Create an ExtractedEvent with sensible defaults."""
    defaults = {
        "title": "Team Meeting",
        "start_time": "2026-03-05T10:00:00",
        "end_time": "2026-03-05T11:00:00",
        "location": "Room A",
        "attendees": ["Alice", "Bob"],
        "confidence": "high",
        "reasoning": "Explicit mention of meeting.",
        "assumptions": ["Duration assumed 1 hour"],
        "action": "create",
        "existing_event_id": None,
    }
    defaults.update(overrides)
    return ExtractedEvent(**defaults)


def _make_pipeline_result(**overrides: object) -> PipelineResult:
    """Create a PipelineResult with sensible defaults."""
    defaults = {
        "transcript_path": Path("/tmp/test.txt"),
        "speakers_found": ["Alice", "Bob"],
        "utterance_count": 5,
        "events_extracted": [],
        "events_synced": [],
        "events_failed": [],
        "warnings": [],
        "duration_seconds": 2.5,
        "dry_run": False,
        "memory_actions": [],
        "extraction_usage_metadata": [],
        "memory_usage_metadata": [],
    }
    defaults.update(overrides)
    return PipelineResult(**defaults)


def _make_usage_metadata(prompt_tokens: int = 100, candidates_tokens: int = 50) -> SimpleNamespace:
    """Create a mock Gemini SDK usage_metadata object."""
    return SimpleNamespace(
        prompt_token_count=prompt_tokens,
        candidates_token_count=candidates_tokens,
        total_token_count=prompt_tokens + candidates_tokens,
    )


# ---------------------------------------------------------------------------
# EventResponse tests
# ---------------------------------------------------------------------------


class TestEventResponse:
    """Tests for EventResponse model."""

    def test_from_extracted_event_fields(self) -> None:
        """EventResponse preserves all ExtractedEvent fields."""
        event = _make_extracted_event()
        resp = EventResponse(
            title=event.title,
            start_time=event.start_time,
            end_time=event.end_time,
            location=event.location,
            attendees=event.attendees,
            confidence=event.confidence,
            reasoning=event.reasoning,
            assumptions=event.assumptions,
            action=event.action,
            existing_event_id=event.existing_event_id,
        )
        assert resp.title == "Team Meeting"
        assert resp.start_time == "2026-03-05T10:00:00"
        assert resp.location == "Room A"
        assert resp.attendees == ["Alice", "Bob"]
        assert resp.confidence == "high"
        assert resp.action == "create"


# ---------------------------------------------------------------------------
# TokenUsageResponse tests
# ---------------------------------------------------------------------------


class TestTokenUsageResponse:
    """Tests for token usage aggregation and cost calculation."""

    def test_aggregates_from_both_metadata_lists(self) -> None:
        """Aggregates prompt + output tokens from extraction and memory metadata."""
        extraction = [_make_usage_metadata(100, 50)]
        memory = [_make_usage_metadata(200, 80), _make_usage_metadata(150, 60)]

        result = TokenUsageResponse.from_usage_metadata(extraction, memory)

        assert result.prompt_tokens == 450  # 100 + 200 + 150
        assert result.output_tokens == 190  # 50 + 80 + 60
        assert result.total_tokens == 640

    def test_estimated_cost_with_gemini_pricing(self) -> None:
        """Cost is calculated using Gemini 2.5 pricing."""
        # 1M prompt tokens = $1.25, 1M output tokens = $10.00
        meta = [_make_usage_metadata(1_000_000, 1_000_000)]

        result = TokenUsageResponse.from_usage_metadata(meta, [])

        assert result.estimated_cost_usd is not None
        # $1.25 + $10.00 = $11.25
        assert abs(result.estimated_cost_usd - 11.25) < 0.01

    def test_empty_metadata_returns_zeros(self) -> None:
        """Empty metadata lists produce zero tokens and null cost."""
        result = TokenUsageResponse.from_usage_metadata([], [])

        assert result.prompt_tokens == 0
        assert result.output_tokens == 0
        assert result.total_tokens == 0
        assert result.estimated_cost_usd is None

    def test_none_metadata_items_skipped(self) -> None:
        """None items in the metadata list are silently skipped."""
        result = TokenUsageResponse.from_usage_metadata([None], [None, None])

        assert result.prompt_tokens == 0
        assert result.output_tokens == 0

    def test_missing_attributes_treated_as_zero(self) -> None:
        """Objects without expected attributes are treated as zero."""
        bogus = SimpleNamespace()  # No prompt_token_count or candidates_token_count
        result = TokenUsageResponse.from_usage_metadata([bogus], [])

        assert result.prompt_tokens == 0
        assert result.output_tokens == 0


# ---------------------------------------------------------------------------
# MemoryActionResponse tests
# ---------------------------------------------------------------------------


class TestMemoryActionResponse:
    """Tests for memory action response model."""

    def test_from_memory_action(self) -> None:
        """MemoryActionResponse correctly maps MemoryAction fields."""
        action = MemoryAction(
            action="ADD",
            category="preferences",
            key="meeting_duration",
            new_value="1 hour default",
            confidence="high",
            reasoning="Explicitly stated preference.",
            target_memory_id=None,
        )
        resp = MemoryActionResponse(
            action=action.action,
            category=action.category,
            key=action.key,
            new_value=action.new_value,
            confidence=action.confidence,
            reasoning=action.reasoning,
        )
        assert resp.action == "ADD"
        assert resp.category == "preferences"
        assert resp.key == "meeting_duration"
        assert resp.new_value == "1 hour default"
        assert resp.confidence == "high"
        assert resp.reasoning == "Explicitly stated preference."

    def test_target_memory_id_excluded(self) -> None:
        """MemoryActionResponse does not include target_memory_id."""
        resp = MemoryActionResponse(
            action="UPDATE",
            category="people",
            key="bob",
            new_value="prefers mornings",
            confidence="medium",
            reasoning="Updated info.",
        )
        data = resp.model_dump()
        assert "target_memory_id" not in data


# ---------------------------------------------------------------------------
# MemoryResponse tests
# ---------------------------------------------------------------------------


class TestMemoryResponse:
    """Tests for the memory viewer response model."""

    def test_includes_required_fields(self) -> None:
        """MemoryResponse includes category, key, value, confidence."""
        resp = MemoryResponse(
            category="preferences",
            key="coffee",
            value="likes lattes",
            confidence="high",
        )
        data = resp.model_dump()
        assert data == {
            "category": "preferences",
            "key": "coffee",
            "value": "likes lattes",
            "confidence": "high",
        }

    def test_excludes_timestamps_and_source_count(self) -> None:
        """MemoryResponse does not have timestamp or source_count fields."""
        resp = MemoryResponse(
            category="people",
            key="alice",
            value="manager",
        )
        data = resp.model_dump()
        assert "created_at" not in data
        assert "updated_at" not in data
        assert "source_count" not in data
        assert "id" not in data


# ---------------------------------------------------------------------------
# PipelineResultResponse tests
# ---------------------------------------------------------------------------


class TestPipelineResultResponse:
    """Tests for the top-level pipeline result response model."""

    def test_path_serialized_to_string(self) -> None:
        """PipelineResult.transcript_path (Path) becomes a string."""
        result = _make_pipeline_result(transcript_path=Path("/tmp/conversation.txt"))
        resp = PipelineResultResponse.from_pipeline_result(result)

        assert resp.transcript_path == "/tmp/conversation.txt"
        assert isinstance(resp.transcript_path, str)

    def test_extracted_events_converted(self) -> None:
        """Nested ExtractedEvent objects are converted to EventResponse."""
        event = _make_extracted_event(title="Lunch with Alice")
        result = _make_pipeline_result(events_extracted=[event])
        resp = PipelineResultResponse.from_pipeline_result(result)

        assert len(resp.events_extracted) == 1
        assert isinstance(resp.events_extracted[0], EventResponse)
        assert resp.events_extracted[0].title == "Lunch with Alice"

    def test_synced_events_converted(self) -> None:
        """EventSyncResult dataclasses are converted to SyncResultResponse."""
        event = _make_extracted_event()
        sync = EventSyncResult(
            event=event,
            action_taken="created",
            calendar_event_id="cal-123",
            success=True,
            matched_event_title=None,
            matched_event_time=None,
        )
        result = _make_pipeline_result(events_synced=[sync])
        resp = PipelineResultResponse.from_pipeline_result(result)

        assert len(resp.events_synced) == 1
        assert isinstance(resp.events_synced[0], SyncResultResponse)
        assert resp.events_synced[0].action_taken == "created"
        assert resp.events_synced[0].calendar_event_id == "cal-123"

    def test_failed_events_converted(self) -> None:
        """FailedEvent dataclasses are converted to FailedEventResponse."""
        event = _make_extracted_event()
        failed = FailedEvent(event=event, error="API timeout")
        result = _make_pipeline_result(events_failed=[failed])
        resp = PipelineResultResponse.from_pipeline_result(result)

        assert len(resp.events_failed) == 1
        assert isinstance(resp.events_failed[0], FailedEventResponse)
        assert resp.events_failed[0].error == "API timeout"

    def test_memory_actions_converted(self) -> None:
        """MemoryAction objects are converted to MemoryActionResponse."""
        action = MemoryAction(
            action="ADD",
            category="vocabulary",
            key="standup",
            new_value="daily 15-min meeting",
            confidence="high",
            reasoning="Observed in conversation.",
            target_memory_id=None,
        )
        result = _make_pipeline_result(memory_actions=[action])
        resp = PipelineResultResponse.from_pipeline_result(result)

        assert len(resp.memory_actions) == 1
        assert isinstance(resp.memory_actions[0], MemoryActionResponse)
        assert resp.memory_actions[0].action == "ADD"
        assert resp.memory_actions[0].key == "standup"

    def test_token_usage_aggregated(self) -> None:
        """Token usage from extraction and memory metadata is aggregated."""
        extraction_meta = [_make_usage_metadata(500, 200)]
        memory_meta = [_make_usage_metadata(300, 100)]
        result = _make_pipeline_result(
            extraction_usage_metadata=extraction_meta,
            memory_usage_metadata=memory_meta,
        )
        resp = PipelineResultResponse.from_pipeline_result(result)

        assert resp.token_usage.prompt_tokens == 800
        assert resp.token_usage.output_tokens == 300
        assert resp.token_usage.total_tokens == 1100

    def test_empty_result_converts_cleanly(self) -> None:
        """A minimal PipelineResult converts without errors."""
        result = _make_pipeline_result()
        resp = PipelineResultResponse.from_pipeline_result(result)

        assert resp.transcript_path == "/tmp/test.txt"
        assert resp.events_extracted == []
        assert resp.events_synced == []
        assert resp.events_failed == []
        assert resp.memory_actions == []
        assert resp.token_usage.prompt_tokens == 0

    def test_model_dump_produces_clean_json(self) -> None:
        """The response model serializes to a dict without errors."""
        event = _make_extracted_event()
        result = _make_pipeline_result(events_extracted=[event])
        resp = PipelineResultResponse.from_pipeline_result(result)

        data = resp.model_dump()
        assert isinstance(data, dict)
        assert data["transcript_path"] == "/tmp/test.txt"
        assert len(data["events_extracted"]) == 1

    def test_synced_event_with_matched_info(self) -> None:
        """Synced events preserve matched_event_title and matched_event_time."""
        event = _make_extracted_event(action="update", existing_event_id=1)
        sync = EventSyncResult(
            event=event,
            action_taken="updated",
            calendar_event_id="cal-456",
            success=True,
            matched_event_title="Old Team Meeting",
            matched_event_time="2026-03-04T10:00:00",
        )
        result = _make_pipeline_result(events_synced=[sync])
        resp = PipelineResultResponse.from_pipeline_result(result)

        assert resp.events_synced[0].matched_event_title == "Old Team Meeting"
        assert resp.events_synced[0].matched_event_time == "2026-03-04T10:00:00"

    def test_dry_run_flag_preserved(self) -> None:
        """The dry_run flag is preserved in the response."""
        result = _make_pipeline_result(dry_run=True)
        resp = PipelineResultResponse.from_pipeline_result(result)
        assert resp.dry_run is True

    def test_warnings_preserved(self) -> None:
        """Pipeline warnings are preserved in the response."""
        result = _make_pipeline_result(warnings=["Calendar context unavailable"])
        resp = PipelineResultResponse.from_pipeline_result(result)
        assert resp.warnings == ["Calendar context unavailable"]
