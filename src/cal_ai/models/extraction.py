"""Pydantic models for LLM event extraction.

Defines the structured data types used in the Gemini extraction pipeline:

- :class:`ExtractedEvent` -- a single calendar event as returned by the LLM
  (datetimes as ISO 8601 strings).
- :class:`ExtractionResult` -- wrapper for the full LLM response.
- :class:`ValidatedEvent` -- post-validation model with parsed ``datetime``
  objects and a default 1-hour duration applied when ``end_time`` is missing.
- :class:`LLMResponseSchema` -- schema for Gemini's ``response_schema``
  parameter, using proper ``Optional`` fields (SDK v1.63.0+).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# ExtractedEvent -- raw LLM output for a single event
# ---------------------------------------------------------------------------

_VALID_CONFIDENCES: set[str] = {"high", "medium", "low"}
_VALID_ACTIONS: set[str] = {"create", "update", "delete"}


class ExtractedEvent(BaseModel):
    """A single calendar event extracted by the LLM.

    All datetime values are ISO 8601 **strings** at this stage; they are
    parsed into real ``datetime`` objects in :class:`ValidatedEvent`.

    Attributes:
        title: Short event title.
        start_time: ISO 8601 datetime string for the event start.
        end_time: ISO 8601 datetime string for the event end, or ``None``
            if the LLM could not determine it.
        location: Event location, or ``None`` if unknown.
        attendees: List of attendee names.
        confidence: LLM's confidence in the extraction
            (``"high"``, ``"medium"``, or ``"low"``).
        reasoning: Free-text explanation of why this event was extracted.
        assumptions: Any assumptions the LLM made to fill gaps.
        action: Calendar action (``"create"``, ``"update"``, or ``"delete"``).
        existing_event_id: Remapped integer ID of an existing calendar event
            for update/delete actions, or ``None`` for create actions.
    """

    title: str
    start_time: str
    end_time: str | None = None
    location: str | None = None
    attendees: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    reasoning: str
    assumptions: list[str] = Field(default_factory=list)
    action: Literal["create", "update", "delete"] = "create"
    existing_event_id: int | None = None


# ---------------------------------------------------------------------------
# ExtractionResult -- full LLM response wrapper
# ---------------------------------------------------------------------------


class ExtractionResult(BaseModel):
    """Wrapper for the complete LLM extraction response.

    Attributes:
        events: List of extracted calendar events (may be empty).
        summary: Human-readable summary of the extraction outcome.
        usage_metadata: List of token-usage metadata objects from LLM
            API calls (one per attempt).  Populated by
            :meth:`~cal_ai.llm.GeminiClient.extract_events` after
            the API call.  Defaults to an empty list.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    events: list[ExtractedEvent] = Field(default_factory=list)
    summary: str
    usage_metadata: list[Any] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ValidatedEvent -- post-validation with parsed datetimes
# ---------------------------------------------------------------------------

_DEFAULT_DURATION = timedelta(hours=1)


class ValidatedEvent(BaseModel):
    """A calendar event with validated, parsed datetime objects.

    Created from an :class:`ExtractedEvent` after parsing ISO 8601 strings
    into ``datetime`` instances and applying a 1-hour default duration when
    ``end_time`` is missing.

    Attributes:
        title: Short event title.
        start_time: Parsed event start as a ``datetime``.
        end_time: Parsed event end as a ``datetime``. If the original
            :class:`ExtractedEvent` had no end_time, this defaults to
            ``start_time + 1 hour``.
        location: Event location, or ``None``.
        attendees: List of attendee names.
        confidence: LLM confidence level.
        reasoning: Free-text extraction reasoning.
        assumptions: Assumptions made during extraction.
        action: Calendar action.
        existing_event_id: Remapped integer ID of an existing calendar event,
            or ``None``.
    """

    title: str
    start_time: datetime
    end_time: datetime
    location: str | None = None
    attendees: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    reasoning: str
    assumptions: list[str] = Field(default_factory=list)
    action: Literal["create", "update", "delete"] = "create"
    existing_event_id: int | None = None

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def _parse_datetime_string(cls, value: datetime | str) -> datetime:
        """Accept ISO 8601 strings and convert them to ``datetime`` objects."""
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value

    @classmethod
    def from_extracted(cls, event: ExtractedEvent) -> ValidatedEvent:
        """Create a :class:`ValidatedEvent` from an :class:`ExtractedEvent`.

        Parses ISO 8601 datetime strings and applies a 1-hour default
        duration when ``end_time`` is ``None``.

        Args:
            event: The raw extracted event from the LLM.

        Returns:
            A validated event with proper ``datetime`` values.

        Raises:
            ValueError: If ``start_time`` cannot be parsed as ISO 8601.
        """
        start = datetime.fromisoformat(event.start_time)
        end = (
            datetime.fromisoformat(event.end_time)
            if event.end_time is not None
            else start + _DEFAULT_DURATION
        )
        return cls(
            title=event.title,
            start_time=start,
            end_time=end,
            location=event.location,
            attendees=event.attendees,
            confidence=event.confidence,
            reasoning=event.reasoning,
            assumptions=event.assumptions,
            action=event.action,
            existing_event_id=event.existing_event_id,
        )


# ---------------------------------------------------------------------------
# LLMResponseSchema -- schema for Gemini response_schema (SDK v1.63.0+)
# ---------------------------------------------------------------------------


class LLMResponseEvent(BaseModel):
    """Single-event schema for Gemini's ``response_schema`` parameter.

    Uses proper ``Optional`` fields (supported by SDK v1.63.0+) instead of
    ``"none"`` sentinel strings.  Comma-separated string fields
    (``attendees``, ``assumptions``) are still strings because Gemini's
    structured output handles them more reliably that way; they are split
    into lists during post-processing in :meth:`GeminiClient._convert_event`.

    Attributes:
        title: Event title.
        start_time: ISO 8601 datetime string.
        end_time: ISO 8601 datetime string, or ``None`` if unknown.
        location: Location string, or ``None`` if unknown.
        attendees: Comma-separated attendee names, or ``None`` if unknown.
        confidence: ``"high"``, ``"medium"``, or ``"low"``.
        reasoning: Extraction reasoning.
        assumptions: Comma-separated assumptions, or ``None`` if none.
        action: ``"create"``, ``"update"``, or ``"delete"``.
        existing_event_id: Remapped integer ID of an existing calendar
            event for update/delete, or ``None`` for create.
    """

    title: str
    start_time: str
    end_time: str | None = None
    location: str | None = None
    attendees: str | None = None
    confidence: str
    reasoning: str
    assumptions: str | None = None
    action: str
    existing_event_id: int | None = None


class LLMResponseSchema(BaseModel):
    """Top-level schema passed to Gemini's ``response_schema`` parameter.

    Uses proper ``Optional`` fields where appropriate (SDK v1.63.0+).

    Attributes:
        events: List of event objects.
        summary: Extraction summary.
    """

    events: list[LLMResponseEvent]
    summary: str
