"""Tolerance assertion engine for regression test extraction results.

Provides three tolerance levels (strict, moderate, relaxed) for comparing
actual :class:`~cal_ai.models.extraction.ExtractionResult` objects against
expected :class:`~tests.regression.schema.SidecarSpec` definitions.

Uses greedy best-match event pairing to avoid false failures from event
reordering, and ``rapidfuzz.fuzz.token_set_ratio`` for fuzzy title
matching.  The greedy approach is sufficient for regression tests with
typical event counts (1-10 events per sample).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from rapidfuzz.fuzz import token_set_ratio

from cal_ai.models.extraction import ExtractedEvent, ExtractionResult

from .schema import SidecarExpectedEvent, SidecarSpec

# ---------------------------------------------------------------------------
# Tolerance thresholds
# ---------------------------------------------------------------------------

_TOLERANCE_LEVELS = ("strict", "moderate", "relaxed")


@dataclass(frozen=True)
class ToleranceThresholds:
    """Threshold values for a single tolerance level.

    Attributes:
        event_count_tolerance: Maximum allowed difference in event count.
        time_tolerance: Maximum allowed time difference for start/end times.
        title_ratio_min: Minimum ``token_set_ratio`` score (0-100) for title
            matching.
    """

    event_count_tolerance: int
    time_tolerance: timedelta
    title_ratio_min: float


THRESHOLDS: dict[str, ToleranceThresholds] = {
    "strict": ToleranceThresholds(
        event_count_tolerance=0,
        time_tolerance=timedelta(minutes=30),
        title_ratio_min=95.0,
    ),
    "moderate": ToleranceThresholds(
        event_count_tolerance=1,
        time_tolerance=timedelta(hours=2),
        title_ratio_min=80.0,
    ),
    "relaxed": ToleranceThresholds(
        event_count_tolerance=2,
        time_tolerance=timedelta(days=1),
        title_ratio_min=60.0,
    ),
}


# ---------------------------------------------------------------------------
# Event distance scoring for best-match pairing
# ---------------------------------------------------------------------------


def _action_distance(actual: str, expected: str) -> float:
    """Return 0.0 if actions match, 1000.0 otherwise.

    A high penalty ensures action mismatches dominate the pairing cost.
    """
    return 0.0 if actual == expected else 1000.0


def _title_distance(actual: str, expected: str) -> float:
    """Return a distance based on fuzzy title similarity.

    Uses ``rapidfuzz.fuzz.token_set_ratio`` (0-100).  Distance is
    ``100 - ratio`` so that identical titles yield 0.0 distance.
    """
    ratio = token_set_ratio(actual, expected)
    return 100.0 - ratio


def _time_distance(actual_iso: str | None, expected_iso: str | None) -> float:
    """Return the absolute time difference in minutes, or 0 if both are None.

    If one side is ``None`` and the other is not, returns a large penalty.
    """
    if actual_iso is None and expected_iso is None:
        return 0.0
    if actual_iso is None or expected_iso is None:
        return 10000.0

    try:
        actual_dt = datetime.fromisoformat(actual_iso)
        expected_dt = datetime.fromisoformat(expected_iso)
    except ValueError:
        return 10000.0

    diff = abs((actual_dt - expected_dt).total_seconds()) / 60.0
    return diff


def _event_pair_distance(actual: ExtractedEvent, expected: SidecarExpectedEvent) -> float:
    """Compute composite distance between an actual and expected event.

    Sum of action distance, title distance, and start_time distance.
    Lower is better.
    """
    return (
        _action_distance(actual.action, expected.action)
        + _title_distance(actual.title, expected.title)
        + _time_distance(actual.start_time, expected.start_time)
    )


# ---------------------------------------------------------------------------
# Best-match event pairing (greedy)
# ---------------------------------------------------------------------------


def _best_match_pairs(
    actual_events: list[ExtractedEvent],
    expected_events: list[SidecarExpectedEvent],
) -> list[tuple[ExtractedEvent, SidecarExpectedEvent, float]]:
    """Pair actual events with expected events using greedy best-match.

    For each expected event (in order), selects the closest unmatched
    actual event by composite distance (action + title + start_time).
    This greedy approach is not globally optimal but is sufficient for
    regression test suites where event counts are small (typically 1-10)
    and events are well-separated by action+title+time.

    Returns a list of ``(actual, expected, distance)`` tuples.  If there
    are fewer actual events than expected, some expected events will be
    unmatched (not included in the result).

    Args:
        actual_events: Events extracted by the pipeline.
        expected_events: Events defined in the sidecar spec.

    Returns:
        List of matched ``(actual, expected, distance)`` triples.
    """
    available = list(range(len(actual_events)))
    pairs: list[tuple[ExtractedEvent, SidecarExpectedEvent, float]] = []

    for exp in expected_events:
        if not available:
            break

        best_idx = -1
        best_dist = float("inf")

        for idx in available:
            dist = _event_pair_distance(actual_events[idx], exp)
            if dist < best_dist:
                best_dist = dist
                best_idx = idx

        if best_idx >= 0:
            pairs.append((actual_events[best_idx], exp, best_dist))
            available.remove(best_idx)

    return pairs


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


def _assert_time_within_tolerance(
    actual_iso: str | None,
    expected_iso: str | None,
    tolerance: timedelta,
    label: str,
) -> None:
    """Assert that two ISO datetime strings are within *tolerance*.

    Args:
        actual_iso: Actual ISO 8601 string from extraction.
        expected_iso: Expected ISO 8601 string from sidecar.
        tolerance: Maximum allowed difference.
        label: Human-readable label for error messages (e.g. "start_time").

    Raises:
        AssertionError: If the times differ by more than *tolerance*.
    """
    __tracebackhide__ = True

    if expected_iso is None:
        return  # Nothing to check.

    if actual_iso is None:
        raise AssertionError(f"{label}: expected {expected_iso!r} but got None")

    try:
        actual_dt = datetime.fromisoformat(actual_iso)
    except ValueError as exc:
        raise AssertionError(f"{label}: cannot parse actual {actual_iso!r}: {exc}") from exc

    try:
        expected_dt = datetime.fromisoformat(expected_iso)
    except ValueError as exc:
        raise AssertionError(
            f"{label}: cannot parse expected {expected_iso!r}: {exc}"
        ) from exc

    diff = abs(actual_dt - expected_dt)
    if diff > tolerance:
        raise AssertionError(
            f"{label}: time difference {diff} exceeds tolerance {tolerance} "
            f"(actual={actual_iso!r}, expected={expected_iso!r})"
        )


def _assert_title_match(
    actual: str,
    expected: str,
    min_ratio: float,
) -> None:
    """Assert fuzzy title similarity meets the minimum ratio.

    Args:
        actual: Actual event title.
        expected: Expected event title.
        min_ratio: Minimum ``token_set_ratio`` score (0-100).

    Raises:
        AssertionError: If the ratio is below *min_ratio*.
    """
    __tracebackhide__ = True
    ratio = token_set_ratio(actual, expected)
    if ratio < min_ratio:
        raise AssertionError(
            f"Title mismatch: token_set_ratio={ratio:.1f} < {min_ratio} "
            f"(actual={actual!r}, expected={expected!r})"
        )


def _assert_attendees_contain(
    actual_attendees: list[str],
    required_substrings: list[str],
) -> None:
    """Assert that all required attendee substrings appear in actual attendees.

    Comparison is case-insensitive.

    Args:
        actual_attendees: Attendee list from the extracted event.
        required_substrings: Substrings that must each appear in at least
            one actual attendee.

    Raises:
        AssertionError: If a required substring is not found.
    """
    __tracebackhide__ = True
    if not required_substrings:
        return

    actual_lower = [a.lower() for a in actual_attendees]

    for required in required_substrings:
        req_lower = required.lower()
        found = any(req_lower in attendee for attendee in actual_lower)
        if not found:
            raise AssertionError(
                f"Attendee check failed: {required!r} not found in "
                f"actual attendees {actual_attendees}"
            )


# ---------------------------------------------------------------------------
# Main assertion entry point
# ---------------------------------------------------------------------------


def _build_context_id_set(sidecar: SidecarSpec) -> set[int]:
    """Build the set of valid integer IDs from the sidecar's calendar context.

    Integer IDs are 1-based and sequential, matching the convention used
    by :func:`~tests.regression.loader.build_calendar_context`.

    Args:
        sidecar: A validated sidecar spec.

    Returns:
        A set of valid integer IDs (e.g., ``{1, 2, 3}``).
    """
    return set(range(1, len(sidecar.calendar_context) + 1))


def _resolve_delete_expected_time(
    expected_event: SidecarExpectedEvent,
    sidecar: SidecarSpec,
) -> tuple[str | None, str | None]:
    """Resolve expected start/end times for delete actions.

    For delete actions, the tolerance check should compare against the
    referenced calendar event's time (from ``calendar_context``), not
    the sidecar's expected event time.  If the expected event specifies
    ``existing_event_id_required`` and the sidecar has calendar context,
    look up the referenced event's times from the context.

    Falls back to the expected event's own times if no context match.

    Args:
        expected_event: The expected event from the sidecar.
        sidecar: The full sidecar spec (for calendar context lookup).

    Returns:
        A tuple of ``(start_time, end_time)`` ISO strings to compare against.
    """
    if expected_event.action != "delete" or not expected_event.existing_event_id_required:
        return expected_event.start_time, expected_event.end_time

    # Look up the calendar context event by its 1-based index.
    # The expected_event doesn't carry the integer ID directly, but the
    # actual event will.  We fall back to the sidecar's expected times.
    # The actual resolution happens in the main loop where we have the
    # actual_event's existing_event_id.
    return expected_event.start_time, expected_event.end_time


def _resolve_delete_time_from_context(
    actual_event_id: int | None,
    sidecar: SidecarSpec,
) -> tuple[str | None, str | None]:
    """Resolve start/end times from calendar context for a delete action.

    When a delete action references an existing calendar event via
    ``existing_event_id``, the time tolerance should be checked against
    the referenced event's original times from the calendar context.

    Args:
        actual_event_id: The integer ID from the extracted event.
        sidecar: The full sidecar spec with calendar context.

    Returns:
        A tuple of ``(start_time, end_time)`` from the referenced calendar
        context event, or ``(None, None)`` if the ID is not found.
    """
    if actual_event_id is None or not sidecar.calendar_context:
        return None, None

    idx = actual_event_id - 1  # Convert 1-based to 0-based.
    if 0 <= idx < len(sidecar.calendar_context):
        ctx_event = sidecar.calendar_context[idx]
        return ctx_event.start, ctx_event.end

    return None, None


def assert_extraction_result(
    actual: ExtractionResult,
    sidecar: SidecarSpec,
) -> None:
    """Assert that an extraction result matches the sidecar expectations.

    This is the main entry point for the tolerance assertion engine.
    Uses best-match event pairing and the sidecar's tolerance level
    to validate event count, actions, titles, times, and attendees.

    For delete actions with ``existing_event_id``, time tolerance is
    checked against the referenced calendar context event's times
    (not the sidecar's expected event times).

    Args:
        actual: The pipeline's extraction result.
        sidecar: The sidecar spec with expected events and tolerance.

    Raises:
        AssertionError: If any assertion fails.
    """
    __tracebackhide__ = True

    level: Literal["strict", "moderate", "relaxed"] = sidecar.tolerance
    thresholds = THRESHOLDS[level]

    expected_events = sidecar.expected_events
    actual_events = actual.events

    # Build the set of valid context IDs for validation.
    valid_context_ids = _build_context_id_set(sidecar)

    # --- Event count check ---
    count_diff = abs(len(actual_events) - len(expected_events))
    if count_diff > thresholds.event_count_tolerance:
        raise AssertionError(
            f"Event count mismatch [{level}]: "
            f"expected {len(expected_events)} (+-{thresholds.event_count_tolerance}), "
            f"got {len(actual_events)}"
        )

    # --- Best-match pairing ---
    pairs = _best_match_pairs(actual_events, expected_events)

    # --- Per-pair assertions ---
    errors: list[str] = []

    for actual_event, expected_event, _dist in pairs:
        pair_label = f"[{expected_event.action}] {expected_event.title!r}"

        # Action match (always exact).
        if actual_event.action != expected_event.action:
            errors.append(
                f"{pair_label}: action mismatch: "
                f"actual={actual_event.action!r}, expected={expected_event.action!r}"
            )
            continue  # Skip further checks if action is wrong.

        # Title fuzzy match.
        try:
            _assert_title_match(
                actual_event.title,
                expected_event.title,
                thresholds.title_ratio_min,
            )
        except AssertionError as exc:
            errors.append(f"{pair_label}: {exc}")

        # Resolve expected times: for delete actions with a referenced
        # calendar context event, use the context event's times instead.
        expected_start = expected_event.start_time
        expected_end = expected_event.end_time
        if (
            actual_event.action == "delete"
            and actual_event.existing_event_id is not None
            and sidecar.calendar_context
        ):
            ctx_start, ctx_end = _resolve_delete_time_from_context(
                actual_event.existing_event_id, sidecar
            )
            if ctx_start is not None:
                expected_start = ctx_start
            if ctx_end is not None:
                expected_end = ctx_end

        # Start time tolerance.
        try:
            _assert_time_within_tolerance(
                actual_event.start_time,
                expected_start,
                thresholds.time_tolerance,
                f"{pair_label} start_time",
            )
        except AssertionError as exc:
            errors.append(str(exc))

        # End time tolerance.
        try:
            _assert_time_within_tolerance(
                actual_event.end_time,
                expected_end,
                thresholds.time_tolerance,
                f"{pair_label} end_time",
            )
        except AssertionError as exc:
            errors.append(str(exc))

        # Existing event ID required check: must be non-None AND valid.
        if expected_event.existing_event_id_required:
            if actual_event.existing_event_id is None:
                errors.append(
                    f"{pair_label}: existing_event_id is required but was None"
                )
            elif valid_context_ids and actual_event.existing_event_id not in valid_context_ids:
                errors.append(
                    f"{pair_label}: existing_event_id={actual_event.existing_event_id} "
                    f"is not in valid context IDs {sorted(valid_context_ids)}"
                )

        # Attendees subset check.
        try:
            _assert_attendees_contain(
                actual_event.attendees,
                expected_event.attendees_contain,
            )
        except AssertionError as exc:
            errors.append(f"{pair_label}: {exc}")

        # Location check (only if sidecar specifies one).
        if expected_event.location is not None:
            try:
                _assert_title_match(
                    actual_event.location or "",
                    expected_event.location,
                    thresholds.title_ratio_min,
                )
            except AssertionError as exc:
                errors.append(f"{pair_label} location: {exc}")

    if errors:
        error_text = "\n  ".join(errors)
        raise AssertionError(
            f"Extraction assertion failures [{level}] "
            f"({len(errors)} issue(s)):\n  {error_text}"
        )
