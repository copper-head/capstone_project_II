"""Pydantic models for regression test sidecar JSON files.

Each ``.txt`` sample transcript is paired with a ``.expected.json`` sidecar
that defines the expected extraction outcome, tolerance level, optional
calendar context, and a mock LLM response for deterministic testing.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SidecarCalendarEvent(BaseModel):
    """A single event in the sidecar's ``calendar_context`` array.

    Represents an existing Google Calendar event that should be injected
    into the pipeline as context for CRUD-aware extraction.

    Attributes:
        id: Google Calendar event UUID (will be remapped to an integer).
        summary: Event title.
        start: ISO 8601 datetime string for event start.
        end: ISO 8601 datetime string for event end.
        location: Event location, or ``None``.
    """

    id: str
    summary: str
    start: str
    end: str
    location: str | None = None


class SidecarExpectedEvent(BaseModel):
    """Expected extraction result for a single event.

    Attributes:
        action: The expected calendar action.
        title: Expected event title (fuzzy-matched via ``rapidfuzz``).
        start_time: Expected ISO 8601 start time (tolerance-checked).
        end_time: Expected ISO 8601 end time (tolerance-checked), or ``None``.
        existing_event_id_required: If ``True``, the actual event must have
            a non-``None`` ``existing_event_id`` matching a calendar context
            entry.  Relevant for update/delete actions.
        location: Expected location string, or ``None`` to skip check.
        attendees_contain: List of attendee name substrings that must all
            appear in the actual attendees list (case-insensitive).
    """

    action: Literal["create", "update", "delete"]
    title: str
    start_time: str
    end_time: str | None = None
    existing_event_id_required: bool = False
    location: str | None = None
    attendees_contain: list[str] = Field(default_factory=list)


class SidecarMemoryEntry(BaseModel):
    """A single memory entry in the sidecar's ``memory_context`` array.

    Provides typed, schema-validated memory data for regression tests that
    exercise memory-aware extraction.  Objects satisfy the duck-typed
    contract required by :func:`~cal_ai.memory.formatter.format_memory_context`
    (``category``, ``key``, ``value`` attributes).

    Attributes:
        category: Memory category.
        key: Lookup identifier within the category.
        value: The memory content.
        confidence: Confidence level.  Defaults to ``"medium"``.
    """

    category: Literal["preferences", "people", "vocabulary", "patterns", "corrections"]
    key: str
    value: str
    confidence: Literal["low", "medium", "high"] = "medium"


class SidecarSpec(BaseModel):
    """Top-level sidecar JSON schema for a regression test sample.

    Attributes:
        description: Human-readable description of the test scenario.
        category: Sample category (mirrors directory structure).
        tolerance: Assertion tolerance level.  Defaults to ``"moderate"``.
        owner: Owner name injected into the pipeline.  Defaults to ``"Alice"``.
        reference_datetime: ISO 8601 datetime used as ``now`` in the
            pipeline.  Defaults to ``"2026-02-20T10:00:00"``.
        calendar_context: List of pre-existing calendar events to inject
            as context for CRUD-aware extraction.
        expected_events: List of expected extraction results.
        memory_context: Optional list of memory entries to inject into the
            pipeline via patched ``MemoryStore.load_all()``.  When ``None``
            (default), the pipeline uses its normal empty-DB behavior.
        mock_llm_response: Raw JSON dict the mocked LLM should return.
        expected_events_no_memory: Expected extraction results when memory
            is NOT injected (empty ``load_all``).  Used by the memory
            round-trip test runner for the no-memory pass.  ``None`` default.
        mock_llm_response_no_memory: Mock LLM response for the no-memory
            extraction pass.  ``None`` default.
        expected_memory_facts: Documentation-only list of memory facts that
            the A-transcript would produce.  NOT programmatically asserted
            (``dry_run=True`` skips Stage 4).  ``None`` default.
        notes: Optional notes about the test scenario.
    """

    description: str
    category: str
    tolerance: Literal["strict", "moderate", "relaxed"] = "moderate"
    owner: str = "Alice"
    reference_datetime: str = "2026-02-20T10:00:00"
    calendar_context: list[SidecarCalendarEvent] = Field(default_factory=list)
    expected_events: list[SidecarExpectedEvent] = Field(default_factory=list)
    memory_context: list[SidecarMemoryEntry] | None = None
    mock_llm_response: dict[str, Any] = Field(default_factory=dict)
    expected_events_no_memory: list[SidecarExpectedEvent] | None = None
    mock_llm_response_no_memory: dict[str, Any] | None = None
    expected_memory_facts: list[SidecarMemoryEntry] | None = None
    notes: str | None = None
