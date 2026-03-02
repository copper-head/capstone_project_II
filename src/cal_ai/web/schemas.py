"""Pydantic response models for the cal-ai web API.

Serializes the pipeline's stdlib dataclasses and nested Pydantic models
into clean JSON for the frontend.  The top-level converter
:meth:`PipelineResultResponse.from_pipeline_result` handles all
necessary transformations (``Path`` to ``str``, token aggregation, etc.).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Event-level response models
# ---------------------------------------------------------------------------


class EventResponse(BaseModel):
    """A single extracted calendar event for the API response.

    Mirrors :class:`~cal_ai.models.extraction.ExtractedEvent` fields.
    """

    title: str
    start_time: str
    end_time: str | None = None
    location: str | None = None
    attendees: list[str] = Field(default_factory=list)
    confidence: str
    reasoning: str
    assumptions: list[str] = Field(default_factory=list)
    action: str = "create"
    existing_event_id: int | None = None


class SyncResultResponse(BaseModel):
    """Result of syncing a single event to Google Calendar.

    Mirrors :class:`~cal_ai.pipeline.EventSyncResult`.
    """

    event: EventResponse
    action_taken: str
    calendar_event_id: str | None = None
    success: bool = True
    error: str | None = None
    matched_event_title: str | None = None
    matched_event_time: str | None = None


class FailedEventResponse(BaseModel):
    """An event that failed to sync.

    Mirrors :class:`~cal_ai.pipeline.FailedEvent`.
    """

    event: EventResponse
    error: str


# ---------------------------------------------------------------------------
# Memory action response model
# ---------------------------------------------------------------------------


class MemoryActionResponse(BaseModel):
    """A single memory action from the write path.

    Mirrors :class:`~cal_ai.memory.models.MemoryAction` fields, excluding
    ``target_memory_id`` (internal remapped ID, not useful for display).
    """

    action: str
    category: str
    key: str
    new_value: str | None = None
    confidence: str = "medium"
    reasoning: str


# ---------------------------------------------------------------------------
# Token usage response model
# ---------------------------------------------------------------------------

# Gemini 2.5 pricing (per million tokens).
_INPUT_COST_PER_M = 1.25
_OUTPUT_COST_PER_M = 10.00


class TokenUsageResponse(BaseModel):
    """Aggregated token usage from all LLM calls.

    Built from ``extraction_usage_metadata`` and ``memory_usage_metadata``
    on :class:`~cal_ai.pipeline.PipelineResult`.
    """

    prompt_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None

    @classmethod
    def from_usage_metadata(
        cls,
        extraction_metadata: list[Any],
        memory_metadata: list[Any],
    ) -> TokenUsageResponse:
        """Aggregate token counts from Gemini SDK usage metadata objects.

        Each metadata object is expected to have ``prompt_token_count``
        and ``candidates_token_count`` attributes.  Missing or ``None``
        values are treated as zero.

        Args:
            extraction_metadata: Usage metadata from extraction LLM calls.
            memory_metadata: Usage metadata from memory LLM calls.

        Returns:
            Aggregated :class:`TokenUsageResponse`.
        """
        prompt_total = 0
        output_total = 0

        for meta in [*extraction_metadata, *memory_metadata]:
            if meta is None:
                continue
            prompt_total += getattr(meta, "prompt_token_count", 0) or 0
            output_total += getattr(meta, "candidates_token_count", 0) or 0

        total = prompt_total + output_total

        cost: float | None = None
        if total > 0:
            cost = (prompt_total / 1_000_000 * _INPUT_COST_PER_M) + (
                output_total / 1_000_000 * _OUTPUT_COST_PER_M
            )

        return cls(
            prompt_tokens=prompt_total,
            output_tokens=output_total,
            total_tokens=total,
            estimated_cost_usd=cost,
        )


# ---------------------------------------------------------------------------
# Memory viewer response model
# ---------------------------------------------------------------------------


class MemoryResponse(BaseModel):
    """A single memory entry for the ``GET /api/memories`` endpoint.

    Includes only the fields relevant for display (no timestamps or
    source_count, per interview decision).
    """

    category: str
    key: str
    value: str
    confidence: str = "medium"


# ---------------------------------------------------------------------------
# Top-level pipeline result response
# ---------------------------------------------------------------------------


class PipelineResultResponse(BaseModel):
    """Full pipeline result serialized for the API.

    Mirrors :class:`~cal_ai.pipeline.PipelineResult` with all nested
    models converted to Pydantic response types.
    """

    transcript_path: str
    speakers_found: list[str] = Field(default_factory=list)
    utterance_count: int = 0
    events_extracted: list[EventResponse] = Field(default_factory=list)
    events_synced: list[SyncResultResponse] = Field(default_factory=list)
    events_failed: list[FailedEventResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    dry_run: bool = False
    memories_added: int = 0
    memories_updated: int = 0
    memories_deleted: int = 0
    memory_actions: list[MemoryActionResponse] = Field(default_factory=list)
    token_usage: TokenUsageResponse = Field(default_factory=TokenUsageResponse)

    @classmethod
    def from_pipeline_result(cls, result: Any) -> PipelineResultResponse:
        """Convert a :class:`~cal_ai.pipeline.PipelineResult` to a response model.

        Handles:
        - ``Path`` to ``str`` for ``transcript_path``.
        - Nested ``ExtractedEvent`` (Pydantic) to ``EventResponse``.
        - ``EventSyncResult`` / ``FailedEvent`` (dataclasses) to response models.
        - ``MemoryAction`` to ``MemoryActionResponse`` (excludes ``target_memory_id``).
        - Token aggregation from ``extraction_usage_metadata`` + ``memory_usage_metadata``.

        Args:
            result: A :class:`~cal_ai.pipeline.PipelineResult` instance.

        Returns:
            A :class:`PipelineResultResponse` ready for JSON serialization.
        """
        # Convert ExtractedEvent (Pydantic) -> EventResponse
        events = [
            EventResponse(
                title=e.title,
                start_time=e.start_time,
                end_time=e.end_time,
                location=e.location,
                attendees=e.attendees,
                confidence=e.confidence,
                reasoning=e.reasoning,
                assumptions=e.assumptions,
                action=e.action,
                existing_event_id=e.existing_event_id,
            )
            for e in result.events_extracted
        ]

        # Convert EventSyncResult (dataclass) -> SyncResultResponse
        synced = [
            SyncResultResponse(
                event=EventResponse(
                    title=s.event.title,
                    start_time=s.event.start_time,
                    end_time=s.event.end_time,
                    location=s.event.location,
                    attendees=s.event.attendees,
                    confidence=s.event.confidence,
                    reasoning=s.event.reasoning,
                    assumptions=s.event.assumptions,
                    action=s.event.action,
                    existing_event_id=s.event.existing_event_id,
                ),
                action_taken=s.action_taken,
                calendar_event_id=s.calendar_event_id,
                success=s.success,
                error=s.error,
                matched_event_title=s.matched_event_title,
                matched_event_time=s.matched_event_time,
            )
            for s in result.events_synced
        ]

        # Convert FailedEvent (dataclass) -> FailedEventResponse
        failed = [
            FailedEventResponse(
                event=EventResponse(
                    title=f.event.title,
                    start_time=f.event.start_time,
                    end_time=f.event.end_time,
                    location=f.event.location,
                    attendees=f.event.attendees,
                    confidence=f.event.confidence,
                    reasoning=f.event.reasoning,
                    assumptions=f.event.assumptions,
                    action=f.event.action,
                    existing_event_id=f.event.existing_event_id,
                ),
                error=f.error,
            )
            for f in result.events_failed
        ]

        # Convert MemoryAction -> MemoryActionResponse (exclude target_memory_id)
        memory_actions = [
            MemoryActionResponse(
                action=a.action,
                category=a.category,
                key=a.key,
                new_value=a.new_value,
                confidence=a.confidence,
                reasoning=a.reasoning,
            )
            for a in result.memory_actions
        ]

        # Aggregate token usage
        token_usage = TokenUsageResponse.from_usage_metadata(
            extraction_metadata=result.extraction_usage_metadata,
            memory_metadata=result.memory_usage_metadata,
        )

        return cls(
            transcript_path=str(result.transcript_path),
            speakers_found=result.speakers_found,
            utterance_count=result.utterance_count,
            events_extracted=events,
            events_synced=synced,
            events_failed=failed,
            warnings=result.warnings,
            duration_seconds=result.duration_seconds,
            dry_run=result.dry_run,
            memories_added=result.memories_added,
            memories_updated=result.memories_updated,
            memories_deleted=result.memories_deleted,
            memory_actions=memory_actions,
            token_usage=token_usage,
        )
