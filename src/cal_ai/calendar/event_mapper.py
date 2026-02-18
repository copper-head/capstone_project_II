"""Map extracted events to the Google Calendar API body format.

Converts :class:`~cal_ai.models.extraction.ValidatedEvent` instances into
``dict`` payloads suitable for the Google Calendar ``events().insert()`` and
``events().update()`` API methods.

The mapping includes:

- **summary** from the event title.
- **location** (when provided).
- **start / end** with ISO 8601 datetimes and the configured IANA timezone.
- **description** containing the LLM reasoning and assumptions for demo
  observability.
- **attendees** -- the calendar owner is mapped to their email address;
  other attendees are listed by display name in the description body
  (the LLM extracts names, not email addresses).
"""

from __future__ import annotations

import logging
from datetime import datetime

from cal_ai.models.extraction import ValidatedEvent

logger = logging.getLogger(__name__)


def map_to_google_event(
    event: ValidatedEvent,
    timezone: str,
    owner_email: str,
) -> dict:
    """Convert a validated event into a Google Calendar API event body.

    Args:
        event: A :class:`ValidatedEvent` with parsed ``datetime`` objects.
        timezone: IANA timezone string (e.g. ``"America/Vancouver"``) applied
            to the start and end times.
        owner_email: The Google account email of the calendar owner.  When the
            owner appears in the attendee list, they are added as a proper
            ``attendees`` entry with their email.

    Returns:
        A ``dict`` conforming to the Google Calendar Event resource schema,
        ready to be passed to ``events().insert()`` or ``events().update()``.
    """
    if event.end_time <= event.start_time:
        raise ValueError(
            f"end_time ({event.end_time.isoformat()}) must be after "
            f"start_time ({event.start_time.isoformat()})"
        )

    body: dict = {
        "summary": event.title,
        "start": _format_datetime(event.start_time, timezone),
        "end": _format_datetime(event.end_time, timezone),
        "description": _build_description(event, owner_email),
    }

    if event.location:
        body["location"] = event.location

    # Only add the owner as a Google Calendar attendee (has an email).
    # Other names from the LLM are listed in the description instead.
    attendee_entries = _build_attendees(event.attendees, owner_email)
    if attendee_entries:
        body["attendees"] = attendee_entries

    logger.info(
        "Mapped event '%s' (%s -> %s) to Google Calendar body",
        event.title,
        event.start_time.isoformat(),
        event.end_time.isoformat(),
    )

    return body


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_datetime(dt: datetime, timezone: str) -> dict:
    """Format a datetime for the Google Calendar API.

    Args:
        dt: The datetime value to format.
        timezone: IANA timezone string.

    Returns:
        A dict with ``dateTime`` in ISO 8601 format and ``timeZone``.
    """
    return {
        "dateTime": dt.isoformat(),
        "timeZone": timezone,
    }


def _build_description(event: ValidatedEvent, owner_email: str) -> str:
    """Build the event description with LLM reasoning for observability.

    Includes the extraction reasoning, any assumptions made, and a list of
    non-owner attendees (by display name) since the LLM only extracts names,
    not email addresses.

    Args:
        event: The validated event.
        owner_email: The calendar owner's email (used to identify the owner
            in the attendee list).

    Returns:
        A multi-line description string.
    """
    sections: list[str] = []

    # LLM reasoning
    sections.append(f"Reasoning: {event.reasoning}")

    # Assumptions
    if event.assumptions:
        assumptions_text = "; ".join(event.assumptions)
        sections.append(f"Assumptions: {assumptions_text}")

    # Other attendees (non-owner names)
    other_attendees = [name for name in event.attendees if name.lower() != owner_email.lower()]
    if other_attendees:
        names = ", ".join(other_attendees)
        sections.append(f"Other attendees: {names}")

    return "\n".join(sections)


def _build_attendees(
    attendees: list[str],
    owner_email: str,
) -> list[dict]:
    """Build the attendees list for the Google Calendar API.

    Only the calendar owner is mapped to a proper attendee entry (with their
    email address).  Other attendees extracted by the LLM are names without
    email addresses and are instead included in the event description.

    Args:
        attendees: List of attendee names from the LLM extraction.
        owner_email: The Google account email of the calendar owner.

    Returns:
        A list of attendee dicts.  May be empty if the owner is not in the
        attendee list.
    """
    entries: list[dict] = []

    for name in attendees:
        if name.lower() == owner_email.lower():
            entries.append({"email": owner_email})

    return entries
