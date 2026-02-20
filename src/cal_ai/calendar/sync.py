"""Sync orchestrator for Google Calendar event operations.

Provides :func:`sync_events`, the top-level entry point that takes a batch of
validated events and dispatches each one to the appropriate
:class:`~cal_ai.calendar.client.GoogleCalendarClient` method based on its
``action`` field (``"create"``, ``"update"``, or ``"delete"``).

Partial failures are handled gracefully -- a single failing event does not
prevent the remaining events from being processed.  Results are aggregated
into a :class:`~cal_ai.models.calendar.SyncResult`.
"""

from __future__ import annotations

import logging

from cal_ai.calendar.client import GoogleCalendarClient
from cal_ai.models.calendar import SyncResult
from cal_ai.models.extraction import ValidatedEvent

logger = logging.getLogger(__name__)


def sync_events(
    events: list[ValidatedEvent],
    client: GoogleCalendarClient,
) -> SyncResult:
    """Sync a batch of validated events to Google Calendar.

    Iterates over *events* and dispatches each one to the correct client
    method based on ``event.action``:

    - ``"create"`` -- calls :meth:`GoogleCalendarClient.create_event`.
      A ``None`` return means the event was a duplicate and is counted as
      *skipped* rather than *created*.
    - ``"update"`` -- calls :meth:`GoogleCalendarClient.find_and_update_event`.
      A ``None`` return means no matching event was found and is counted as
      *skipped*.
    - ``"delete"`` -- calls :meth:`GoogleCalendarClient.find_and_delete_event`.
      A ``False`` return means no matching event was found and is counted as
      *skipped*.

    Processing continues even if individual events fail.  Failures are
    recorded in the returned :class:`SyncResult` for inspection.

    Args:
        events: List of validated events to sync.
        client: An initialised :class:`GoogleCalendarClient` instance.

    Returns:
        A :class:`SyncResult` with counts for created, updated, deleted,
        and skipped events, plus any conflicts and failures.
    """
    result = SyncResult()

    logger.info("Starting sync of %d event(s)", len(events))

    for event in events:
        try:
            _dispatch_event(event, client, result)
        except Exception as exc:
            logger.error(
                "Failed to sync event '%s' (action=%s): %s",
                event.title,
                event.action,
                exc,
            )
            result.failures.append(
                {
                    "event": event.title,
                    "action": event.action,
                    "error": str(exc),
                }
            )

    logger.info(
        "Sync complete: %d created, %d updated, %d deleted, %d skipped, "
        "%d failure(s), %d conflict(s)",
        result.created,
        result.updated,
        result.deleted,
        result.skipped,
        len(result.failures),
        len(result.conflicts),
    )

    return result


def _dispatch_event(
    event: ValidatedEvent,
    client: GoogleCalendarClient,
    result: SyncResult,
) -> None:
    """Dispatch a single event to the appropriate client method.

    Mutates *result* in place, incrementing the relevant counter.

    Args:
        event: The validated event to process.
        client: The calendar client.
        result: The running sync result to update.

    Raises:
        ValueError: If ``event.action`` is not one of
            ``"create"``, ``"update"``, or ``"delete"``.
        Exception: Any exception raised by the underlying client method
            is propagated to the caller for failure tracking.
    """
    action = event.action

    if action == "create":
        _handle_create(event, client, result)
    elif action == "update":
        _handle_update(event, client, result)
    elif action == "delete":
        _handle_delete(event, client, result)
    else:
        raise ValueError(f"Unknown event action: {action!r}")


def _handle_create(
    event: ValidatedEvent,
    client: GoogleCalendarClient,
    result: SyncResult,
) -> None:
    """Handle a create action for a single event.

    Args:
        event: The event to create.
        client: The calendar client.
        result: The running sync result to update.
    """
    response = client.create_event(event)
    if response is None:
        # Duplicate detected -- event was skipped.
        result.skipped += 1
        logger.info("Event '%s' skipped (duplicate)", event.title)
    else:
        result.created += 1
        logger.info("Event '%s' created successfully", event.title)


def _handle_update(
    event: ValidatedEvent,
    client: GoogleCalendarClient,
    result: SyncResult,
) -> None:
    """Handle an update action for a single event.

    Args:
        event: The event containing updated data and search criteria.
        client: The calendar client.
        result: The running sync result to update.
    """
    response = client.find_and_update_event(event)
    if response is None:
        # No matching event found to update.
        result.skipped += 1
        logger.info("Event '%s' skipped (no match for update)", event.title)
    else:
        result.updated += 1
        logger.info("Event '%s' updated successfully", event.title)


def _handle_delete(
    event: ValidatedEvent,
    client: GoogleCalendarClient,
    result: SyncResult,
) -> None:
    """Handle a delete action for a single event.

    Args:
        event: The event containing search criteria for deletion.
        client: The calendar client.
        result: The running sync result to update.
    """
    deleted = client.find_and_delete_event(event)
    if not deleted:
        # No matching event found to delete.
        result.skipped += 1
        logger.info("Event '%s' skipped (no match for delete)", event.title)
    else:
        result.deleted += 1
        logger.info("Event '%s' deleted successfully", event.title)
