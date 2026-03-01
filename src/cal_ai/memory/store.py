"""SQLite-backed memory store for the cal-ai memory system.

Provides persistent storage for scheduling-relevant facts about the owner
and the people they interact with.  Uses SQLite with WAL journal mode for
safe concurrent reads.

The store manages two tables:

- ``memories`` -- current memory facts with UPSERT semantics.
- ``memory_log`` -- append-only audit trail of all memory operations.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from cal_ai.memory.models import MemoryRecord

# ---------------------------------------------------------------------------
# SQL DDL
# ---------------------------------------------------------------------------

_CREATE_MEMORIES_TABLE = """\
CREATE TABLE IF NOT EXISTS memories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category     TEXT NOT NULL,
    key          TEXT NOT NULL,
    value        TEXT NOT NULL,
    confidence   TEXT DEFAULT 'medium',
    source_count INTEGER DEFAULT 1,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE(category, key)
);
"""

_CREATE_MEMORY_LOG_TABLE = """\
CREATE TABLE IF NOT EXISTS memory_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id    INTEGER,
    category     TEXT,
    key          TEXT,
    action       TEXT NOT NULL,
    old_value    TEXT,
    new_value    TEXT,
    transcript   TEXT,
    created_at   TEXT NOT NULL
);
"""


class MemoryStore:
    """SQLite-backed store for persistent memory facts.

    On instantiation, creates the parent directory (if needed), opens (or
    creates) the SQLite database file, enables WAL journal mode, and
    ensures both tables exist.

    Args:
        db_path: Path to the SQLite database file.  Parent directories
            are created automatically.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_MEMORIES_TABLE)
        self._conn.execute(_CREATE_MEMORY_LOG_TABLE)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load_all(self) -> list[MemoryRecord]:
        """Load all memories ordered by category, then key.

        Returns:
            List of :class:`MemoryRecord` instances.  Empty list when
            the store contains no memories.
        """
        cursor = self._conn.execute(
            "SELECT id, category, key, value, confidence, source_count, "
            "created_at, updated_at FROM memories ORDER BY category, key"
        )
        return [MemoryRecord(**dict(row)) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert(
        self,
        category: str,
        key: str,
        value: str,
        confidence: str = "medium",
    ) -> int:
        """Insert a new memory or update an existing one.

        Uses ``INSERT ... ON CONFLICT(category, key) DO UPDATE`` to handle
        both cases in a single statement.  On conflict the value and
        confidence are replaced, ``source_count`` is incremented, and
        ``updated_at`` is refreshed.

        Args:
            category: Memory category.
            key: Lookup identifier within the category.
            value: Memory content.
            confidence: Confidence level (``"low"``, ``"medium"``, ``"high"``).

        Returns:
            The ``id`` of the upserted row.
        """
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """\
            INSERT INTO memories
                (category, key, value, confidence, source_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(category, key) DO UPDATE SET
                value = excluded.value,
                confidence = excluded.confidence,
                source_count = source_count + 1,
                updated_at = excluded.updated_at
            """,
            (category, key, value, confidence, now, now),
        )
        self._conn.commit()

        # Always SELECT to get the correct row ID.  cursor.lastrowid is
        # unreliable on the UPDATE path of an UPSERT (it may hold a stale
        # value from a prior INSERT on the same connection).
        row = self._conn.execute(
            "SELECT id FROM memories WHERE category = ? AND key = ?",
            (category, key),
        ).fetchone()
        return row["id"]  # type: ignore[index]

    def delete(self, memory_id: int) -> bool:
        """Delete a memory by its primary key.

        Args:
            memory_id: The ``id`` of the memory row to delete.

        Returns:
            ``True`` if a row was deleted, ``False`` if the id was not found.
        """
        cursor = self._conn.execute(
            "DELETE FROM memories WHERE id = ?",
            (memory_id,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def log_action(
        self,
        action: str,
        memory_id: int | None,
        category: str | None,
        key: str | None,
        old_value: str | None,
        new_value: str | None,
        transcript: str | None = None,
    ) -> int:
        """Write an entry to the ``memory_log`` audit trail.

        Stores category and key snapshots alongside the memory_id so the
        audit trail survives memory deletion.

        Args:
            action: The action performed (ADD, UPDATE, DELETE, NOOP).
            memory_id: Historical reference to the memory row id
                (not an enforced FK -- may refer to a deleted row).
            category: Snapshot of the memory category at time of action.
            key: Snapshot of the memory key at time of action.
            old_value: Previous value (for UPDATE/DELETE), or ``None``.
            new_value: New value (for ADD/UPDATE), or ``None``.
            transcript: Source transcript filename, or ``None``.

        Returns:
            The ``id`` of the new log entry.
        """
        now = datetime.now(UTC).isoformat()
        cursor = self._conn.execute(
            """\
            INSERT INTO memory_log
                (memory_id, category, key, action, old_value, new_value, transcript, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (memory_id, category, key, action, old_value, new_value, transcript, now),
        )
        self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()
