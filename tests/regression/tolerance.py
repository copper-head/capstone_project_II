"""Tolerance assertion engine for regression test extraction results.

Provides three tolerance levels (strict, moderate, relaxed) for comparing
actual :class:`~cal_ai.models.extraction.ExtractionResult` objects against
expected :class:`~tests.regression.schema.SidecarSpec` definitions.

Uses minimum-cost bipartite matching (Hungarian algorithm) for optimal
event pairing to avoid false failures from event reordering, and
``rapidfuzz.fuzz.token_set_ratio`` for fuzzy title matching.
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
# Minimum-cost bipartite matching (Hungarian algorithm)
# ---------------------------------------------------------------------------


def _hungarian_assignment(cost_matrix: list[list[float]]) -> list[tuple[int, int]]:
    """Solve the linear assignment problem using the Hungarian algorithm.

    Given an n x m cost matrix, finds the assignment of rows to columns
    that minimizes total cost.  Handles rectangular matrices by padding
    to square with high-cost dummy entries.

    This is an O(n^3) implementation suitable for the small matrices
    encountered in regression tests (typically < 10x10).

    Args:
        cost_matrix: An n x m matrix of costs, where ``cost_matrix[i][j]``
            is the cost of assigning row *i* to column *j*.

    Returns:
        A list of ``(row, col)`` pairs representing the optimal assignment.
        Only includes pairs where both row and col are within the original
        (non-padded) matrix dimensions.
    """
    if not cost_matrix or not cost_matrix[0]:
        return []

    n_rows = len(cost_matrix)
    n_cols = len(cost_matrix[0])
    n = max(n_rows, n_cols)

    # Pad to square with large dummy costs.
    pad_cost = 1e9
    matrix = [[pad_cost] * n for _ in range(n)]
    for i in range(n_rows):
        for j in range(n_cols):
            matrix[i][j] = cost_matrix[i][j]

    # Hungarian algorithm (Kuhn-Munkres).
    u = [0.0] * (n + 1)  # Row potentials.
    v = [0.0] * (n + 1)  # Column potentials.
    p = [0] * (n + 1)  # Column assignment: p[j] = row assigned to col j.
    way = [0] * (n + 1)  # Augmenting path backtrack.

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        min_v = [float("inf")] * (n + 1)
        used = [False] * (n + 1)

        while True:
            used[j0] = True
            i0 = p[j0]
            delta = float("inf")
            j1 = -1

            for j in range(1, n + 1):
                if not used[j]:
                    cur = matrix[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < min_v[j]:
                        min_v[j] = cur
                        way[j] = j0
                    if min_v[j] < delta:
                        delta = min_v[j]
                        j1 = j

            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    min_v[j] -= delta

            j0 = j1
            if p[j0] == 0:
                break

        # Backtrack to update assignment.
        while j0:
            p[j0] = p[way[j0]]
            j0 = way[j0]

    # Extract assignments (filter out dummy rows/cols).
    result: list[tuple[int, int]] = []
    for j in range(1, n + 1):
        if p[j] != 0 and p[j] - 1 < n_rows and j - 1 < n_cols:
            result.append((p[j] - 1, j - 1))

    return result


def _best_match_pairs(
    actual_events: list[ExtractedEvent],
    expected_events: list[SidecarExpectedEvent],
) -> list[tuple[ExtractedEvent, SidecarExpectedEvent, float]]:
    """Pair actual events with expected events using minimum-cost matching.

    Builds a cost matrix of composite distances (action + title + start_time)
    and solves the linear assignment problem using the Hungarian algorithm
    to find the globally optimal pairing that minimizes total distance.

    Returns a list of ``(actual, expected, distance)`` tuples.  If there
    are fewer actual events than expected, some expected events will be
    unmatched (not included in the result).

    Args:
        actual_events: Events extracted by the pipeline.
        expected_events: Events defined in the sidecar spec.

    Returns:
        List of matched ``(actual, expected, distance)`` triples.
    """
    if not actual_events or not expected_events:
        return []

    # Build cost matrix: rows = actual, cols = expected.
    cost_matrix: list[list[float]] = []
    for act in actual_events:
        row = [_event_pair_distance(act, exp) for exp in expected_events]
        cost_matrix.append(row)

    # Solve assignment.
    assignment = _hungarian_assignment(cost_matrix)

    # Build result pairs.
    pairs: list[tuple[ExtractedEvent, SidecarExpectedEvent, float]] = []
    for act_idx, exp_idx in assignment:
        dist = cost_matrix[act_idx][exp_idx]
        pairs.append((actual_events[act_idx], expected_events[exp_idx], dist))

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
            elif not valid_context_ids:
                errors.append(
                    f"{pair_label}: existing_event_id_required=True but "
                    f"calendar_context is empty (no valid IDs to match against)"
                )
            elif actual_event.existing_event_id not in valid_context_ids:
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
