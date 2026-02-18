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
    """

    event: ExtractedEvent
    action_taken: str
    calendar_event_id: str | None = None
    success: bool = True
    error: str | None = None


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
    # Stage 2: Extract Events
    # ------------------------------------------------------------------
    logger.info("Stage 2: Extracting events via LLM")

    settings = load_settings()
    gemini = GeminiClient(api_key=settings.gemini_api_key)

    # Build the transcript text for the LLM from the parsed utterances.
    transcript_text = _build_transcript_text(parse_result.utterances)

    try:
        extraction = gemini.extract_events(
            transcript_text=transcript_text,
            owner_name=owner,
            current_datetime=now,
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
            result.events_synced.append(
                EventSyncResult(
                    event=event,
                    action_taken=f"would_{event.action}",
                    success=True,
                )
            )
    else:
        logger.info(
            "Stage 3: Syncing %d event(s) to Google Calendar",
            len(result.events_extracted),
        )

        client = _build_calendar_client(settings)

        # Validate extracted events to get parsed datetimes for the calendar client.
        validated_map = _validate_events(gemini, extraction, now)

        for event in result.events_extracted:
            validated = validated_map.get(event.title)
            if validated is None:
                result.events_failed.append(
                    FailedEvent(event=event, error="Event validation failed")
                )
                continue

            try:
                sync_result = _sync_single_event(validated, client)
                result.events_synced.append(
                    EventSyncResult(
                        event=event,
                        action_taken=sync_result["action_taken"],
                        calendar_event_id=sync_result.get("calendar_event_id"),
                        success=True,
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
    """Validate extracted events and return a title-to-validated mapping.

    Args:
        gemini: The :class:`GeminiClient` instance.
        extraction: The :class:`ExtractionResult` from the LLM.
        now: Current datetime for validation.

    Returns:
        A dict mapping event titles to :class:`ValidatedEvent` instances.
    """
    validated_list = gemini.validate_events(extraction, current_datetime=now)
    return {v.title: v for v in validated_list}


def _sync_single_event(
    event: ValidatedEvent,
    client: GoogleCalendarClient,
) -> dict:
    """Sync a single validated event to Google Calendar.

    Dispatches to the appropriate client method based on the event's
    ``action`` field.

    Args:
        event: The validated event to sync.
        client: The Google Calendar client.

    Returns:
        A dict with ``action_taken`` and optional ``calendar_event_id``.

    Raises:
        ValueError: If the event action is unknown.
        Exception: Any error from the calendar client.
    """
    action = event.action

    if action == "create":
        response = client.create_event(event)
        if response is None:
            return {"action_taken": "skipped_duplicate", "calendar_event_id": None}
        return {
            "action_taken": "created",
            "calendar_event_id": response.get("id"),
        }
    elif action == "update":
        response = client.find_and_update_event(event)
        if response is None:
            return {"action_taken": "skipped_no_match", "calendar_event_id": None}
        return {
            "action_taken": "updated",
            "calendar_event_id": response.get("id"),
        }
    elif action == "delete":
        deleted = client.find_and_delete_event(event)
        if not deleted:
            return {"action_taken": "skipped_no_match", "calendar_event_id": None}
        return {"action_taken": "deleted", "calendar_event_id": None}
    else:
        raise ValueError(f"Unknown event action: {action!r}")
