"""Demo output formatter for the conversation-to-calendar pipeline.

Renders a :class:`~cal_ai.pipeline.PipelineResult` as structured console
output showing the full reasoning chain: transcript metadata, extracted
events with AI reasoning, calendar operations, and a summary.

The primary entry point is :func:`format_pipeline_result`, which returns
the formatted string.  :func:`print_pipeline_result` is a convenience
wrapper that writes directly to stdout.
"""

from __future__ import annotations

import sys
from datetime import datetime

from cal_ai.pipeline import EventSyncResult, FailedEvent, PipelineResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BANNER_WIDTH = 60
_SEPARATOR = "=" * _BANNER_WIDTH


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_pipeline_result(result: PipelineResult) -> str:
    """Render a :class:`PipelineResult` as structured demo output.

    The output includes four labelled stages and a summary section:

    - **Stage 1** -- Transcript metadata (file, speakers, utterance count).
    - **Stage 2** -- Extracted events with details, AI reasoning, and
      assumptions.
    - **Stage 3** -- Calendar operations with action markers.
    - **Summary** -- Counts, warnings, and pipeline duration.

    Args:
        result: The pipeline result to format.

    Returns:
        A multi-line string ready for console display.
    """
    lines: list[str] = []

    _append_banner(lines)
    _append_stage1(lines, result)
    _append_stage2(lines, result)
    _append_stage3(lines, result)
    _append_summary(lines, result)
    lines.append(_SEPARATOR)

    return "\n".join(lines)


def print_pipeline_result(result: PipelineResult) -> None:
    """Format and print a :class:`PipelineResult` to stdout.

    Args:
        result: The pipeline result to display.
    """
    sys.stdout.write(format_pipeline_result(result) + "\n")


# ---------------------------------------------------------------------------
# Internal formatters
# ---------------------------------------------------------------------------


def _append_banner(lines: list[str]) -> None:
    """Append the application banner."""
    lines.append(_SEPARATOR)
    lines.append("  CONVERSATION-TO-CALENDAR AI")
    lines.append(_SEPARATOR)


def _append_stage1(lines: list[str], result: PipelineResult) -> None:
    """Append Stage 1: Transcript Loaded."""
    lines.append("")
    lines.append("--- STAGE 1: Transcript Loaded ---")
    lines.append(f"  File: {result.transcript_path}")
    speakers = ", ".join(result.speakers_found) if result.speakers_found else "none"
    lines.append(f"  Speakers: {speakers}")
    lines.append(f"  Utterances: {result.utterance_count} lines")


def _append_stage2(lines: list[str], result: PipelineResult) -> None:
    """Append Stage 2: Events Extracted."""
    lines.append("")
    lines.append("--- STAGE 2: Events Extracted ---")

    if not result.events_extracted:
        lines.append("  No calendar events detected in this conversation.")
        return

    lines.append(f"  Found {len(result.events_extracted)} event(s)")

    for idx, event in enumerate(result.events_extracted, start=1):
        lines.append("")
        lines.append(f"  Event {idx}: {event.title}")
        lines.append(f"    When: {_format_event_time(event.start_time, event.end_time)}")

        if event.location:
            lines.append(f"    Where: {event.location}")

        if event.attendees:
            lines.append(f"    Who: {', '.join(event.attendees)}")

        lines.append(f"    Action: {event.action}")
        lines.append(f"    Confidence: {event.confidence}")
        lines.append(f"    AI Reasoning: {event.reasoning}")

        if event.assumptions:
            lines.append(f"    Assumptions: {'; '.join(event.assumptions)}")


def _append_stage3(lines: list[str], result: PipelineResult) -> None:
    """Append Stage 3: Calendar Operations."""
    lines.append("")
    lines.append("--- STAGE 3: Calendar Operations ---")

    if not result.events_extracted:
        lines.append("  No operations to perform.")
        return

    for sync in result.events_synced:
        _append_sync_result(lines, sync, result.dry_run)

    for failed in result.events_failed:
        _append_failed_event(lines, failed)


def _append_sync_result(
    lines: list[str],
    sync: EventSyncResult,
    dry_run: bool,
) -> None:
    """Append sync result lines, including matched event info for updates/deletes."""
    matched_info = _format_matched_info(sync)

    if dry_run:
        action_label = _dry_run_label(sync.action_taken)
        lines.append(f'  [DRY RUN] {action_label} "{sync.event.title}"')
        if matched_info:
            lines.append(f"    {matched_info}")
    else:
        tag = _action_tag(sync.action_taken)
        suffix = f" (ID: {sync.calendar_event_id})" if sync.calendar_event_id else ""
        status_word = _action_status_word(sync.action_taken)
        lines.append(f'  [{tag}] "{sync.event.title}" -> {status_word}{suffix}')
        if matched_info:
            lines.append(f"    {matched_info}")


def _append_failed_event(lines: list[str], failed: FailedEvent) -> None:
    """Append a failed event with its error message."""
    lines.append(f'  [FAILED] "{failed.event.title}" -> Error: {failed.error}')


def _append_summary(lines: list[str], result: PipelineResult) -> None:
    """Append the summary section."""
    lines.append("")
    lines.append("--- SUMMARY ---")
    lines.append(f"  Events extracted: {len(result.events_extracted)}")
    lines.append(f"  Successfully synced: {len(result.events_synced)}")
    lines.append(f"  Failed: {len(result.events_failed)}")
    lines.append(f"  Warnings: {len(result.warnings)}")

    if result.warnings:
        for warning in result.warnings:
            lines.append(f"    - {warning}")

    lines.append(f"  Pipeline duration: {result.duration_seconds:.1f}s")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_event_time(start_time: str, end_time: str | None) -> str:
    """Format event start and end times for display.

    Attempts to parse ISO 8601 strings into human-readable form.
    Falls back to the raw string if parsing fails.

    Args:
        start_time: ISO 8601 start datetime string.
        end_time: ISO 8601 end datetime string, or ``None``.

    Returns:
        A formatted time range string.
    """
    try:
        start_dt = datetime.fromisoformat(start_time)
        start_str = start_dt.strftime("%A %Y-%m-%d, %I:%M %p")
    except (ValueError, TypeError):
        start_str = start_time

    if end_time is None:
        return start_str

    try:
        end_dt = datetime.fromisoformat(end_time)
        # If same day, show only the time for the end.
        if (
            isinstance(start_str, str) and start_str != start_time  # successfully parsed
        ):
            start_dt_parsed = datetime.fromisoformat(start_time)
            if start_dt_parsed.date() == end_dt.date():
                end_str = end_dt.strftime("%I:%M %p")
            else:
                end_str = end_dt.strftime("%A %Y-%m-%d, %I:%M %p")
        else:
            end_str = end_dt.strftime("%A %Y-%m-%d, %I:%M %p")
    except (ValueError, TypeError):
        end_str = end_time

    return f"{start_str} - {end_str}"


def _action_tag(action_taken: str) -> str:
    """Convert an action_taken string to an uppercase display tag.

    Args:
        action_taken: The action performed (e.g. ``"created"``).

    Returns:
        Uppercase tag (e.g. ``"CREATE"``).
    """
    mapping = {
        "created": "CREATE",
        "updated": "UPDATE",
        "deleted": "DELETE",
        "skipped_duplicate": "SKIP",
        "skipped_no_match": "SKIP",
    }
    return mapping.get(action_taken, action_taken.upper())


def _action_status_word(action_taken: str) -> str:
    """Convert an action_taken string to a past-tense status word.

    Args:
        action_taken: The action performed.

    Returns:
        Human-readable status (e.g. ``"Created"``).
    """
    mapping = {
        "created": "Created",
        "updated": "Updated",
        "deleted": "Deleted",
        "skipped_duplicate": "Skipped (duplicate)",
        "skipped_no_match": "Skipped (no match)",
    }
    return mapping.get(action_taken, action_taken.title())


def _dry_run_label(action_taken: str) -> str:
    """Convert a dry-run action_taken to a descriptive label.

    Args:
        action_taken: The would-be action (e.g. ``"would_create"``).

    Returns:
        Label like ``"Would create"``.
    """
    mapping = {
        "would_create": "Would create",
        "would_update": "Would update",
        "would_delete": "Would delete",
    }
    return mapping.get(action_taken, action_taken.replace("_", " ").title())


def _format_matched_info(sync: EventSyncResult) -> str | None:
    """Build a matched-event info string for UPDATE and DELETE actions.

    For UPDATE actions, returns ``"Matched existing: <title> at <time>"``.
    For DELETE actions, returns ``"Removing: <title> at <time>"``.
    Returns ``None`` when no matched event info is available or the action
    is CREATE.

    Args:
        sync: The sync result to inspect.

    Returns:
        A descriptive string, or ``None`` if not applicable.
    """
    if sync.matched_event_title is None:
        return None

    time_str = _format_matched_time(sync.matched_event_time)
    title = sync.matched_event_title

    action = sync.action_taken
    if action in ("updated", "would_update"):
        return f"Matched existing: {title} at {time_str}"
    elif action in ("deleted", "would_delete"):
        return f"Removing: {title} at {time_str}"

    return None


def _format_matched_time(time_str: str | None) -> str:
    """Format a matched event's start time for display.

    Attempts to parse an ISO 8601 string into a human-readable form.
    Falls back to the raw string if parsing fails.

    Args:
        time_str: ISO 8601 datetime string, or ``None``.

    Returns:
        A formatted time string, or ``"unknown time"`` if ``None``.
    """
    if not time_str:
        return "unknown time"
    try:
        dt = datetime.fromisoformat(time_str)
        return dt.strftime("%A %Y-%m-%d, %I:%M %p")
    except (ValueError, TypeError):
        return time_str
