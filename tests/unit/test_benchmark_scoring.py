"""Unit tests for the benchmark scoring engine.

Covers: all-correct, all-wrong, partial match, empty expected, empty actual,
mixed actions, P/R/F1 edge cases, aggregation, and confidence calibration.
"""

from __future__ import annotations

import pytest

from cal_ai.benchmark.scoring import (
    SampleScore,
    _compute_prf,
    aggregate_scores,
    calibrate_confidence,
    score_sample,
)
from cal_ai.models.extraction import ExtractedEvent
from tests.regression.schema import SidecarExpectedEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_actual(
    title: str = "Lunch",
    action: str = "create",
    start: str = "2026-02-20T12:00:00",
    end: str | None = "2026-02-20T13:00:00",
    confidence: str = "high",
    existing_event_id: int | None = None,
) -> ExtractedEvent:
    """Create a minimal ExtractedEvent for testing."""
    return ExtractedEvent(
        title=title,
        start_time=start,
        end_time=end,
        confidence=confidence,
        reasoning="test",
        action=action,
        existing_event_id=existing_event_id,
    )


def _make_expected(
    title: str = "Lunch",
    action: str = "create",
    start: str = "2026-02-20T12:00:00",
    end: str | None = "2026-02-20T13:00:00",
) -> SidecarExpectedEvent:
    """Create a minimal SidecarExpectedEvent for testing."""
    return SidecarExpectedEvent(
        title=title,
        action=action,
        start_time=start,
        end_time=end,
    )


# ===========================================================================
# _compute_prf tests
# ===========================================================================


class TestComputePRF:
    """Test the raw P/R/F1 computation helper."""

    def test_vacuous_truth(self) -> None:
        """Both empty: P=1.0, R=1.0, F1=1.0."""
        p, r, f1 = _compute_prf(0, 0, 0)
        assert p == 1.0
        assert r == 1.0
        assert f1 == 1.0

    def test_perfect_score(self) -> None:
        """All correct, no FP or FN."""
        p, r, f1 = _compute_prf(5, 0, 0)
        assert p == 1.0
        assert r == 1.0
        assert f1 == 1.0

    def test_actual_empty_expected_nonempty(self) -> None:
        """No predictions: P=1.0 (no false positives), R=0.0."""
        p, r, f1 = _compute_prf(0, 0, 3)
        assert p == 1.0
        assert r == 0.0
        assert f1 == 0.0

    def test_expected_empty_actual_nonempty(self) -> None:
        """All FP: P=0.0, R=1.0 (nothing to miss)."""
        p, r, f1 = _compute_prf(0, 3, 0)
        assert p == 0.0
        assert r == 1.0
        assert f1 == 0.0

    def test_partial_match(self) -> None:
        """2 TP, 1 FP, 1 FN."""
        p, r, f1 = _compute_prf(2, 1, 1)
        assert p == pytest.approx(2 / 3)
        assert r == pytest.approx(2 / 3)
        expected_f1 = 2 * (2 / 3) * (2 / 3) / (2 / 3 + 2 / 3)
        assert f1 == pytest.approx(expected_f1)

    def test_all_wrong(self) -> None:
        """0 TP, 2 FP, 3 FN."""
        p, r, f1 = _compute_prf(0, 2, 3)
        assert p == 0.0
        assert r == 0.0
        assert f1 == 0.0


# ===========================================================================
# score_sample tests
# ===========================================================================


class TestScoreSample:
    """Test score_sample() with various scenarios."""

    def test_both_empty(self) -> None:
        """Empty actual and expected => vacuous truth."""
        result = score_sample([], [], "strict", sample_name="empty")
        assert result.tp == 0
        assert result.fp == 0
        assert result.fn == 0
        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1 == 1.0
        assert result.per_event_details == []

    def test_actual_empty_expected_nonempty(self) -> None:
        """No predictions made, 2 expected events."""
        expected = [
            _make_expected("Lunch"),
            _make_expected("Dinner", start="2026-02-20T18:00:00"),
        ]
        result = score_sample([], expected, "moderate", sample_name="no_pred")
        assert result.tp == 0
        assert result.fp == 0
        assert result.fn == 2
        assert result.precision == 1.0
        assert result.recall == 0.0
        assert result.f1 == 0.0

    def test_expected_empty_actual_nonempty(self) -> None:
        """Predictions but nothing expected."""
        actual = [
            _make_actual("Lunch"),
            _make_actual("Dinner", start="2026-02-20T18:00:00"),
        ]
        result = score_sample(actual, [], "moderate", sample_name="fp_only")
        assert result.tp == 0
        assert result.fp == 2
        assert result.fn == 0
        assert result.precision == 0.0
        assert result.recall == 1.0
        assert result.f1 == 0.0

    def test_all_correct_single_event(self) -> None:
        """One event, exact match => TP=1."""
        actual = [_make_actual("Lunch")]
        expected = [_make_expected("Lunch")]
        result = score_sample(actual, expected, "strict", sample_name="crud/simple_lunch")
        assert result.tp == 1
        assert result.fp == 0
        assert result.fn == 0
        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1 == 1.0
        assert result.sample_name == "crud/simple_lunch"
        assert result.category == "uncategorized"

    def test_all_correct_multiple_events(self) -> None:
        """Multiple events, all matching."""
        actual = [
            _make_actual("Lunch"),
            _make_actual("Dinner", start="2026-02-20T18:00:00", end="2026-02-20T19:00:00"),
        ]
        expected = [
            _make_expected("Lunch"),
            _make_expected("Dinner", start="2026-02-20T18:00:00", end="2026-02-20T19:00:00"),
        ]
        result = score_sample(actual, expected, "moderate")
        assert result.tp == 2
        assert result.fp == 0
        assert result.fn == 0
        assert result.f1 == 1.0

    def test_all_wrong_action_mismatch(self) -> None:
        """Action mismatch causes paired event to count as FP+FN."""
        actual = [_make_actual("Lunch", action="delete")]
        expected = [_make_expected("Lunch", action="create")]
        result = score_sample(actual, expected, "moderate")
        assert result.tp == 0
        assert result.fp == 1
        assert result.fn == 1
        assert result.precision == 0.0
        assert result.recall == 0.0
        assert result.f1 == 0.0

    def test_title_mismatch_strict(self) -> None:
        """Strict mode requires exact title match (case-insensitive)."""
        actual = [_make_actual("Business Lunch Meeting")]
        expected = [_make_expected("Lunch")]
        result = score_sample(actual, expected, "strict")
        # Titles don't match exactly.
        assert result.tp == 0
        assert result.fp == 1
        assert result.fn == 1

    def test_title_fuzzy_match_moderate(self) -> None:
        """Moderate mode uses fuzzy title matching."""
        actual = [_make_actual("Lunch Meeting")]
        expected = [_make_expected("Lunch Meeting")]
        result = score_sample(actual, expected, "moderate")
        assert result.tp == 1
        assert result.fp == 0
        assert result.fn == 0

    def test_time_within_tolerance(self) -> None:
        """Start time within moderate tolerance (2 hours)."""
        actual = [_make_actual("Lunch", start="2026-02-20T12:30:00")]
        expected = [_make_expected("Lunch", start="2026-02-20T12:00:00")]
        result = score_sample(actual, expected, "moderate")
        assert result.tp == 1

    def test_time_outside_tolerance(self) -> None:
        """Start time outside strict tolerance (30 min)."""
        actual = [_make_actual("Lunch", start="2026-02-20T14:00:00")]
        expected = [_make_expected("Lunch", start="2026-02-20T12:00:00")]
        result = score_sample(actual, expected, "strict")
        assert result.tp == 0
        assert result.fp == 1
        assert result.fn == 1

    def test_partial_match(self) -> None:
        """2 of 3 events match, 1 extra actual, 1 missed expected."""
        actual = [
            _make_actual("Lunch"),
            _make_actual("Dinner", start="2026-02-20T18:00:00", end="2026-02-20T19:00:00"),
            _make_actual("Phantom Event", start="2026-02-20T20:00:00"),
        ]
        expected = [
            _make_expected("Lunch"),
            _make_expected("Dinner", start="2026-02-20T18:00:00", end="2026-02-20T19:00:00"),
            _make_expected("Meeting", start="2026-02-20T09:00:00", end="2026-02-20T10:00:00"),
        ]
        result = score_sample(actual, expected, "moderate")
        # Lunch matches, Dinner matches, Phantom paired with Meeting
        # but likely mismatches => FP+FN.
        assert result.tp == 2
        assert result.fp >= 1
        assert result.fn >= 1

    def test_mixed_actions(self) -> None:
        """Create, update, and delete actions all scored correctly."""
        actual = [
            _make_actual("New Event", action="create"),
            _make_actual(
                "Updated Event",
                action="update",
                start="2026-02-21T10:00:00",
                end="2026-02-21T11:00:00",
            ),
            _make_actual(
                "Cancelled Event",
                action="delete",
                start="2026-02-22T09:00:00",
                end="2026-02-22T10:00:00",
            ),
        ]
        expected = [
            _make_expected("New Event", action="create"),
            _make_expected(
                "Updated Event",
                action="update",
                start="2026-02-21T10:00:00",
                end="2026-02-21T11:00:00",
            ),
            _make_expected(
                "Cancelled Event",
                action="delete",
                start="2026-02-22T09:00:00",
                end="2026-02-22T10:00:00",
            ),
        ]
        result = score_sample(actual, expected, "strict")
        assert result.tp == 3
        assert result.fp == 0
        assert result.fn == 0
        assert result.f1 == 1.0

    def test_per_event_details_populated(self) -> None:
        """Verify per-event details are populated correctly."""
        actual = [_make_actual("Lunch")]
        expected = [_make_expected("Lunch")]
        result = score_sample(actual, expected, "moderate")
        assert len(result.per_event_details) == 1
        detail = result.per_event_details[0]
        assert detail.classification == "tp"
        assert detail.actual_event is not None
        assert detail.expected_event is not None
        assert detail.mismatch_reasons == []

    def test_mismatch_details_have_reasons(self) -> None:
        """FP details include mismatch reasons."""
        actual = [_make_actual("Lunch", action="delete")]
        expected = [_make_expected("Lunch", action="create")]
        result = score_sample(actual, expected, "moderate")
        fp_details = [d for d in result.per_event_details if d.classification == "fp"]
        assert len(fp_details) == 1
        assert len(fp_details[0].mismatch_reasons) > 0
        assert "action" in fp_details[0].mismatch_reasons[0]

    def test_category_passed_through(self) -> None:
        """Category is stored in the SampleScore."""
        result = score_sample([], [], "moderate", sample_name="test", category="crud")
        assert result.category == "crud"

    def test_relaxed_tolerance_allows_wider_time(self) -> None:
        """Relaxed tolerance: 1 day window."""
        actual = [_make_actual("Event", start="2026-02-21T12:00:00")]
        expected = [_make_expected("Event", start="2026-02-20T18:00:00")]
        result = score_sample(actual, expected, "relaxed")
        # 18 hours diff, within 1 day tolerance.
        assert result.tp == 1


# ===========================================================================
# aggregate_scores tests
# ===========================================================================


class TestAggregateScores:
    """Test aggregate_scores() overall and per-category metrics."""

    def test_empty_list(self) -> None:
        """No samples => vacuous truth aggregate."""
        result = aggregate_scores([])
        assert result.overall_tp == 0
        assert result.overall_precision == 1.0
        assert result.overall_recall == 1.0
        assert result.overall_f1 == 1.0
        assert result.sample_count == 0

    def test_single_sample(self) -> None:
        """One sample's metrics pass through to aggregate."""
        sample = SampleScore(
            sample_name="test",
            category="crud",
            tolerance="moderate",
            tp=3,
            fp=1,
            fn=0,
            precision=3 / 4,
            recall=1.0,
            f1=6 / 7,
        )
        result = aggregate_scores([sample])
        assert result.overall_tp == 3
        assert result.overall_fp == 1
        assert result.overall_fn == 0
        assert result.overall_precision == pytest.approx(3 / 4)
        assert result.overall_recall == 1.0
        assert result.sample_count == 1
        assert len(result.per_category) == 1
        assert result.per_category[0].category == "crud"

    def test_multiple_categories(self) -> None:
        """Multiple categories are tracked separately."""
        samples = [
            SampleScore(
                sample_name="s1",
                category="crud",
                tolerance="moderate",
                tp=2,
                fp=0,
                fn=0,
                precision=1.0,
                recall=1.0,
                f1=1.0,
            ),
            SampleScore(
                sample_name="s2",
                category="crud",
                tolerance="moderate",
                tp=1,
                fp=1,
                fn=0,
                precision=0.5,
                recall=1.0,
                f1=2 / 3,
            ),
            SampleScore(
                sample_name="s3",
                category="adversarial",
                tolerance="relaxed",
                tp=0,
                fp=0,
                fn=2,
                precision=1.0,
                recall=0.0,
                f1=0.0,
            ),
        ]
        result = aggregate_scores(samples)
        assert result.overall_tp == 3
        assert result.overall_fp == 1
        assert result.overall_fn == 2
        assert result.sample_count == 3
        assert len(result.per_category) == 2

        # Categories are sorted alphabetically.
        assert result.per_category[0].category == "adversarial"
        assert result.per_category[0].tp == 0
        assert result.per_category[0].fn == 2
        assert result.per_category[0].sample_count == 1

        assert result.per_category[1].category == "crud"
        assert result.per_category[1].tp == 3
        assert result.per_category[1].fp == 1
        assert result.per_category[1].sample_count == 2

    def test_micro_averaging(self) -> None:
        """Aggregate uses micro-averaging (sum TP/FP/FN then compute)."""
        samples = [
            SampleScore(
                sample_name="s1",
                category="a",
                tolerance="strict",
                tp=1,
                fp=0,
                fn=1,
                precision=1.0,
                recall=0.5,
                f1=2 / 3,
            ),
            SampleScore(
                sample_name="s2",
                category="a",
                tolerance="strict",
                tp=3,
                fp=1,
                fn=0,
                precision=0.75,
                recall=1.0,
                f1=6 / 7,
            ),
        ]
        result = aggregate_scores(samples)
        # Micro: tp=4, fp=1, fn=1
        assert result.overall_tp == 4
        assert result.overall_fp == 1
        assert result.overall_fn == 1
        assert result.overall_precision == pytest.approx(4 / 5)
        assert result.overall_recall == pytest.approx(4 / 5)


# ===========================================================================
# calibrate_confidence tests
# ===========================================================================


class TestCalibrateConfidence:
    """Test calibrate_confidence() confidence-to-accuracy mapping."""

    def test_empty_scores(self) -> None:
        """No samples => empty dict."""
        assert calibrate_confidence([]) == {}

    def test_all_high_correct(self) -> None:
        """All high-confidence events are TPs."""
        actual = [_make_actual("Lunch", confidence="high")]
        expected = [_make_expected("Lunch")]
        sample = score_sample(actual, expected, "moderate", sample_name="t")
        result = calibrate_confidence([sample])
        assert result == {"high": 1.0}

    def test_mixed_confidence(self) -> None:
        """Mix of high/medium confidence with different accuracies."""
        from cal_ai.benchmark.scoring import EventMatchDetail

        # Build SampleScores with explicit per_event_details.
        details = [
            EventMatchDetail(
                classification="tp",
                actual_event=_make_actual("E1", confidence="high"),
                expected_event=_make_expected("E1"),
            ),
            EventMatchDetail(
                classification="tp",
                actual_event=_make_actual("E2", confidence="high"),
                expected_event=_make_expected("E2"),
            ),
            EventMatchDetail(
                classification="fp",
                actual_event=_make_actual("E3", confidence="high"),
                mismatch_reasons=["action mismatch"],
            ),
            EventMatchDetail(
                classification="tp",
                actual_event=_make_actual("E4", confidence="medium"),
                expected_event=_make_expected("E4"),
            ),
            EventMatchDetail(
                classification="fp",
                actual_event=_make_actual("E5", confidence="medium"),
                mismatch_reasons=["title mismatch"],
            ),
            EventMatchDetail(
                classification="fn",
                expected_event=_make_expected("E6"),
            ),
        ]
        sample = SampleScore(
            sample_name="test",
            category="mixed",
            tolerance="moderate",
            tp=3,
            fp=2,
            fn=1,
            precision=0.6,
            recall=0.75,
            f1=0.667,
            per_event_details=details,
        )
        result = calibrate_confidence([sample])
        # high: 2 TP out of 3 actual = 2/3
        assert result["high"] == pytest.approx(2 / 3)
        # medium: 1 TP out of 2 actual = 1/2
        assert result["medium"] == pytest.approx(1 / 2)
        # low: not present
        assert "low" not in result

    def test_low_confidence_tracked(self) -> None:
        """Low confidence events are tracked when present."""
        from cal_ai.benchmark.scoring import EventMatchDetail

        details = [
            EventMatchDetail(
                classification="fp",
                actual_event=_make_actual("E1", confidence="low"),
                mismatch_reasons=["wrong"],
            ),
        ]
        sample = SampleScore(
            sample_name="t",
            category="a",
            tolerance="moderate",
            tp=0,
            fp=1,
            fn=0,
            precision=0.0,
            recall=1.0,
            f1=0.0,
            per_event_details=details,
        )
        result = calibrate_confidence([sample])
        assert result["low"] == 0.0

    def test_multiple_samples(self) -> None:
        """Calibration aggregates across multiple samples."""
        from cal_ai.benchmark.scoring import EventMatchDetail

        sample1 = SampleScore(
            sample_name="s1",
            category="a",
            tolerance="moderate",
            tp=1,
            fp=0,
            fn=0,
            precision=1.0,
            recall=1.0,
            f1=1.0,
            per_event_details=[
                EventMatchDetail(
                    classification="tp",
                    actual_event=_make_actual("E1", confidence="high"),
                    expected_event=_make_expected("E1"),
                ),
            ],
        )
        sample2 = SampleScore(
            sample_name="s2",
            category="b",
            tolerance="moderate",
            tp=0,
            fp=1,
            fn=0,
            precision=0.0,
            recall=1.0,
            f1=0.0,
            per_event_details=[
                EventMatchDetail(
                    classification="fp",
                    actual_event=_make_actual("E2", confidence="high"),
                    mismatch_reasons=["wrong"],
                ),
            ],
        )
        result = calibrate_confidence([sample1, sample2])
        # high: 1 TP out of 2 = 0.5
        assert result["high"] == pytest.approx(0.5)
