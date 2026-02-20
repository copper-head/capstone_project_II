"""Loader utilities for regression test samples and sidecar files.

Discovers ``.txt`` transcript files paired with ``.expected.json`` sidecars
and converts sidecar calendar context into the pipeline's
:class:`~cal_ai.calendar.context.CalendarContext` dataclass.
"""

from __future__ import annotations

import json
from pathlib import Path

from cal_ai.calendar.context import CalendarContext

from .schema import SidecarSpec


def discover_samples(base_dir: str | Path) -> list[tuple[Path, SidecarSpec]]:
    """Discover sample transcripts paired with sidecar JSON files.

    Recursively globs ``**/*.txt`` under *base_dir*, pairs each with a
    sibling ``.expected.json`` file, and returns validated
    ``(txt_path, sidecar)`` tuples.  Samples without a matching sidecar
    are silently skipped.

    Args:
        base_dir: Root directory to search for samples.

    Returns:
        A sorted list of ``(txt_path, SidecarSpec)`` tuples, ordered by
        the transcript file path for deterministic test ordering.
    """
    base = Path(base_dir)
    results: list[tuple[Path, SidecarSpec]] = []

    for txt_path in sorted(base.rglob("*.txt")):
        sidecar_path = txt_path.with_suffix(".expected.json")
        if sidecar_path.exists():
            sidecar = load_sidecar(sidecar_path)
            results.append((txt_path, sidecar))

    return results


def load_sidecar(json_path: str | Path) -> SidecarSpec:
    """Load and validate a sidecar JSON file.

    Args:
        json_path: Path to the ``.expected.json`` file.

    Returns:
        A validated :class:`SidecarSpec` instance.

    Raises:
        pydantic.ValidationError: If the JSON does not match the schema.
        json.JSONDecodeError: If the file is not valid JSON.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return SidecarSpec.model_validate(data)


def build_calendar_context(sidecar: SidecarSpec) -> CalendarContext:
    """Convert a sidecar's calendar context into a CalendarContext.

    Builds the same structure that :func:`~cal_ai.calendar.context.fetch_calendar_context`
    returns, but from static sidecar data rather than a live API call.
    Events are assigned sequential integer IDs starting at 1.

    The ``events_text`` uses the same format as the production code:
    ``[ID] Title | Start - End | Location``

    Args:
        sidecar: A validated sidecar spec.

    Returns:
        A :class:`CalendarContext` populated from the sidecar's
        ``calendar_context`` entries.  If the sidecar has no calendar
        context, an empty ``CalendarContext`` is returned.
    """
    if not sidecar.calendar_context:
        return CalendarContext()

    id_map: dict[int, str] = {}
    event_meta: dict[int, dict[str, str]] = {}
    lines: list[str] = []

    for i, event in enumerate(sidecar.calendar_context, start=1):
        id_map[i] = event.id
        event_meta[i] = {
            "title": event.summary,
            "start_time": event.start,
        }

        parts = [f"[{i}] {event.summary}", f"{event.start} - {event.end}"]
        if event.location:
            parts.append(event.location)
        lines.append(" | ".join(parts))

    return CalendarContext(
        events_text="\n".join(lines),
        id_map=id_map,
        event_count=len(sidecar.calendar_context),
        event_meta=event_meta,
    )
