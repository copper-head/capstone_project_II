"""Unit tests for the memory context formatter.

Tests cover:
- Empty memories return empty string
- Single memory produces header + category + bullet
- Multiple memories grouped by category
- Multiple categories each get subheadings
- Owner name appears in header
- Duck-typed input (objects with category/key/value attributes)
- Ordering: categories appear in insertion order
"""

from __future__ import annotations

from types import SimpleNamespace

from cal_ai.memory.formatter import format_memory_context
from cal_ai.memory.models import MemoryRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_memory(
    category: str = "preferences",
    key: str = "meeting_time",
    value: str = "Alice prefers morning meetings",
    **kwargs,
) -> MemoryRecord:
    """Build a stub MemoryRecord."""
    return MemoryRecord(
        id=kwargs.get("id", 1),
        category=category,
        key=key,
        value=value,
        confidence=kwargs.get("confidence", "medium"),
        source_count=kwargs.get("source_count", 1),
        created_at=kwargs.get("created_at", "2026-01-01T00:00:00"),
        updated_at=kwargs.get("updated_at", "2026-01-01T00:00:00"),
    )


def _make_duck_entry(
    category: str = "preferences",
    key: str = "meeting_time",
    value: str = "Prefers mornings",
) -> SimpleNamespace:
    """Build a duck-typed object with category/key/value attributes."""
    return SimpleNamespace(category=category, key=key, value=value)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFormatMemoryContext:
    """Tests for format_memory_context()."""

    def test_empty_memories_returns_empty_string(self) -> None:
        """No memories -> empty string (no header emitted)."""
        result = format_memory_context([], "Alice")

        assert result == ""

    def test_single_memory_produces_header_and_bullet(self) -> None:
        """One memory -> header + category subheading + bullet point."""
        memories = [_make_memory()]
        result = format_memory_context(memories, "Alice")

        assert "## Your Memory (about Alice)" in result
        assert "### Preferences" in result
        assert "- **meeting_time**: Alice prefers morning meetings" in result

    def test_multiple_memories_same_category(self) -> None:
        """Two memories in the same category -> both under one subheading."""
        memories = [
            _make_memory(key="meeting_time", value="Prefers mornings"),
            _make_memory(id=2, key="lunch_break", value="Noon-1pm always blocked"),
        ]
        result = format_memory_context(memories, "Alice")

        # Only one category heading
        assert result.count("### Preferences") == 1
        # Both bullet points present
        assert "- **meeting_time**:" in result
        assert "- **lunch_break**:" in result

    def test_multiple_categories(self) -> None:
        """Memories in different categories -> separate subheadings."""
        memories = [
            _make_memory(category="preferences", key="time", value="mornings"),
            _make_memory(id=2, category="people", key="Bob", value="Alice's manager"),
            _make_memory(id=3, category="vocabulary", key="sync", value="15 min meeting"),
        ]
        result = format_memory_context(memories, "Alice")

        assert "### Preferences" in result
        assert "### People" in result
        assert "### Vocabulary" in result

    def test_owner_name_in_header(self) -> None:
        """Header includes the owner name."""
        memories = [_make_memory()]
        result = format_memory_context(memories, "Bob")

        assert "## Your Memory (about Bob)" in result

    def test_duck_typed_input_accepted(self) -> None:
        """Objects with category/key/value attributes (not MemoryRecord) work."""
        entries = [
            _make_duck_entry("preferences", "time", "Mornings"),
            _make_duck_entry("people", "Carol", "Colleague"),
        ]
        result = format_memory_context(entries, "Alice")

        assert "## Your Memory (about Alice)" in result
        assert "- **time**: Mornings" in result
        assert "- **Carol**: Colleague" in result

    def test_categories_preserve_insertion_order(self) -> None:
        """Categories appear in the order they first occur in the input."""
        memories = [
            _make_memory(id=1, category="people", key="Bob", value="Manager"),
            _make_memory(id=2, category="preferences", key="time", value="AM"),
        ]
        result = format_memory_context(memories, "Alice")

        people_pos = result.index("### People")
        preferences_pos = result.index("### Preferences")
        assert people_pos < preferences_pos, (
            "Categories should appear in insertion order (people before preferences)"
        )

    def test_category_title_case(self) -> None:
        """Category subheadings use title case."""
        memories = [
            _make_memory(category="vocabulary", key="sync", value="15 min"),
        ]
        result = format_memory_context(memories, "Alice")

        assert "### Vocabulary" in result
