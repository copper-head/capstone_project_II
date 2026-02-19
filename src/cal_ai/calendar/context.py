"""Calendar context fetcher and ID remapping for LLM prompt injection.

Fetches the owner's upcoming events from Google Calendar and formats them
as compact prompt context with integer ID remapping.  Integer IDs replace
long Google Calendar UUIDs to reduce LLM error rates (~5% vs ~50% with
raw UUIDs, per BAML research).

Key function:
    :func:`fetch_calendar_context` -- fetches a configurable time window
    of events and returns a :class:`CalendarContext` with formatted text,
    an integer-to-UUID mapping, and an event count.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from cal_ai.calendar.client import GoogleCalendarClient

logger = logging.getLogger(__name__)

# Default lookahead window in days.
_DEFAULT_WINDOW_DAYS = 14


@dataclass
class CalendarContext:
    """Formatted calendar context for LLM prompt injection.

    Attributes:
        events_text: Compact one-line-per-event text with integer IDs,
            ready to be appended to the LLM prompt.
        id_map: Mapping from integer IDs (starting at 1) back to Google
            Calendar event UUIDs.  Enables reverse lookup after LLM
            response: ``id_map[3] -> "abc123googleeventid"``.
        event_count: Number of events in the context window.
    """

    events_text: str = ""
    id_map: dict[int, str] = field(default_factory=dict)
    event_count: int = 0


def _format_event_line(idx: int, event: dict) -> str:
    """Format a single Google Calendar event as a compact one-line string.

    Format: ``[ID] Title | Start - End | Location``

    Args:
        idx: The integer ID for this event (1-based).
        event: A Google Calendar event resource dict.

    Returns:
        A single formatted line.
    """
    title = event.get("summary", "(No title)")

    # Extract start/end display strings.
    start_obj = event.get("start", {})
    end_obj = event.get("end", {})
    start_str = start_obj.get("dateTime") or start_obj.get("date", "?")
    end_str = end_obj.get("dateTime") or end_obj.get("date", "?")

    location = event.get("location", "")

    parts = [f"[{idx}] {title}", f"{start_str} - {end_str}"]
    if location:
        parts.append(location)

    return " | ".join(parts)


def _parse_sort_key(event: dict) -> datetime:
    """Extract a datetime from an event for chronological sorting.

    Falls back to ``datetime.max`` if the start time cannot be parsed,
    pushing unparsable events to the end of the list.

    Args:
        event: A Google Calendar event resource dict.

    Returns:
        A ``datetime`` for sorting.
    """
    start_obj = event.get("start", {})
    start_str = start_obj.get("dateTime") or start_obj.get("date")

    if start_str is None:
        return datetime.max

    try:
        dt = datetime.fromisoformat(start_str)
        # Strip tzinfo for consistent sorting with naive datetimes.
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except ValueError:
        return datetime.max


def fetch_calendar_context(
    client: GoogleCalendarClient,
    now: datetime,
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> CalendarContext:
    """Fetch upcoming calendar events and format them as prompt context.

    Calls ``client.list_events()`` for the window from *now* to
    *now + window_days* days, sorts events chronologically, assigns
    sequential integer IDs starting at 1, and formats each event as a
    compact one-line string.

    On fetch failure (network error, API error), returns an empty
    :class:`CalendarContext` with a warning logged -- the pipeline is
    never blocked by a context fetch failure.

    Args:
        client: An authenticated :class:`GoogleCalendarClient`.
        now: The current datetime (start of the fetch window).
        window_days: Number of days to look ahead.  Defaults to 14.

    Returns:
        A :class:`CalendarContext` with formatted text, ID mapping,
        and event count.
    """
    time_min = now
    time_max = now + timedelta(days=window_days)

    try:
        raw_events = client.list_events(time_min=time_min, time_max=time_max)
    except Exception:
        logger.warning(
            "Failed to fetch calendar context; proceeding without context",
            exc_info=True,
        )
        return CalendarContext()

    # Sort chronologically.
    sorted_events = sorted(raw_events, key=_parse_sort_key)

    # Build ID map and formatted lines.
    id_map: dict[int, str] = {}
    lines: list[str] = []

    for i, event in enumerate(sorted_events, start=1):
        event_id = event.get("id", "")
        id_map[i] = event_id
        lines.append(_format_event_line(i, event))

    events_text = "\n".join(lines)

    return CalendarContext(
        events_text=events_text,
        id_map=id_map,
        event_count=len(sorted_events),
    )
