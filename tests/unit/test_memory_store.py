"""Tests for the memory store (SQLite CRUD and schema creation)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from cal_ai.memory.models import MemoryRecord
from cal_ai.memory.store import MemoryStore

# ---------------------------------------------------------------------------
# Schema auto-creation
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Tests for automatic database and table creation."""

    def test_creates_db_file(self, tmp_path: Path) -> None:
        """MemoryStore creates the SQLite database file on init."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        store.close()

        assert db_path.exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """MemoryStore creates parent directories that do not exist."""
        db_path = tmp_path / "nested" / "deep" / "memory.db"
        store = MemoryStore(db_path)
        store.close()

        assert db_path.exists()
        assert db_path.parent.is_dir()

    def test_memories_table_exists(self, tmp_path: Path) -> None:
        """The memories table is created on init."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        store.close()

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_memory_log_table_exists(self, tmp_path: Path) -> None:
        """The memory_log table is created on init."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        store.close()

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_log'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_wal_journal_mode(self, tmp_path: Path) -> None:
        """WAL journal mode is enabled on the connection."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)

        # Query the journal mode from the store's connection.
        cursor = store._conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        store.close()

        assert mode == "wal"

    def test_idempotent_schema_creation(self, tmp_path: Path) -> None:
        """Opening the same DB file twice does not fail (CREATE IF NOT EXISTS)."""
        db_path = tmp_path / "memory.db"
        store1 = MemoryStore(db_path)
        store1.upsert("preferences", "test", "value")
        store1.close()

        store2 = MemoryStore(db_path)
        memories = store2.load_all()
        store2.close()

        assert len(memories) == 1


# ---------------------------------------------------------------------------
# load_all
# ---------------------------------------------------------------------------


class TestLoadAll:
    """Tests for MemoryStore.load_all()."""

    def test_load_all_empty(self, tmp_path: Path) -> None:
        """load_all returns an empty list when the store is empty."""
        store = MemoryStore(tmp_path / "memory.db")
        memories = store.load_all()
        store.close()

        assert memories == []

    def test_load_all_returns_memory_records(self, tmp_path: Path) -> None:
        """load_all returns a list of MemoryRecord instances."""
        store = MemoryStore(tmp_path / "memory.db")
        store.upsert("preferences", "morning_meetings", "Prefers before 11am")
        memories = store.load_all()
        store.close()

        assert len(memories) == 1
        assert isinstance(memories[0], MemoryRecord)

    def test_load_all_ordered_by_category_then_key(self, tmp_path: Path) -> None:
        """load_all returns memories ordered by category, then key."""
        store = MemoryStore(tmp_path / "memory.db")
        store.upsert("vocabulary", "quick sync", "15-minute meeting")
        store.upsert("people", "Bob", "Alice's manager")
        store.upsert("preferences", "morning_meetings", "Before 11am")
        store.upsert("people", "Alice", "The owner")

        memories = store.load_all()
        store.close()

        categories_keys = [(m.category, m.key) for m in memories]
        assert categories_keys == [
            ("people", "Alice"),
            ("people", "Bob"),
            ("preferences", "morning_meetings"),
            ("vocabulary", "quick sync"),
        ]

    def test_load_all_includes_all_fields(self, tmp_path: Path) -> None:
        """load_all returns records with all expected fields populated."""
        store = MemoryStore(tmp_path / "memory.db")
        store.upsert("preferences", "key1", "value1", "high")
        memories = store.load_all()
        store.close()

        mem = memories[0]
        assert mem.category == "preferences"
        assert mem.key == "key1"
        assert mem.value == "value1"
        assert mem.confidence == "high"
        assert mem.source_count == 1
        assert mem.created_at != ""
        assert mem.updated_at != ""
        assert mem.id > 0


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------


class TestUpsert:
    """Tests for MemoryStore.upsert()."""

    def test_upsert_new_record(self, tmp_path: Path) -> None:
        """Upserting a new (category, key) creates a new row."""
        store = MemoryStore(tmp_path / "memory.db")
        row_id = store.upsert("preferences", "meeting_time", "Mornings", "high")
        store.close()

        assert row_id > 0

    def test_upsert_returns_row_id(self, tmp_path: Path) -> None:
        """upsert returns the integer id of the inserted/updated row."""
        store = MemoryStore(tmp_path / "memory.db")
        row_id = store.upsert("preferences", "key1", "value1")
        store.close()

        assert isinstance(row_id, int)

    def test_upsert_existing_updates_value(self, tmp_path: Path) -> None:
        """Upserting an existing (category, key) updates the value."""
        store = MemoryStore(tmp_path / "memory.db")
        store.upsert("people", "Bob", "Manager")
        store.upsert("people", "Bob", "Former manager")

        memories = store.load_all()
        store.close()

        assert len(memories) == 1
        assert memories[0].value == "Former manager"

    def test_upsert_existing_updates_confidence(self, tmp_path: Path) -> None:
        """Upserting an existing record updates the confidence level."""
        store = MemoryStore(tmp_path / "memory.db")
        store.upsert("people", "Bob", "Manager", "low")
        store.upsert("people", "Bob", "Manager", "high")

        memories = store.load_all()
        store.close()

        assert memories[0].confidence == "high"

    def test_upsert_existing_increments_source_count(self, tmp_path: Path) -> None:
        """Each upsert on the same (category, key) increments source_count."""
        store = MemoryStore(tmp_path / "memory.db")
        store.upsert("vocabulary", "standup", "15 min")
        store.upsert("vocabulary", "standup", "15 min daily")
        store.upsert("vocabulary", "standup", "15 min daily standup")

        memories = store.load_all()
        store.close()

        assert memories[0].source_count == 3

    def test_upsert_existing_updates_timestamp(self, tmp_path: Path) -> None:
        """Upserting updates the updated_at timestamp."""
        store = MemoryStore(tmp_path / "memory.db")
        store.upsert("preferences", "key1", "value1")
        first = store.load_all()[0]

        store.upsert("preferences", "key1", "value2")
        second = store.load_all()[0]
        store.close()

        assert second.updated_at >= first.updated_at

    def test_upsert_default_confidence_is_medium(self, tmp_path: Path) -> None:
        """Default confidence is 'medium' when not specified."""
        store = MemoryStore(tmp_path / "memory.db")
        store.upsert("preferences", "key1", "value1")
        memories = store.load_all()
        store.close()

        assert memories[0].confidence == "medium"

    def test_upsert_different_keys_same_category(self, tmp_path: Path) -> None:
        """Different keys in the same category create separate rows."""
        store = MemoryStore(tmp_path / "memory.db")
        store.upsert("people", "Bob", "Manager")
        store.upsert("people", "Carol", "Designer")

        memories = store.load_all()
        store.close()

        assert len(memories) == 2

    def test_upsert_same_key_different_category(self, tmp_path: Path) -> None:
        """Same key in different categories creates separate rows."""
        store = MemoryStore(tmp_path / "memory.db")
        store.upsert("people", "standup", "Daily standup team")
        store.upsert("vocabulary", "standup", "15 min meeting")

        memories = store.load_all()
        store.close()

        assert len(memories) == 2


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDelete:
    """Tests for MemoryStore.delete()."""

    def test_delete_existing(self, tmp_path: Path) -> None:
        """Deleting an existing memory removes it from the store."""
        store = MemoryStore(tmp_path / "memory.db")
        row_id = store.upsert("preferences", "key1", "value1")

        result = store.delete(row_id)
        memories = store.load_all()
        store.close()

        assert result is True
        assert memories == []

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        """Deleting a non-existent id returns False."""
        store = MemoryStore(tmp_path / "memory.db")
        result = store.delete(999)
        store.close()

        assert result is False

    def test_delete_only_removes_target(self, tmp_path: Path) -> None:
        """Deleting one memory does not affect others."""
        store = MemoryStore(tmp_path / "memory.db")
        id1 = store.upsert("people", "Bob", "Manager")
        store.upsert("people", "Carol", "Designer")

        store.delete(id1)
        memories = store.load_all()
        store.close()

        assert len(memories) == 1
        assert memories[0].key == "Carol"


# ---------------------------------------------------------------------------
# log_action
# ---------------------------------------------------------------------------


class TestLogAction:
    """Tests for MemoryStore.log_action()."""

    def test_log_action_returns_id(self, tmp_path: Path) -> None:
        """log_action returns the auto-incremented log entry id."""
        store = MemoryStore(tmp_path / "memory.db")
        log_id = store.log_action(
            action="ADD",
            memory_id=1,
            category="people",
            key="Bob",
            old_value=None,
            new_value="Manager",
            transcript="test.txt",
        )
        store.close()

        assert isinstance(log_id, int)
        assert log_id > 0

    def test_log_action_stores_category_key_snapshots(self, tmp_path: Path) -> None:
        """log_action stores category and key snapshots for traceability."""
        store = MemoryStore(tmp_path / "memory.db")
        store.log_action(
            action="UPDATE",
            memory_id=42,
            category="preferences",
            key="morning_meetings",
            old_value="Before 11am",
            new_value="Before 10am",
            transcript="chat.txt",
        )

        # Read log directly from SQLite.
        cursor = store._conn.execute(
            "SELECT memory_id, category, key, action, old_value, new_value, transcript "
            "FROM memory_log"
        )
        row = cursor.fetchone()
        store.close()

        assert row["memory_id"] == 42
        assert row["category"] == "preferences"
        assert row["key"] == "morning_meetings"
        assert row["action"] == "UPDATE"
        assert row["old_value"] == "Before 11am"
        assert row["new_value"] == "Before 10am"
        assert row["transcript"] == "chat.txt"

    def test_log_action_no_fk_constraint(self, tmp_path: Path) -> None:
        """memory_log.memory_id is not an enforced FK -- can reference deleted rows."""
        store = MemoryStore(tmp_path / "memory.db")

        # Insert and delete a memory, then log with the deleted id.
        row_id = store.upsert("people", "Bob", "Manager")
        store.delete(row_id)

        # This should NOT raise even though the memory is deleted.
        log_id = store.log_action(
            action="DELETE",
            memory_id=row_id,
            category="people",
            key="Bob",
            old_value="Manager",
            new_value=None,
        )
        store.close()

        assert log_id > 0

    def test_log_action_with_none_transcript(self, tmp_path: Path) -> None:
        """log_action accepts None for the transcript parameter."""
        store = MemoryStore(tmp_path / "memory.db")
        log_id = store.log_action(
            action="ADD",
            memory_id=1,
            category="vocabulary",
            key="standup",
            old_value=None,
            new_value="15 min meeting",
        )
        store.close()

        assert log_id > 0

    def test_log_action_preserves_audit_after_memory_delete(self, tmp_path: Path) -> None:
        """Deleting a memory does not remove its audit log entries."""
        store = MemoryStore(tmp_path / "memory.db")
        row_id = store.upsert("people", "Bob", "Manager")
        store.log_action(
            action="ADD",
            memory_id=row_id,
            category="people",
            key="Bob",
            old_value=None,
            new_value="Manager",
        )

        # Delete the memory.
        store.delete(row_id)

        # Audit log should still have the entry.
        cursor = store._conn.execute("SELECT COUNT(*) FROM memory_log")
        count = cursor.fetchone()[0]
        store.close()

        assert count == 1


# ---------------------------------------------------------------------------
# Memory log schema columns
# ---------------------------------------------------------------------------


class TestMemoryLogSchema:
    """Tests verifying the memory_log table schema."""

    def test_memory_log_has_category_column(self, tmp_path: Path) -> None:
        """memory_log table includes a category column."""
        store = MemoryStore(tmp_path / "memory.db")
        cursor = store._conn.execute("PRAGMA table_info(memory_log)")
        columns = {row["name"] for row in cursor.fetchall()}
        store.close()

        assert "category" in columns

    def test_memory_log_has_key_column(self, tmp_path: Path) -> None:
        """memory_log table includes a key column."""
        store = MemoryStore(tmp_path / "memory.db")
        cursor = store._conn.execute("PRAGMA table_info(memory_log)")
        columns = {row["name"] for row in cursor.fetchall()}
        store.close()

        assert "key" in columns
