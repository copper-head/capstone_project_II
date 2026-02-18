"""Data models for Google Calendar sync results.

Defines the structured output from the calendar sync orchestrator:

- :class:`SyncResult` -- aggregated outcome of syncing extracted events
  to Google Calendar, including counts and failure/conflict details.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SyncResult:
    """Aggregated result of syncing extracted events to Google Calendar.

    Returned by the sync orchestrator after processing a batch of events.
    Tracks how many events were created, updated, deleted, or skipped,
    along with any conflicts or failures encountered.

    Attributes:
        created: Number of events successfully created.
        updated: Number of events successfully updated.
        deleted: Number of events successfully deleted.
        skipped: Number of events skipped (e.g. duplicates).
        conflicts: Details of scheduling conflicts detected during sync.
            Each dict contains at minimum ``"event"`` and ``"conflicting_with"``
            keys describing the overlap.
        failures: Details of events that failed to sync.
            Each dict contains at minimum ``"event"`` and ``"error"`` keys.
    """

    created: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    conflicts: list[dict] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)

    @property
    def total_processed(self) -> int:
        """Total number of events that were successfully processed."""
        return self.created + self.updated + self.deleted

    @property
    def has_failures(self) -> bool:
        """Whether any events failed to sync."""
        return len(self.failures) > 0

    @property
    def has_conflicts(self) -> bool:
        """Whether any scheduling conflicts were detected."""
        return len(self.conflicts) > 0
