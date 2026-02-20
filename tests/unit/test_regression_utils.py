"""Unit tests for regression test infrastructure: schema, loader, and tolerance engine.

Tests cover:
- Sidecar schema validation
- Sample discovery and sidecar loading
- Tolerance assertion engine at all three levels (strict, moderate, relaxed)
- Best-match event pairing
- Attendee subset checks
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cal_ai.models.extraction import ExtractedEvent, ExtractionResult
from tests.regression.loader import build_calendar_context, discover_samples, load_sidecar
from tests.regression.schema import SidecarCalendarEvent, SidecarExpectedEvent, SidecarSpec
from tests.regression.tolerance import (
    _best_match_pairs,
    _time_distance,
    _title_distance,
    assert_extraction_result,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_extracted_event(**overrides) -> ExtractedEvent:
    """Create an ExtractedEvent with sensible defaults."""
    defaults = {
        "title": "Team Standup",
        "start_time": "2026-02-20T09:00:00",
        "end_time": "2026-02-20T09:30:00",
        "confidence": "high",
        "reasoning": "Daily standup mentioned in conversation.",
        "action": "create",
    }
    defaults.update(overrides)
    return ExtractedEvent(**defaults)


def _make_extraction_result(events: list[ExtractedEvent]) -> ExtractionResult:
    """Create an ExtractionResult wrapping the given events."""
    return ExtractionResult(events=events, summary="Test extraction result.")


def _make_sidecar(**overrides) -> SidecarSpec:
    """Create a SidecarSpec with sensible defaults."""
    defaults = {
        "description": "Test sidecar",
        "category": "crud",
        "tolerance": "moderate",
        "expected_events": [],
    }
    defaults.update(overrides)
    return SidecarSpec(**defaults)


def _make_expected_event(**overrides) -> SidecarExpectedEvent:
    """Create a SidecarExpectedEvent with sensible defaults."""
    defaults = {
        "action": "create",
        "title": "Team Standup",
        "start_time": "2026-02-20T09:00:00",
    }
    defaults.update(overrides)
    return SidecarExpectedEvent(**defaults)


# ===========================================================================
# Schema validation tests
# ===========================================================================


class TestSidecarSchema:
    """Tests for Pydantic sidecar schema validation."""

    def test_minimal_sidecar_validates(self):
        """A sidecar with only required fields should validate."""
        spec = SidecarSpec(
            description="Minimal test",
            category="crud",
        )
        assert spec.tolerance == "moderate"
        assert spec.owner == "Alice"
        assert spec.expected_events == []
        assert spec.calendar_context == []

    def test_full_sidecar_validates(self):
        """A sidecar with all fields should validate."""
        spec = SidecarSpec(
            description="Full test",
            category="multi_speaker",
            tolerance="strict",
            owner="Bob",
            reference_datetime="2026-03-01T14:00:00",
            calendar_context=[
                SidecarCalendarEvent(
                    id="abc123",
                    summary="Meeting",
                    start="2026-02-20T10:00:00",
                    end="2026-02-20T11:00:00",
                    location="Room A",
                ),
            ],
            expected_events=[
                SidecarExpectedEvent(
                    action="update",
                    title="Meeting",
                    start_time="2026-02-20T10:00:00",
                    existing_event_id_required=True,
                    attendees_contain=["Bob"],
                ),
            ],
            mock_llm_response={"events": [], "summary": "No events"},
            notes="This is a note.",
        )
        assert spec.tolerance == "strict"
        assert len(spec.calendar_context) == 1
        assert spec.calendar_context[0].location == "Room A"

    def test_invalid_tolerance_rejected(self):
        """An invalid tolerance value should raise ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SidecarSpec(
                description="Bad tolerance",
                category="crud",
                tolerance="ultra_strict",
            )


# ===========================================================================
# Loader tests
# ===========================================================================


class TestLoader:
    """Tests for sample discovery and sidecar loading."""

    def test_load_sidecar_valid(self, tmp_path: Path):
        """Loading a valid sidecar JSON should return a SidecarSpec."""
        sidecar_data = {
            "description": "Simple test",
            "category": "crud",
            "tolerance": "strict",
            "expected_events": [
                {
                    "action": "create",
                    "title": "Lunch",
                    "start_time": "2026-02-20T12:00:00",
                }
            ],
        }
        json_path = tmp_path / "sample.expected.json"
        json_path.write_text(json.dumps(sidecar_data))

        spec = load_sidecar(json_path)
        assert spec.description == "Simple test"
        assert spec.tolerance == "strict"
        assert len(spec.expected_events) == 1

    def test_discover_samples_pairs_files(self, tmp_path: Path):
        """discover_samples should pair .txt with .expected.json files."""
        # Create a sample with sidecar.
        (tmp_path / "hello.txt").write_text("Alice: Let's have lunch")
        sidecar_data = {
            "description": "Lunch",
            "category": "crud",
            "expected_events": [],
        }
        (tmp_path / "hello.expected.json").write_text(json.dumps(sidecar_data))

        # Create a sample without sidecar (should be skipped).
        (tmp_path / "orphan.txt").write_text("Bob: Nothing here")

        results = discover_samples(tmp_path)
        assert len(results) == 1
        assert results[0][0].name == "hello.txt"

    def test_discover_samples_recursive(self, tmp_path: Path):
        """discover_samples should find samples in subdirectories."""
        subdir = tmp_path / "crud"
        subdir.mkdir()
        (subdir / "test.txt").write_text("Alice: Meeting tomorrow")
        sidecar_data = {"description": "Meeting", "category": "crud", "expected_events": []}
        (subdir / "test.expected.json").write_text(json.dumps(sidecar_data))

        results = discover_samples(tmp_path)
        assert len(results) == 1
        assert "crud" in str(results[0][0])

    def test_build_calendar_context_empty(self):
        """An empty calendar_context should produce empty CalendarContext."""
        sidecar = _make_sidecar()
        ctx = build_calendar_context(sidecar)
        assert ctx.events_text == ""
        assert ctx.id_map == {}
        assert ctx.event_count == 0

    def test_build_calendar_context_with_events(self):
        """Calendar context should produce correct id_map and events_text."""
        sidecar = _make_sidecar(
            calendar_context=[
                SidecarCalendarEvent(
                    id="uuid-1",
                    summary="Meeting A",
                    start="2026-02-20T10:00:00",
                    end="2026-02-20T11:00:00",
                    location="Room 101",
                ),
                SidecarCalendarEvent(
                    id="uuid-2",
                    summary="Lunch",
                    start="2026-02-20T12:00:00",
                    end="2026-02-20T13:00:00",
                ),
            ]
        )
        ctx = build_calendar_context(sidecar)
        assert ctx.event_count == 2
        assert ctx.id_map[1] == "uuid-1"
        assert ctx.id_map[2] == "uuid-2"
        assert "[1] Meeting A" in ctx.events_text
        assert "[2] Lunch" in ctx.events_text
        assert "Room 101" in ctx.events_text
        assert ctx.event_meta[1]["title"] == "Meeting A"


# ===========================================================================
# Tolerance engine: distance and pairing tests
# ===========================================================================


class TestDistanceFunctions:
    """Tests for distance scoring used in best-match pairing."""

    def test_title_distance_identical(self):
        """Identical titles should yield distance 0."""
        assert _title_distance("Team Standup", "Team Standup") == 0.0

    def test_title_distance_similar(self):
        """Similar titles should yield small distance."""
        dist = _title_distance("Team Standup Meeting", "Team Standup")
        assert dist < 30.0  # Should be quite close

    def test_title_distance_different(self):
        """Totally different titles should yield large distance."""
        dist = _title_distance("Team Standup", "Birthday Party")
        assert dist > 50.0

    def test_time_distance_identical(self):
        """Identical times should yield distance 0."""
        assert _time_distance("2026-02-20T09:00:00", "2026-02-20T09:00:00") == 0.0

    def test_time_distance_one_hour(self):
        """One hour difference should yield ~60 minutes distance."""
        dist = _time_distance("2026-02-20T09:00:00", "2026-02-20T10:00:00")
        assert abs(dist - 60.0) < 0.1

    def test_time_distance_none_both(self):
        """Both None should yield distance 0."""
        assert _time_distance(None, None) == 0.0


class TestBestMatchPairing:
    """Tests for the best-match event pairing algorithm."""

    def test_single_pair(self):
        """A single actual and expected event should pair correctly."""
        actual = [_make_extracted_event()]
        expected = [_make_expected_event()]
        pairs = _best_match_pairs(actual, expected)
        assert len(pairs) == 1
        assert pairs[0][0].title == "Team Standup"
        assert pairs[0][1].title == "Team Standup"

    def test_reordered_events_pair_correctly(self):
        """Events in different order should still match by content."""
        actual = [
            _make_extracted_event(title="Lunch", start_time="2026-02-20T12:00:00"),
            _make_extracted_event(title="Standup", start_time="2026-02-20T09:00:00"),
        ]
        expected = [
            _make_expected_event(title="Standup", start_time="2026-02-20T09:00:00"),
            _make_expected_event(title="Lunch", start_time="2026-02-20T12:00:00"),
        ]
        pairs = _best_match_pairs(actual, expected)
        assert len(pairs) == 2
        # Each expected should match its actual regardless of order.
        titles_paired = {(p[0].title, p[1].title) for p in pairs}
        assert ("Standup", "Standup") in titles_paired
        assert ("Lunch", "Lunch") in titles_paired

    def test_more_expected_than_actual(self):
        """When more expected than actual, only available pairs are returned."""
        actual = [_make_extracted_event()]
        expected = [_make_expected_event(), _make_expected_event(title="Other")]
        pairs = _best_match_pairs(actual, expected)
        assert len(pairs) == 1


# ===========================================================================
# Tolerance assertion: STRICT (2 tests)
# ===========================================================================


class TestStrictTolerance:
    """Tests for strict tolerance level assertions."""

    def test_strict_exact_match_passes(self):
        """Exact match at strict level should pass."""
        event = _make_extracted_event()
        result = _make_extraction_result([event])
        sidecar = _make_sidecar(
            tolerance="strict",
            expected_events=[
                _make_expected_event(
                    end_time="2026-02-20T09:30:00",
                ),
            ],
        )
        # Should not raise.
        assert_extraction_result(result, sidecar)

    def test_strict_time_off_by_1h_fails(self):
        """Start time off by 1 hour should fail strict (30min tolerance)."""
        event = _make_extracted_event(start_time="2026-02-20T10:00:00")
        result = _make_extraction_result([event])
        sidecar = _make_sidecar(
            tolerance="strict",
            expected_events=[_make_expected_event()],
        )
        with pytest.raises(AssertionError, match="time difference"):
            assert_extraction_result(result, sidecar)


# ===========================================================================
# Tolerance assertion: MODERATE (2 tests)
# ===========================================================================


class TestModerateTolerance:
    """Tests for moderate tolerance level assertions."""

    def test_moderate_slight_time_drift_passes(self):
        """Start time off by 1 hour should pass moderate (2hr tolerance)."""
        event = _make_extracted_event(start_time="2026-02-20T10:00:00")
        result = _make_extraction_result([event])
        sidecar = _make_sidecar(
            tolerance="moderate",
            expected_events=[_make_expected_event()],
        )
        # Should not raise: 1 hour < 2 hour tolerance.
        assert_extraction_result(result, sidecar)

    def test_moderate_extra_event_within_tolerance_passes(self):
        """One extra event should pass moderate (+-1 tolerance)."""
        events = [
            _make_extracted_event(title="Team Standup"),
            _make_extracted_event(
                title="Extra Event",
                start_time="2026-02-20T14:00:00",
            ),
        ]
        result = _make_extraction_result(events)
        sidecar = _make_sidecar(
            tolerance="moderate",
            expected_events=[_make_expected_event()],
        )
        # Should not raise: 2 actual vs 1 expected = diff of 1, within +-1.
        assert_extraction_result(result, sidecar)


# ===========================================================================
# Tolerance assertion: RELAXED (2 tests)
# ===========================================================================


class TestRelaxedTolerance:
    """Tests for relaxed tolerance level assertions."""

    def test_relaxed_large_time_drift_passes(self):
        """Start time off by 12 hours should pass relaxed (1-day tolerance)."""
        event = _make_extracted_event(start_time="2026-02-20T21:00:00")
        result = _make_extraction_result([event])
        sidecar = _make_sidecar(
            tolerance="relaxed",
            expected_events=[_make_expected_event()],
        )
        # Should not raise: 12 hours < 1 day tolerance.
        assert_extraction_result(result, sidecar)

    def test_relaxed_fuzzy_title_passes(self):
        """Loosely similar title should pass relaxed (ratio >= 60)."""
        event = _make_extracted_event(title="Team Standup Call")
        result = _make_extraction_result([event])
        sidecar = _make_sidecar(
            tolerance="relaxed",
            expected_events=[_make_expected_event(title="Team Standup")],
        )
        # Should not raise: titles share key words.
        assert_extraction_result(result, sidecar)


# ===========================================================================
# Tolerance assertion: cross-cutting
# ===========================================================================


class TestToleranceCrossCutting:
    """Cross-cutting tolerance assertion tests."""

    def test_action_mismatch_always_fails(self):
        """Wrong action type should fail at any tolerance level."""
        event = _make_extracted_event(action="delete", existing_event_id=1)
        result = _make_extraction_result([event])
        sidecar = _make_sidecar(
            tolerance="relaxed",
            expected_events=[_make_expected_event(action="create")],
        )
        with pytest.raises(AssertionError, match="action mismatch"):
            assert_extraction_result(result, sidecar)

    def test_event_count_too_many_fails_strict(self):
        """Three extra events should fail strict (0 tolerance)."""
        events = [
            _make_extracted_event(title=f"Event {i}") for i in range(4)
        ]
        result = _make_extraction_result(events)
        sidecar = _make_sidecar(
            tolerance="strict",
            expected_events=[_make_expected_event()],
        )
        with pytest.raises(AssertionError, match="Event count mismatch"):
            assert_extraction_result(result, sidecar)

    def test_attendees_subset_check(self):
        """Attendees that are required must appear in actual."""
        event = _make_extracted_event(attendees=["Alice", "Bob", "Charlie"])
        result = _make_extraction_result([event])
        sidecar = _make_sidecar(
            tolerance="moderate",
            expected_events=[
                _make_expected_event(attendees_contain=["alice", "bob"]),
            ],
        )
        # Should pass: case-insensitive match.
        assert_extraction_result(result, sidecar)

    def test_attendees_missing_fails(self):
        """Missing required attendee should fail."""
        event = _make_extracted_event(attendees=["Alice"])
        result = _make_extraction_result([event])
        sidecar = _make_sidecar(
            tolerance="moderate",
            expected_events=[
                _make_expected_event(attendees_contain=["Dave"]),
            ],
        )
        with pytest.raises(AssertionError, match="Dave"):
            assert_extraction_result(result, sidecar)

    def test_existing_event_id_required(self):
        """When existing_event_id_required=True, None should fail."""
        event = _make_extracted_event(
            action="update",
            existing_event_id=None,
        )
        result = _make_extraction_result([event])
        sidecar = _make_sidecar(
            tolerance="moderate",
            expected_events=[
                _make_expected_event(
                    action="update",
                    existing_event_id_required=True,
                ),
            ],
        )
        with pytest.raises(AssertionError, match="existing_event_id is required"):
            assert_extraction_result(result, sidecar)

    def test_empty_expected_empty_actual_passes(self):
        """No expected and no actual events should pass at any level."""
        result = _make_extraction_result([])
        sidecar = _make_sidecar(tolerance="strict", expected_events=[])
        assert_extraction_result(result, sidecar)

    def test_existing_event_id_out_of_range_fails(self):
        """An existing_event_id outside the context domain should fail."""
        event = _make_extracted_event(
            action="update",
            existing_event_id=99,  # Out of range.
        )
        result = _make_extraction_result([event])
        sidecar = _make_sidecar(
            tolerance="moderate",
            calendar_context=[
                SidecarCalendarEvent(
                    id="uuid-1",
                    summary="Meeting",
                    start="2026-02-20T10:00:00",
                    end="2026-02-20T11:00:00",
                ),
            ],
            expected_events=[
                _make_expected_event(
                    action="update",
                    existing_event_id_required=True,
                ),
            ],
        )
        with pytest.raises(AssertionError, match="not in valid context IDs"):
            assert_extraction_result(result, sidecar)

    def test_delete_time_resolved_from_calendar_context(self):
        """Delete actions should compare against calendar context event times."""
        # The calendar context event is at 10:00-11:00.
        # The actual delete event references it and also reports 10:00-11:00.
        # The sidecar expected event has different times (09:00) but since
        # the delete resolves from context, it should still pass.
        event = _make_extracted_event(
            action="delete",
            title="Meeting",
            start_time="2026-02-20T10:00:00",
            end_time="2026-02-20T11:00:00",
            existing_event_id=1,
        )
        result = _make_extraction_result([event])
        sidecar = _make_sidecar(
            tolerance="strict",
            calendar_context=[
                SidecarCalendarEvent(
                    id="uuid-1",
                    summary="Meeting",
                    start="2026-02-20T10:00:00",
                    end="2026-02-20T11:00:00",
                ),
            ],
            expected_events=[
                _make_expected_event(
                    action="delete",
                    title="Meeting",
                    # The expected times here differ from context, but
                    # for delete actions the context times should be used.
                    start_time="2026-02-20T09:00:00",
                    existing_event_id_required=True,
                ),
            ],
        )
        # Should pass: delete resolves times from context (10:00),
        # and actual is also 10:00, so it is within strict tolerance.
        assert_extraction_result(result, sidecar)

    def test_delete_without_context_uses_expected_times(self):
        """Delete actions without calendar context should use expected times."""
        event = _make_extracted_event(
            action="delete",
            title="Meeting",
            start_time="2026-02-20T09:00:00",
            existing_event_id=None,
        )
        result = _make_extraction_result([event])
        sidecar = _make_sidecar(
            tolerance="moderate",
            # No calendar_context.
            expected_events=[
                _make_expected_event(
                    action="delete",
                    title="Meeting",
                    start_time="2026-02-20T09:00:00",
                ),
            ],
        )
        # Should pass: no context, so expected times are used directly.
        assert_extraction_result(result, sidecar)
