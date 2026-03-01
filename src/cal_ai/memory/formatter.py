"""Memory context formatter for LLM prompt injection.

Formats loaded memories into a text section suitable for inclusion in the
extraction system prompt.  Follows the ``CalendarContext`` pattern from
:mod:`cal_ai.calendar.context` -- the formatter is the single source of
truth for the memory section header and layout.

The formatter accepts any sequence of objects with ``category``, ``key``,
and ``value`` attributes (duck-typed), allowing both :class:`MemoryRecord`
(from the store) and test-specific entry types to be formatted without
conversion.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any


def format_memory_context(
    memories: Sequence[Any],
    owner_name: str,
) -> str:
    """Format memories into a prompt-injectable text section.

    Groups memories by category with bullet points under category
    subheadings.  Returns the **complete section** including the
    ``## Your Memory (about {owner_name})`` header.

    When *memories* is empty, returns ``""`` so that no memory section
    is emitted in the prompt (preserving byte-for-byte backward
    compatibility when there are no memories).

    Args:
        memories: Sequence of objects with ``category``, ``key``, and
            ``value`` attributes.  Both :class:`MemoryRecord` and
            test stubs satisfy this contract.
        owner_name: Display name of the calendar owner, used in the
            section header.

    Returns:
        The formatted memory section string, or ``""`` if *memories*
        is empty.
    """
    if not memories:
        return ""

    # Group by category, preserving insertion order within each group.
    grouped: dict[str, list[Any]] = defaultdict(list)
    for mem in memories:
        grouped[mem.category].append(mem)

    lines: list[str] = [f"## Your Memory (about {owner_name})", ""]

    for category, entries in grouped.items():
        lines.append(f"### {category.title()}")
        for entry in entries:
            lines.append(f"- **{entry.key}**: {entry.value}")
        lines.append("")

    return "\n".join(lines)
