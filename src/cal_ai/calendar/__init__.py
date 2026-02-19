"""Google Calendar integration for cal-ai."""

from __future__ import annotations

from cal_ai.calendar.auth import get_calendar_credentials
from cal_ai.calendar.client import GoogleCalendarClient
from cal_ai.calendar.context import CalendarContext, fetch_calendar_context
from cal_ai.calendar.event_mapper import map_to_google_event
from cal_ai.calendar.sync import sync_events

__all__ = [
    "CalendarContext",
    "GoogleCalendarClient",
    "fetch_calendar_context",
    "get_calendar_credentials",
    "map_to_google_event",
    "sync_events",
]
