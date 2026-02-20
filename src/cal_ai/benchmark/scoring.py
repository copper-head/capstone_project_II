"""Scoring engine for benchmark Precision/Recall/F1 metrics.

Reuses fn-7's best-match Hungarian algorithm and tolerance thresholds
to pair actual extraction events against expected sidecar events, then
classifies each match as a true positive (TP) or mismatch.  Unmatched
actual events are false positives (FP) and unmatched expected events
are false negatives (FN).

Functions:
    :func:`score_sample` -- score a single sample's extraction result.
    :func:`aggregate_scores` -- aggregate per-sample scores into overall
        and per-category P/R/F1.
    :func:`calibrate_confidence` -- map confidence levels to accuracy
        percentages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from rapidfuzz.fuzz import token_set_ratio

from cal_ai.models.extraction import ExtractedEvent
from tests.regression.schema import SidecarExpectedEvent
from tests.regression.tolerance import (
    THRESHOLDS,
    _best_match_pairs,
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventMatchDetail:
    """Detail record for a single event pairing outcome.

    Attributes:
        classification: One of ``"tp"``, ``"fp"``, or ``"fn"``.
        actual_event: The extracted event (``None`` for FN).
        expected_event: The expected sidecar event (``None`` for FP).
        mismatch_reasons: List of reasons if a paired match failed tolerance
            checks (empty for TP, FP, and FN).
    """

    classification: Literal["tp", "fp", "fn"]
    actual_event: ExtractedEvent | None = None
    expected_event: SidecarExpectedEvent | None = None
    mismatch_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SampleScore:
    """Score result for a single benchmark sample.

    Attributes:
        sample_name: Identifier for the sample (e.g. ``"crud/simple_lunch"``).
        category: Sample category (e.g. ``"crud"``).
        tolerance: Tolerance level used for scoring.
        tp: True positive count.
        fp: False positive count.
        fn: False negative count.
        precision: Precision metric (0.0-1.0).
        recall: Recall metric (0.0-1.0).
        f1: F1 score (0.0-1.0).
        per_event_details: Detailed classification for each event.
    """

    sample_name: str
    category: str
    tolerance: str
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    per_event_details: list[EventMatchDetail] = field(default_factory=list)


@dataclass(frozen=True)
class CategoryScore:
    """Aggregate P/R/F1 for a single category.

    Attributes:
        category: Category name.
        tp: Total true positives across samples in this category.
        fp: Total false positives.
        fn: Total false negatives.
        precision: Category-level precision.
        recall: Category-level recall.
        f1: Category-level F1.
        sample_count: Number of samples in this category.
    """

    category: str
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    sample_count: int


@dataclass(frozen=True)
class AggregateScore:
    """Aggregate benchmark scores across all samples.

    Attributes:
        overall_tp: Total true positives across all samples.
        overall_fp: Total false positives.
        overall_fn: Total false negatives.
        overall_precision: Overall precision (micro-averaged).
        overall_recall: Overall recall (micro-averaged).
        overall_f1: Overall F1 (micro-averaged).
        per_category: Per-category score breakdown.
        sample_count: Total number of samples scored.
    """

    overall_tp: int
    overall_fp: int
    overall_fn: int
    overall_precision: float
    overall_recall: float
    overall_f1: float
    per_category: list[CategoryScore] = field(default_factory=list)
    sample_count: int = 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """Compute Precision, Recall, and F1 from raw counts.

    Edge cases per spec:
    - Both actual and expected empty (tp=0, fp=0, fn=0):
      P=1.0, R=1.0, F1=1.0 (vacuous truth).
    - Actual empty, expected non-empty (tp=0, fp=0, fn>0):
      P=1.0, R=0.0, F1=0.0.
    - Expected empty, actual non-empty (tp=0, fp>0, fn=0):
      P=0.0, R=1.0, F1=0.0.

    Args:
        tp: True positive count.
        fp: False positive count.
        fn: False negative count.

    Returns:
        Tuple of ``(precision, recall, f1)``.
    """
    # Vacuous truth: no actual and no expected events.
    if tp == 0 and fp == 0 and fn == 0:
        return 1.0, 1.0, 1.0

    # Precision: tp / (tp + fp). If no predictions made (tp+fp=0), P=1.0
    # (no false positives were produced).
    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0

    # Recall: tp / (tp + fn). If no expected events (tp+fn=0), R=1.0
    # (no events were missed).
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0

    # F1: harmonic mean.
    f1 = 2.0 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return precision, recall, f1


def _check_event_match(
    actual: ExtractedEvent,
    expected: SidecarExpectedEvent,
    tolerance: Literal["strict", "moderate", "relaxed"],
) -> list[str]:
    """Check whether an actual-expected event pair is within tolerance.

    Returns an empty list if the pair is a true positive (all checks pass),
    or a list of mismatch reason strings if it fails.

    Args:
        actual: Extracted event from the pipeline.
        expected: Expected event from the sidecar.
        tolerance: Tolerance level for matching.

    Returns:
        List of mismatch reasons (empty means TP).
    """
    thresholds = THRESHOLDS[tolerance]
    reasons: list[str] = []

    # Action match (always exact).
    if actual.action != expected.action:
        reasons.append(f"action: expected {expected.action!r}, got {actual.action!r}")
        return reasons  # Skip further checks if action is wrong.

    # Title match: exact for strict, fuzzy otherwise.
    if tolerance == "strict":
        if actual.title.strip().lower() != expected.title.strip().lower():
            reasons.append(
                f"title (strict exact): expected {expected.title!r}, got {actual.title!r}"
            )
    else:
        ratio = token_set_ratio(actual.title, expected.title)
        if ratio < thresholds.title_ratio_min:
            reasons.append(
                f"title: ratio={ratio:.1f} < {thresholds.title_ratio_min} "
                f"(expected {expected.title!r}, got {actual.title!r})"
            )

    # Start time tolerance.
    start_reason = _check_time_tolerance(
        actual.start_time,
        expected.start_time,
        thresholds.time_tolerance,
        "start_time",
    )
    if start_reason:
        reasons.append(start_reason)

    # End time tolerance.
    end_reason = _check_time_tolerance(
        actual.end_time,
        expected.end_time,
        thresholds.time_tolerance,
        "end_time",
    )
    if end_reason:
        reasons.append(end_reason)

    return reasons


def _check_time_tolerance(
    actual_iso: str | None,
    expected_iso: str | None,
    tolerance: timedelta,
    label: str,
) -> str | None:
    """Check whether two ISO datetime strings are within tolerance.

    Returns ``None`` if within tolerance, or a reason string if not.

    Args:
        actual_iso: Actual ISO 8601 string from extraction.
        expected_iso: Expected ISO 8601 string from sidecar.
        tolerance: Maximum allowed difference.
        label: Human-readable label for messages.

    Returns:
        ``None`` if OK, or a reason string describing the mismatch.
    """
    if expected_iso is None:
        return None  # Nothing to check.

    if actual_iso is None:
        return f"{label}: expected {expected_iso!r} but got None"

    try:
        actual_dt = datetime.fromisoformat(actual_iso)
    except ValueError:
        return f"{label}: cannot parse actual {actual_iso!r}"

    try:
        expected_dt = datetime.fromisoformat(expected_iso)
    except ValueError:
        return f"{label}: cannot parse expected {expected_iso!r}"

    diff = abs(actual_dt - expected_dt)
    if diff > tolerance:
        return (
            f"{label}: difference {diff} exceeds tolerance {tolerance} "
            f"(actual={actual_iso!r}, expected={expected_iso!r})"
        )

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_sample(
    actual_events: list[ExtractedEvent],
    expected_events: list[SidecarExpectedEvent],
    tolerance_level: Literal["strict", "moderate", "relaxed"],
    *,
    sample_name: str = "",
    category: str = "uncategorized",
) -> SampleScore:
    """Score a single sample by matching actual events to expected events.

    Uses fn-7's best-match Hungarian algorithm to pair events, then
    classifies each pair as TP (within tolerance) or mismatch. Unmatched
    actual events are FP, unmatched expected events are FN.

    Args:
        actual_events: Events extracted by the pipeline.
        expected_events: Events from the sidecar spec.
        tolerance_level: Tolerance level for matching.
        sample_name: Human-readable sample name for reporting.
        category: Sample category for aggregation.

    Returns:
        A :class:`SampleScore` with TP/FP/FN counts, P/R/F1 metrics,
        and per-event classification details.
    """
    details: list[EventMatchDetail] = []

    # Handle empty cases early.
    if not actual_events and not expected_events:
        precision, recall, f1 = _compute_prf(0, 0, 0)
        return SampleScore(
            sample_name=sample_name,
            category=category,
            tolerance=tolerance_level,
            tp=0,
            fp=0,
            fn=0,
            precision=precision,
            recall=recall,
            f1=f1,
            per_event_details=details,
        )

    # Best-match pairing via Hungarian algorithm.
    pairs = _best_match_pairs(actual_events, expected_events)

    # Track which indices were paired.
    paired_actual_indices: set[int] = set()
    paired_expected_indices: set[int] = set()

    tp = 0
    fp_from_mismatch = 0
    fn_from_mismatch = 0

    for actual_event, expected_event, _dist in pairs:
        # Find indices for tracking.
        act_idx = actual_events.index(actual_event)
        exp_idx = expected_events.index(expected_event)
        paired_actual_indices.add(act_idx)
        paired_expected_indices.add(exp_idx)

        # Check if the pair is within tolerance.
        mismatch_reasons = _check_event_match(
            actual_event,
            expected_event,
            tolerance_level,
        )

        if not mismatch_reasons:
            # True positive: matched and within tolerance.
            tp += 1
            details.append(
                EventMatchDetail(
                    classification="tp",
                    actual_event=actual_event,
                    expected_event=expected_event,
                )
            )
        else:
            # Paired but outside tolerance: counts as both FP and FN.
            fp_from_mismatch += 1
            fn_from_mismatch += 1
            details.append(
                EventMatchDetail(
                    classification="fp",
                    actual_event=actual_event,
                    expected_event=expected_event,
                    mismatch_reasons=mismatch_reasons,
                )
            )
            details.append(
                EventMatchDetail(
                    classification="fn",
                    actual_event=None,
                    expected_event=expected_event,
                    mismatch_reasons=mismatch_reasons,
                )
            )

    # Unmatched actual events are FP.
    fp_unmatched = 0
    for i, actual_event in enumerate(actual_events):
        if i not in paired_actual_indices:
            fp_unmatched += 1
            details.append(
                EventMatchDetail(
                    classification="fp",
                    actual_event=actual_event,
                )
            )

    # Unmatched expected events are FN.
    fn_unmatched = 0
    for i, expected_event in enumerate(expected_events):
        if i not in paired_expected_indices:
            fn_unmatched += 1
            details.append(
                EventMatchDetail(
                    classification="fn",
                    expected_event=expected_event,
                )
            )

    total_fp = fp_from_mismatch + fp_unmatched
    total_fn = fn_from_mismatch + fn_unmatched
    precision, recall, f1 = _compute_prf(tp, total_fp, total_fn)

    return SampleScore(
        sample_name=sample_name,
        category=category,
        tolerance=tolerance_level,
        tp=tp,
        fp=total_fp,
        fn=total_fn,
        precision=precision,
        recall=recall,
        f1=f1,
        per_event_details=details,
    )


def aggregate_scores(
    sample_scores: list[SampleScore],
) -> AggregateScore:
    """Aggregate per-sample scores into overall and per-category metrics.

    Uses micro-averaging: sums TP/FP/FN across all samples, then
    computes P/R/F1 from the totals.

    Args:
        sample_scores: List of per-sample scores.

    Returns:
        An :class:`AggregateScore` with overall and per-category breakdown.
    """
    if not sample_scores:
        return AggregateScore(
            overall_tp=0,
            overall_fp=0,
            overall_fn=0,
            overall_precision=1.0,
            overall_recall=1.0,
            overall_f1=1.0,
            sample_count=0,
        )

    # Overall micro-average.
    total_tp = sum(s.tp for s in sample_scores)
    total_fp = sum(s.fp for s in sample_scores)
    total_fn = sum(s.fn for s in sample_scores)
    overall_p, overall_r, overall_f1 = _compute_prf(total_tp, total_fp, total_fn)

    # Per-category breakdown.
    categories: dict[str, list[SampleScore]] = {}
    for s in sample_scores:
        categories.setdefault(s.category, []).append(s)

    per_category: list[CategoryScore] = []
    for cat_name in sorted(categories):
        cat_samples = categories[cat_name]
        cat_tp = sum(s.tp for s in cat_samples)
        cat_fp = sum(s.fp for s in cat_samples)
        cat_fn = sum(s.fn for s in cat_samples)
        cat_p, cat_r, cat_f1 = _compute_prf(cat_tp, cat_fp, cat_fn)
        per_category.append(
            CategoryScore(
                category=cat_name,
                tp=cat_tp,
                fp=cat_fp,
                fn=cat_fn,
                precision=cat_p,
                recall=cat_r,
                f1=cat_f1,
                sample_count=len(cat_samples),
            )
        )

    return AggregateScore(
        overall_tp=total_tp,
        overall_fp=total_fp,
        overall_fn=total_fn,
        overall_precision=overall_p,
        overall_recall=overall_r,
        overall_f1=overall_f1,
        per_category=per_category,
        sample_count=len(sample_scores),
    )


def calibrate_confidence(
    sample_scores: list[SampleScore],
) -> dict[str, float]:
    """Map confidence levels to accuracy percentages.

    Groups all scored events by their ``confidence`` field and calculates
    the percentage that are true positives for each level.

    Args:
        sample_scores: List of per-sample scores.

    Returns:
        A dict mapping confidence level (``"high"``, ``"medium"``,
        ``"low"``) to accuracy as a float in [0.0, 1.0].  Levels
        with no events are omitted.
    """
    # Collect all TP and FP details that have an actual_event
    # (these are the predictions we can assess confidence for).
    confidence_counts: dict[str, int] = {}
    confidence_correct: dict[str, int] = {}

    for sample in sample_scores:
        for detail in sample.per_event_details:
            if detail.actual_event is None:
                continue  # FN records have no actual event.
            conf = detail.actual_event.confidence
            confidence_counts[conf] = confidence_counts.get(conf, 0) + 1
            if detail.classification == "tp":
                confidence_correct[conf] = confidence_correct.get(conf, 0) + 1

    result: dict[str, float] = {}
    for conf_level in ("high", "medium", "low"):
        total = confidence_counts.get(conf_level, 0)
        if total > 0:
            correct = confidence_correct.get(conf_level, 0)
            result[conf_level] = correct / total

    return result
