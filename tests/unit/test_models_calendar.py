"""Tests for Google Calendar sync result models.

Covers SyncResult dataclass instantiation, defaults, computed properties,
and aggregation behavior.
"""

from __future__ import annotations

from cal_ai.models.calendar import SyncResult


class TestSyncResultDefaults:
    """Tests for SyncResult default values."""

    def test_default_construction_all_zeros(self) -> None:
        """Default SyncResult has all counters at zero and empty lists."""
        result = SyncResult()

        assert result.created == 0
        assert result.updated == 0
        assert result.deleted == 0
        assert result.skipped == 0
        assert result.conflicts == []
        assert result.failures == []

    def test_default_total_processed_zero(self) -> None:
        """Default SyncResult reports zero total processed."""
        result = SyncResult()

        assert result.total_processed == 0

    def test_default_no_failures(self) -> None:
        """Default SyncResult reports no failures."""
        result = SyncResult()

        assert result.has_failures is False

    def test_default_no_conflicts(self) -> None:
        """Default SyncResult reports no conflicts."""
        result = SyncResult()

        assert result.has_conflicts is False


class TestSyncResultCounts:
    """Tests for SyncResult with explicit counts."""

    def test_explicit_counts_stored(self) -> None:
        """Explicit counter values are stored correctly."""
        result = SyncResult(created=3, updated=1, deleted=2, skipped=1)

        assert result.created == 3
        assert result.updated == 1
        assert result.deleted == 2
        assert result.skipped == 1

    def test_total_processed_sums_create_update_delete(self) -> None:
        """total_processed sums created + updated + deleted (not skipped)."""
        result = SyncResult(created=3, updated=1, deleted=2, skipped=5)

        assert result.total_processed == 6

    def test_total_processed_excludes_skipped(self) -> None:
        """Skipped events are not counted in total_processed."""
        result = SyncResult(created=0, updated=0, deleted=0, skipped=10)

        assert result.total_processed == 0


class TestSyncResultConflicts:
    """Tests for SyncResult conflict tracking."""

    def test_has_conflicts_true_when_conflicts_present(self) -> None:
        """has_conflicts is True when conflicts list is non-empty."""
        result = SyncResult(
            conflicts=[{"event": "Meeting", "conflicting_with": "Lunch"}],
        )

        assert result.has_conflicts is True

    def test_has_conflicts_false_when_empty(self) -> None:
        """has_conflicts is False when conflicts list is empty."""
        result = SyncResult(conflicts=[])

        assert result.has_conflicts is False

    def test_multiple_conflicts_stored(self) -> None:
        """Multiple conflict dicts are stored and accessible."""
        conflicts = [
            {"event": "Meeting A", "conflicting_with": "Meeting B"},
            {"event": "Meeting A", "conflicting_with": "Meeting C"},
        ]
        result = SyncResult(conflicts=conflicts)

        assert len(result.conflicts) == 2
        assert result.conflicts[0]["event"] == "Meeting A"
        assert result.conflicts[1]["conflicting_with"] == "Meeting C"


class TestSyncResultFailures:
    """Tests for SyncResult failure tracking."""

    def test_has_failures_true_when_failures_present(self) -> None:
        """has_failures is True when failures list is non-empty."""
        result = SyncResult(
            failures=[{"event": "Meeting", "error": "API timeout"}],
        )

        assert result.has_failures is True

    def test_has_failures_false_when_empty(self) -> None:
        """has_failures is False when failures list is empty."""
        result = SyncResult(failures=[])

        assert result.has_failures is False

    def test_multiple_failures_stored(self) -> None:
        """Multiple failure dicts are stored and accessible."""
        failures = [
            {"event": "Meeting A", "error": "Rate limited"},
            {"event": "Meeting B", "error": "Auth expired"},
        ]
        result = SyncResult(failures=failures)

        assert len(result.failures) == 2
        assert result.failures[0]["error"] == "Rate limited"
        assert result.failures[1]["error"] == "Auth expired"


class TestSyncResultMixed:
    """Tests for SyncResult with a realistic mixed-outcome scenario."""

    def test_mixed_outcome_scenario(self) -> None:
        """A realistic sync with creates, skips, conflicts, and failures."""
        result = SyncResult(
            created=5,
            updated=2,
            deleted=1,
            skipped=3,
            conflicts=[{"event": "Standup", "conflicting_with": "All-hands"}],
            failures=[{"event": "Bad event", "error": "Invalid time"}],
        )

        assert result.total_processed == 8
        assert result.has_conflicts is True
        assert result.has_failures is True
        assert result.skipped == 3


class TestSyncResultImport:
    """Tests that SyncResult is importable from the models package."""

    def test_import_from_models_package(self) -> None:
        """SyncResult is re-exported from cal_ai.models."""
        from cal_ai.models import SyncResult as SyncResultFromPackage

        result = SyncResultFromPackage(created=1)
        assert result.created == 1

    def test_sync_result_is_mutable(self) -> None:
        """SyncResult fields can be updated after construction (not frozen)."""
        result = SyncResult()
        result.created += 1
        result.failures.append({"event": "Test", "error": "Fail"})

        assert result.created == 1
        assert len(result.failures) == 1
