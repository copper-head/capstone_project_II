"""Pipeline orchestrator for the conversation-to-calendar workflow.

Wires all components together: transcript parsing, LLM event extraction,
Google Calendar sync, and result aggregation.  The top-level entry point
is :func:`run_pipeline`, which returns a :class:`PipelineResult` suitable
for rendering by the demo output formatter.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cal_ai.calendar.auth import get_calendar_credentials
from cal_ai.calendar.client import GoogleCalendarClient
from cal_ai.calendar.context import CalendarContext, fetch_calendar_context
from cal_ai.calendar.exceptions import CalendarNotFoundError
from cal_ai.config import load_settings
from cal_ai.exceptions import ExtractionError
from cal_ai.llm import GeminiClient
from cal_ai.models.extraction import ExtractedEvent, ValidatedEvent
from cal_ai.parser import parse_transcript_file

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventSyncResult:
    """Result of syncing a single event to Google Calendar.

    Attributes:
        event: The extracted event that was synced.
        action_taken: Calendar action performed (``"created"``,
            ``"updated"``, ``"deleted"``, or ``"skipped_duplicate"``).
        calendar_event_id: The Google Calendar event ID if available.
        success: Whether the sync succeeded.
        error: Error message if the sync failed.
        matched_event_title: Title of the existing calendar event that
            was matched for update/delete actions, or ``None``.
        matched_event_time: Start time of the matched existing event
            as an ISO 8601 string, or ``None``.
    """

    event: ExtractedEvent
    action_taken: str
    calendar_event_id: str | None = None
    success: bool = True
    error: str | None = None
    matched_event_title: str | None = None
    matched_event_time: str | None = None


@dataclass(frozen=True)
class FailedEvent:
    """An event that failed to sync to Google Calendar.

    Attributes:
        event: The extracted event that failed.
        error: Human-readable error description.
    """

    event: ExtractedEvent
    error: str


@dataclass
class PipelineResult:
    """Aggregated result from the full pipeline run.

    Contains all data needed to render the demo output: parse metadata,
    extracted events, sync outcomes, warnings, and timing.

    Attributes:
        transcript_path: Path to the input transcript file.
        speakers_found: Unique speakers discovered during parsing.
        utterance_count: Number of utterances in the parsed transcript.
        events_extracted: Events returned by the LLM extractor.
        events_synced: Successfully synced events with their outcomes.
        events_failed: Events that failed to sync.
        warnings: Non-fatal warnings from any pipeline stage.
        duration_seconds: Wall-clock time for the full pipeline.
        dry_run: Whether the pipeline ran in dry-run mode.
        id_map: Mapping from integer IDs (used in LLM context) to
            Google Calendar event UUIDs for reverse lookup during sync.
        event_meta: Mapping from integer IDs to event metadata dicts
            (``title``, ``start_time``).  Used by the demo output
            formatter to show matched event info.
    """

    transcript_path: Path
    speakers_found: list[str] = field(default_factory=list)
    utterance_count: int = 0
    events_extracted: list[ExtractedEvent] = field(default_factory=list)
    events_synced: list[EventSyncResult] = field(default_factory=list)
    events_failed: list[FailedEvent] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    dry_run: bool = False
    id_map: dict[int, str] = field(default_factory=dict)
    event_meta: dict[int, dict[str, str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def run_pipeline(
    transcript_path: Path,
    owner: str,
    dry_run: bool = False,
    current_datetime: datetime | None = None,
) -> PipelineResult:
    """Run the full conversation-to-calendar pipeline.

    Executes four stages:

    1. **Load and Parse** -- read the transcript file, extract speakers
       and utterances.
    2. **Extract Events** -- call the LLM to identify calendar events.
    3. **Sync to Calendar** -- for each event, dispatch the appropriate
       calendar operation (create/update/delete).  Skipped in dry-run mode.
    4. **Summary** -- compute timing and return the aggregated result.

    File-not-found and permission errors are raised immediately.  LLM
    failures result in an empty extraction (zero events).  Individual
    sync failures are recorded but do not stop processing of remaining
    events.

    Args:
        transcript_path: Path to the ``.txt`` transcript file.
        owner: Display name of the calendar owner.
        dry_run: If ``True``, parse and extract but skip calendar sync.
        current_datetime: Override for the current datetime (useful for
            testing).  Defaults to ``datetime.now()`` if not provided.

    Returns:
        A :class:`PipelineResult` with all pipeline outputs.

    Raises:
        FileNotFoundError: If *transcript_path* does not exist.
        PermissionError: If *transcript_path* is not readable.
    """
    start_time = time.monotonic()
    now = current_datetime or datetime.now()

    result = PipelineResult(transcript_path=transcript_path, dry_run=dry_run)

    # ------------------------------------------------------------------
    # Stage 1: Load and Parse
    # ------------------------------------------------------------------
    logger.info("Stage 1: Loading and parsing transcript from %s", transcript_path)

    parse_result = parse_transcript_file(transcript_path)

    result.speakers_found = parse_result.speakers
    result.utterance_count = len(parse_result.utterances)

    # Carry forward any parse warnings.
    for warning in parse_result.warnings:
        msg = f"Parse warning at line {warning.line_number}: {warning.message}"
        result.warnings.append(msg)
        logger.warning(msg)

    logger.info(
        "Stage 1 complete: %d speaker(s), %d utterance(s)",
        len(result.speakers_found),
        result.utterance_count,
    )

    if result.utterance_count == 0:
        logger.info("No utterances found, skipping extraction")
        result.duration_seconds = time.monotonic() - start_time
        return result

    # ------------------------------------------------------------------
    # Stage 1b: Build calendar client and fetch context
    # ------------------------------------------------------------------
    settings = load_settings()

    calendar_context = CalendarContext()
    client: GoogleCalendarClient | None = None

    try:
        client = _build_calendar_client(settings)
        calendar_context = fetch_calendar_context(client, now)
        result.id_map = calendar_context.id_map
        result.event_meta = calendar_context.event_meta
        logger.info(
            "Calendar context fetched: %d event(s) in window",
            calendar_context.event_count,
        )
    except Exception as exc:
        msg = f"Calendar context unavailable, extracting without context: {exc}"
        result.warnings.append(msg)
        logger.warning(msg)

    # ------------------------------------------------------------------
    # Stage 2: Extract Events
    # ------------------------------------------------------------------
    logger.info("Stage 2: Extracting events via LLM")

    gemini = GeminiClient(api_key=settings.gemini_api_key)

    # Build the transcript text for the LLM from the parsed utterances.
    transcript_text = _build_transcript_text(parse_result.utterances)

    try:
        extraction = gemini.extract_events(
            transcript_text=transcript_text,
            owner_name=owner,
            current_datetime=now,
            calendar_context=calendar_context.events_text,
        )
        result.events_extracted = list(extraction.events)
    except ExtractionError as exc:
        msg = f"LLM extraction failed: {exc}"
        result.warnings.append(msg)
        logger.error(msg)
        result.duration_seconds = time.monotonic() - start_time
        return result

    logger.info(
        "Stage 2 complete: %d event(s) extracted",
        len(result.events_extracted),
    )

    if not result.events_extracted:
        result.duration_seconds = time.monotonic() - start_time
        return result

    # ------------------------------------------------------------------
    # Stage 3: Sync to Calendar
    # ------------------------------------------------------------------
    if dry_run:
        logger.info("Stage 3: Dry-run mode -- skipping calendar sync")
        for event in result.events_extracted:
            matched_title, matched_time = _lookup_matched_event(
                event.existing_event_id, result.event_meta
            )
            result.events_synced.append(
                EventSyncResult(
                    event=event,
                    action_taken=f"would_{event.action}",
                    success=True,
                    matched_event_title=matched_title,
                    matched_event_time=matched_time,
                )
            )
    else:
        logger.info(
            "Stage 3: Syncing %d event(s) to Google Calendar",
            len(result.events_extracted),
        )

        # If we don't have a client yet (context fetch was skipped/failed),
        # build one now for the sync stage.
        if client is None:
            client = _build_calendar_client(settings)

        # Validate extracted events and correlate by index position.
        validated_list = _validate_events(gemini, extraction, now)

        for i, event in enumerate(result.events_extracted):
            if i >= len(validated_list):
                result.events_failed.append(
                    FailedEvent(event=event, error="Event validation failed")
                )
                continue

            validated = validated_list[i]

            try:
                sync_result = _sync_single_event(
                    validated, client, result.id_map
                )
                matched_title, matched_time = _lookup_matched_event(
                    event.existing_event_id, result.event_meta
                )
                result.events_synced.append(
                    EventSyncResult(
                        event=event,
                        action_taken=sync_result["action_taken"],
                        calendar_event_id=sync_result.get("calendar_event_id"),
                        success=True,
                        matched_event_title=matched_title,
                        matched_event_time=matched_time,
                    )
                )
            except Exception as exc:
                logger.error(
                    "Failed to sync event '%s': %s",
                    event.title,
                    exc,
                )
                result.events_failed.append(
                    FailedEvent(event=event, error=str(exc))
                )

    logger.info(
        "Stage 3 complete: %d synced, %d failed",
        len(result.events_synced),
        len(result.events_failed),
    )

    # ------------------------------------------------------------------
    # Stage 4: Summary
    # ------------------------------------------------------------------
    result.duration_seconds = time.monotonic() - start_time
    logger.info("Pipeline complete in %.1fs", result.duration_seconds)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _lookup_matched_event(
    existing_event_id: int | None,
    event_meta: dict[int, dict[str, str]],
) -> tuple[str | None, str | None]:
    """Look up matched event title and start time from event metadata.

    Args:
        existing_event_id: The remapped integer ID from the LLM, or ``None``.
        event_meta: Mapping from integer IDs to metadata dicts with
            ``title`` and ``start_time`` keys.

    Returns:
        A tuple of ``(matched_title, matched_start_time)``, both ``None``
        if the event ID is not found or not provided.
    """
    if existing_event_id is None or not event_meta:
        return None, None

    meta = event_meta.get(existing_event_id)
    if meta is None:
        return None, None

    return meta.get("title"), meta.get("start_time")


def _build_transcript_text(utterances: list) -> str:
    """Reconstruct transcript text from parsed utterances.

    Args:
        utterances: List of :class:`~cal_ai.models.transcript.Utterance`.

    Returns:
        Formatted transcript string with ``[Speaker]: text`` lines.
    """
    lines = [f"[{u.speaker}]: {u.text}" for u in utterances]
    return "\n".join(lines)


def _build_calendar_client(settings) -> GoogleCalendarClient:
    """Build and return a configured Google Calendar client.

    Args:
        settings: Application :class:`~cal_ai.config.Settings`.

    Returns:
        An initialised :class:`GoogleCalendarClient`.
    """
    creds = get_calendar_credentials(
        credentials_path=Path("credentials.json"),
        token_path=Path("token.json"),
    )
    return GoogleCalendarClient(
        credentials=creds,
        timezone=settings.timezone,
        owner_email=settings.google_account_email,
    )


def _validate_events(gemini, extraction, now):
    """Validate extracted events and return them as a list for index-based correlation.

    The returned list preserves the same order as the input
    ``extraction.events`` so that ``validated[i]`` corresponds to
    ``extraction.events[i]``.  Events that fail validation are skipped
    by :meth:`GeminiClient.validate_events` (logged and omitted), so the
    returned list may be shorter than the input.

    Args:
        gemini: The :class:`GeminiClient` instance.
        extraction: The :class:`ExtractionResult` from the LLM.
        now: Current datetime for validation.

    Returns:
        A list of :class:`ValidatedEvent` instances in extraction order.
    """
    return gemini.validate_events(extraction, current_datetime=now)


def _sync_single_event(
    event: ValidatedEvent,
    client: GoogleCalendarClient,
    id_map: dict[int, str] | None = None,
) -> dict:
    """Sync a single validated event to Google Calendar.

    Dispatches to the appropriate client method based on the event's
    ``action`` field and the presence of ``existing_event_id``.

    When ``existing_event_id`` is set and found in *id_map*, direct
    event-ID API calls are used (``update_event`` / ``delete_event``).
    On HTTP 404 (``CalendarNotFoundError``):

    - **update** falls back to ``create_event`` (the original event was
      deleted since the context was fetched).
    - **delete** is treated as success (idempotent -- the event is already
      gone).

    When ``existing_event_id`` is absent, the search-based methods
    (``find_and_update_event`` / ``find_and_delete_event``) are used
    as before.

    Args:
        event: The validated event to sync.
        client: The Google Calendar client.
        id_map: Mapping from integer IDs (used in LLM context) to
            Google Calendar event UUIDs.  May be ``None`` or empty.

    Returns:
        A dict with ``action_taken`` and optional ``calendar_event_id``.

    Raises:
        ValueError: If the event action is unknown.
        Exception: Any error from the calendar client.
    """
    action = event.action
    id_map = id_map or {}

    # Resolve the real Google Calendar event ID from the integer mapping.
    real_id: str | None = None
    if event.existing_event_id is not None:
        real_id = id_map.get(event.existing_event_id)
        if real_id is not None:
            logger.info(
                "Resolved existing_event_id %d -> %s for '%s'",
                event.existing_event_id,
                real_id,
                event.title,
            )
        else:
            logger.warning(
                "existing_event_id %d not found in id_map for '%s', "
                "falling back to search-based method",
                event.existing_event_id,
                event.title,
            )

    if action == "create":
        response = client.create_event(event)
        if response is None:
            return {"action_taken": "skipped_duplicate", "calendar_event_id": None}
        return {
            "action_taken": "created",
            "calendar_event_id": response.get("id"),
        }
    elif action == "update":
        if real_id is not None:
            return _update_by_id(event, client, real_id)
        # No existing_event_id -- fall back to search-based update.
        response = client.find_and_update_event(event)
        if response is None:
            return {"action_taken": "skipped_no_match", "calendar_event_id": None}
        return {
            "action_taken": "updated",
            "calendar_event_id": response.get("id"),
        }
    elif action == "delete":
        if real_id is not None:
            return _delete_by_id(event, client, real_id)
        # No existing_event_id -- fall back to search-based delete.
        deleted = client.find_and_delete_event(event)
        if not deleted:
            return {"action_taken": "skipped_no_match", "calendar_event_id": None}
        return {"action_taken": "deleted", "calendar_event_id": None}
    else:
        raise ValueError(f"Unknown event action: {action!r}")


def _update_by_id(
    event: ValidatedEvent,
    client: GoogleCalendarClient,
    real_id: str,
) -> dict:
    """Update an event by its Google Calendar ID with 404 fallback.

    On ``CalendarNotFoundError`` (the event was deleted since the context
    was fetched), falls back to ``create_event`` and logs a warning.

    Args:
        event: The validated event with updated data.
        client: The Google Calendar client.
        real_id: The real Google Calendar event UUID.

    Returns:
        A dict with ``action_taken`` and ``calendar_event_id``.
    """
    try:
        response = client.update_event(real_id, event)
        return {
            "action_taken": "updated",
            "calendar_event_id": response.get("id"),
        }
    except CalendarNotFoundError:
        logger.warning(
            "Event '%s' (id=%s) not found for update (404), "
            "falling back to create",
            event.title,
            real_id,
        )
        response = client.create_event(event)
        if response is None:
            return {"action_taken": "skipped_duplicate", "calendar_event_id": None}
        return {
            "action_taken": "created",
            "calendar_event_id": response.get("id"),
        }


def _delete_by_id(
    event: ValidatedEvent,
    client: GoogleCalendarClient,
    real_id: str,
) -> dict:
    """Delete an event by its Google Calendar ID with 404 fallback.

    On ``CalendarNotFoundError`` (the event is already gone), treats
    the operation as successful (idempotent) and logs a warning.

    Args:
        event: The validated event being deleted.
        client: The Google Calendar client.
        real_id: The real Google Calendar event UUID.

    Returns:
        A dict with ``action_taken`` and ``calendar_event_id``.
    """
    try:
        client.delete_event(real_id)
        return {"action_taken": "deleted", "calendar_event_id": None}
    except CalendarNotFoundError:
        logger.warning(
            "Event '%s' (id=%s) not found for delete (404), "
            "treating as already deleted (idempotent)",
            event.title,
            real_id,
        )
        return {"action_taken": "deleted", "calendar_event_id": None}
