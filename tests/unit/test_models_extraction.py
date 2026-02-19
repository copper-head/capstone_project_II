"""Tests for LLM event extraction Pydantic models.

Covers ExtractedEvent, ExtractionResult, ValidatedEvent, and the
``from_extracted`` factory method including default duration logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from cal_ai.models.extraction import ExtractedEvent, ExtractionResult, ValidatedEvent

# ---------------------------------------------------------------------------
# Helpers -- reusable keyword dicts for building test fixtures
# ---------------------------------------------------------------------------


def _complete_event_kwargs() -> dict:
    """Return kwargs for a fully-populated ExtractedEvent."""
    return {
        "title": "Lunch with Bob",
        "start_time": "2026-02-19T12:00:00",
        "end_time": "2026-02-19T13:00:00",
        "location": "Cafe Roma",
        "attendees": ["Alice", "Bob"],
        "confidence": "high",
        "reasoning": "Both speakers explicitly agreed to lunch.",
        "assumptions": ["Location confirmed by Bob"],
        "action": "create",
    }


def _minimal_event_kwargs() -> dict:
    """Return kwargs for an ExtractedEvent with only required fields."""
    return {
        "title": "Quick sync",
        "start_time": "2026-02-20T09:00:00",
        "confidence": "medium",
        "reasoning": "Mentioned a quick sync but no further details.",
    }


# ---------------------------------------------------------------------------
# ExtractedEvent tests
# ---------------------------------------------------------------------------


class TestExtractedEventValid:
    """Happy-path tests for ExtractedEvent instantiation."""

    def test_extracted_event_valid_complete(self) -> None:
        """All fields with valid values -- model instantiates and fields are accessible."""
        kwargs = _complete_event_kwargs()

        event = ExtractedEvent(**kwargs)

        assert event.title == "Lunch with Bob"
        assert event.start_time == "2026-02-19T12:00:00"
        assert event.end_time == "2026-02-19T13:00:00"
        assert event.location == "Cafe Roma"
        assert event.attendees == ["Alice", "Bob"]
        assert event.confidence == "high"
        assert event.reasoning == "Both speakers explicitly agreed to lunch."
        assert event.assumptions == ["Location confirmed by Bob"]
        assert event.action == "create"

    def test_extracted_event_valid_minimal(self) -> None:
        """Optional fields default correctly when omitted."""
        kwargs = _minimal_event_kwargs()

        event = ExtractedEvent(**kwargs)

        assert event.end_time is None
        assert event.location is None
        assert event.attendees == []
        assert event.assumptions == []
        assert event.action == "create"
        assert event.existing_event_id is None

    def test_extracted_event_with_existing_event_id(self) -> None:
        """existing_event_id is stored when provided."""
        kwargs = _complete_event_kwargs()
        kwargs["action"] = "update"
        kwargs["existing_event_id"] = 3

        event = ExtractedEvent(**kwargs)

        assert event.existing_event_id == 3
        assert event.action == "update"

    def test_extracted_event_existing_event_id_none_by_default(self) -> None:
        """existing_event_id defaults to None when not provided."""
        event = ExtractedEvent(**_complete_event_kwargs())

        assert event.existing_event_id is None


class TestExtractedEventInvalid:
    """Validation failure tests for ExtractedEvent."""

    def test_extracted_event_invalid_confidence(self) -> None:
        """Invalid confidence value raises ValidationError."""
        kwargs = _minimal_event_kwargs()
        kwargs["confidence"] = "maybe"

        with pytest.raises(ValidationError):
            ExtractedEvent(**kwargs)

    def test_extracted_event_missing_required_title(self) -> None:
        """Missing title field raises ValidationError."""
        kwargs = _minimal_event_kwargs()
        del kwargs["title"]

        with pytest.raises(ValidationError):
            ExtractedEvent(**kwargs)

    def test_extracted_event_missing_required_start_time(self) -> None:
        """Missing start_time field raises ValidationError."""
        kwargs = _minimal_event_kwargs()
        del kwargs["start_time"]

        with pytest.raises(ValidationError):
            ExtractedEvent(**kwargs)

    def test_extracted_event_missing_required_reasoning(self) -> None:
        """Missing reasoning field raises ValidationError."""
        kwargs = _minimal_event_kwargs()
        del kwargs["reasoning"]

        with pytest.raises(ValidationError):
            ExtractedEvent(**kwargs)


# ---------------------------------------------------------------------------
# ExtractionResult tests
# ---------------------------------------------------------------------------


class TestExtractionResult:
    """Tests for the ExtractionResult wrapper model."""

    def test_extraction_result_with_events(self) -> None:
        """List of valid ExtractedEvents is stored correctly."""
        event_a = ExtractedEvent(**_complete_event_kwargs())
        event_b = ExtractedEvent(**_minimal_event_kwargs())

        result = ExtractionResult(events=[event_a, event_b], summary="Found 2 events.")

        assert len(result.events) == 2
        assert result.events[0].title == "Lunch with Bob"
        assert result.events[1].title == "Quick sync"
        assert result.summary == "Found 2 events."

    def test_extraction_result_empty_events(self) -> None:
        """Empty events list with a summary is a valid model."""
        result = ExtractionResult(events=[], summary="No actionable events found.")

        assert result.events == []
        assert result.summary == "No actionable events found."


# ---------------------------------------------------------------------------
# ValidatedEvent tests
# ---------------------------------------------------------------------------


class TestValidatedEvent:
    """Tests for ValidatedEvent and its ``from_extracted`` factory."""

    def test_validated_event_default_end_time(self) -> None:
        """When end_time is None, from_extracted defaults to start + 1 hour."""
        extracted = ExtractedEvent(**_minimal_event_kwargs())

        validated = ValidatedEvent.from_extracted(extracted)

        expected_start = datetime(2026, 2, 20, 9, 0, 0)
        expected_end = expected_start + timedelta(hours=1)
        assert validated.start_time == expected_start
        assert validated.end_time == expected_end

    def test_validated_event_explicit_end_time(self) -> None:
        """When end_time is provided, from_extracted uses it as-is."""
        extracted = ExtractedEvent(**_complete_event_kwargs())

        validated = ValidatedEvent.from_extracted(extracted)

        assert validated.start_time == datetime(2026, 2, 19, 12, 0, 0)
        assert validated.end_time == datetime(2026, 2, 19, 13, 0, 0)

    def test_validated_event_iso_datetime_parsing(self) -> None:
        """ISO 8601 string is correctly parsed into a datetime object."""
        kwargs = _minimal_event_kwargs()
        kwargs["start_time"] = "2026-02-19T12:00:00"

        extracted = ExtractedEvent(**kwargs)
        validated = ValidatedEvent.from_extracted(extracted)

        assert validated.start_time == datetime(2026, 2, 19, 12, 0, 0)
        assert isinstance(validated.start_time, datetime)

    def test_validated_event_invalid_datetime_string(self) -> None:
        """Non-ISO-8601 start_time string raises ValueError in from_extracted."""
        kwargs = _minimal_event_kwargs()
        kwargs["start_time"] = "next Thursday"

        extracted = ExtractedEvent(**kwargs)

        with pytest.raises(ValueError):
            ValidatedEvent.from_extracted(extracted)

    def test_validated_event_preserves_existing_event_id(self) -> None:
        """from_extracted passes existing_event_id through to ValidatedEvent."""
        kwargs = _complete_event_kwargs()
        kwargs["action"] = "update"
        kwargs["existing_event_id"] = 7

        extracted = ExtractedEvent(**kwargs)
        validated = ValidatedEvent.from_extracted(extracted)

        assert validated.existing_event_id == 7
        assert validated.action == "update"

    def test_validated_event_existing_event_id_none_by_default(self) -> None:
        """from_extracted sets existing_event_id to None when not provided."""
        extracted = ExtractedEvent(**_minimal_event_kwargs())
        validated = ValidatedEvent.from_extracted(extracted)

        assert validated.existing_event_id is None
