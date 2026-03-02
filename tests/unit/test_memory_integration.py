"""Integration tests for the memory system: full read+write paths.

Covers the end-to-end memory lifecycle using a real SQLite database
(file-based via ``tmp_path``), real formatter, and mocked LLM calls.

Tests:
- Read path: seed store -> load -> format -> verify prompt section.
- Write path (dispatch): dispatch actions -> verify store mutations.
- Write path (orchestrator): run_memory_write with mocked LLM -> verify DB state + result.
- Round-trip: seed, run write path, verify DB state.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from cal_ai.memory.extraction import (
    MemoryWriteResult,
    _build_memory_id_map,
    _dispatch_actions,
    run_memory_write,
)
from cal_ai.memory.formatter import format_memory_context
from cal_ai.memory.models import MemoryAction, MemoryRecord
from cal_ai.memory.store import MemoryStore

# ---------------------------------------------------------------------------
# Read path tests
# ---------------------------------------------------------------------------


class TestMemoryReadPath:
    """Integration tests for the memory read path: store -> format -> prompt."""

    def test_seed_load_format_produces_prompt_section(self, tmp_path: Path) -> None:
        """Seed store -> load_all -> format_memory_context -> valid prompt section."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        try:
            store.upsert("preferences", "meeting_time", "Alice prefers mornings", "high")
            store.upsert("people", "Bob", "Alice's manager; weekly 1:1 Tuesdays", "medium")
            store.upsert("vocabulary", "quick sync", "15-minute meeting", "low")

            memories = store.load_all()
            assert len(memories) == 3

            formatted = format_memory_context(memories, "Alice")
            assert "## Your Memory (about Alice)" in formatted
            assert "### Preferences" in formatted
            assert "meeting_time" in formatted
            assert "Alice prefers mornings" in formatted
            assert "### People" in formatted
            assert "Bob" in formatted
            assert "### Vocabulary" in formatted
            assert "quick sync" in formatted
        finally:
            store.close()

    def test_empty_store_produces_empty_string(self, tmp_path: Path) -> None:
        """Empty memory store -> format_memory_context returns empty string."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        try:
            memories = store.load_all()
            assert memories == []

            formatted = format_memory_context(memories, "Alice")
            assert formatted == ""
        finally:
            store.close()

    def test_load_returns_memory_records(self, tmp_path: Path) -> None:
        """Store returns MemoryRecord instances with correct fields."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        try:
            store.upsert("patterns", "lunch_time", "12:30pm", "high")
            memories = store.load_all()

            assert len(memories) == 1
            mem = memories[0]
            assert isinstance(mem, MemoryRecord)
            assert mem.category == "patterns"
            assert mem.key == "lunch_time"
            assert mem.value == "12:30pm"
            assert mem.confidence == "high"
            assert mem.source_count == 1
            assert mem.created_at != ""
            assert mem.updated_at != ""
        finally:
            store.close()

    def test_format_groups_by_category(self, tmp_path: Path) -> None:
        """Memories from multiple categories are grouped under subheadings."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        try:
            store.upsert("corrections", "standup_duration", "15 min, not 30", "high")
            store.upsert("preferences", "default_location", "Room A", "medium")
            store.upsert("corrections", "team_meeting_day", "Wednesday, not Thursday", "medium")

            memories = store.load_all()
            formatted = format_memory_context(memories, "Alice")

            # Verify both category headings appear.
            assert "### Corrections" in formatted
            assert "### Preferences" in formatted
            # Verify entries under the right headings.
            assert "standup_duration" in formatted
            assert "team_meeting_day" in formatted
            assert "default_location" in formatted
        finally:
            store.close()


# ---------------------------------------------------------------------------
# Write path tests
# ---------------------------------------------------------------------------


class TestMemoryWritePath:
    """Integration tests for the memory write path: actions -> store mutations."""

    def test_add_action_creates_memory(self, tmp_path: Path) -> None:
        """ADD action -> new memory appears in store."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        try:
            actions = [
                MemoryAction(
                    action="ADD",
                    category="preferences",
                    confidence="high",
                    key="meeting_time",
                    new_value="Alice prefers mornings before 11am",
                    reasoning="Alice explicitly stated she prefers mornings.",
                ),
            ]
            id_map: dict[int, int] = {}

            result = _dispatch_actions(store, actions, id_map, transcript_name="test.txt")

            assert result.memories_added == 1
            assert result.memories_updated == 0
            assert result.memories_deleted == 0

            # Verify in DB.
            memories = store.load_all()
            assert len(memories) == 1
            assert memories[0].category == "preferences"
            assert memories[0].key == "meeting_time"
            assert memories[0].value == "Alice prefers mornings before 11am"
            assert memories[0].confidence == "high"
        finally:
            store.close()

    def test_update_action_modifies_memory(self, tmp_path: Path) -> None:
        """UPDATE action -> existing memory value updated, source_count incremented."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        try:
            # Seed an existing memory.
            store.upsert("people", "Bob", "Alice's colleague", "medium")

            # Build ID map: remapped ID 1 -> db ID mem_id.
            existing = store.load_all()
            id_map = _build_memory_id_map(existing)

            actions = [
                MemoryAction(
                    action="UPDATE",
                    category="people",
                    confidence="high",
                    key="Bob",
                    new_value="Alice's manager; weekly 1:1 on Tuesdays",
                    reasoning="Bob was promoted to Alice's manager.",
                    target_memory_id=1,  # remapped ID
                ),
            ]

            result = _dispatch_actions(store, actions, id_map, transcript_name="test.txt")

            assert result.memories_updated == 1

            # Verify update in DB.
            memories = store.load_all()
            assert len(memories) == 1
            assert memories[0].value == "Alice's manager; weekly 1:1 on Tuesdays"
            assert memories[0].confidence == "high"
            assert memories[0].source_count == 2  # incremented by upsert
        finally:
            store.close()

    def test_delete_action_removes_memory(self, tmp_path: Path) -> None:
        """DELETE action -> memory removed from store."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        try:
            # Seed two memories.
            store.upsert("vocabulary", "quick sync", "15-minute meeting", "medium")
            store.upsert("vocabulary", "standup", "daily standup", "high")

            existing = store.load_all()
            id_map = _build_memory_id_map(existing)
            assert len(existing) == 2

            # Delete the first one (remapped ID 1).
            actions = [
                MemoryAction(
                    action="DELETE",
                    category="vocabulary",
                    confidence="medium",
                    key="quick sync",
                    reasoning="Owner no longer uses this term.",
                    target_memory_id=1,
                ),
            ]

            result = _dispatch_actions(store, actions, id_map, transcript_name="test.txt")

            assert result.memories_deleted == 1

            # Verify deletion in DB.
            memories = store.load_all()
            assert len(memories) == 1
            assert memories[0].key == "standup"
        finally:
            store.close()

    def test_noop_action_leaves_store_unchanged(self, tmp_path: Path) -> None:
        """NOOP action -> store is unchanged, log entry created."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        try:
            store.upsert("preferences", "meeting_time", "mornings", "high")
            existing = store.load_all()
            id_map = _build_memory_id_map(existing)

            actions = [
                MemoryAction(
                    action="NOOP",
                    category="preferences",
                    confidence="high",
                    key="meeting_time",
                    reasoning="Already known, no change needed.",
                    target_memory_id=1,
                ),
            ]

            result = _dispatch_actions(store, actions, id_map, transcript_name="test.txt")

            assert result.memories_added == 0
            assert result.memories_updated == 0
            assert result.memories_deleted == 0

            # Store should be unchanged.
            memories = store.load_all()
            assert len(memories) == 1
            assert memories[0].value == "mornings"
        finally:
            store.close()

    def test_mixed_actions_batch(self, tmp_path: Path) -> None:
        """Multiple actions in a single batch: ADD + UPDATE + DELETE."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        try:
            # Seed existing memories.
            store.upsert("people", "Bob", "Alice's colleague", "medium")
            store.upsert("vocabulary", "standup", "daily standup", "low")

            existing = store.load_all()
            id_map = _build_memory_id_map(existing)

            actions = [
                # ADD a new memory.
                MemoryAction(
                    action="ADD",
                    category="preferences",
                    confidence="high",
                    key="default_duration",
                    new_value="1 hour",
                    reasoning="Alice mentioned she likes 1-hour meetings.",
                ),
                # UPDATE Bob's info.
                MemoryAction(
                    action="UPDATE",
                    category="people",
                    confidence="high",
                    key="Bob",
                    new_value="Alice's manager",
                    reasoning="Bob was promoted.",
                    target_memory_id=1,
                ),
                # DELETE standup vocab.
                MemoryAction(
                    action="DELETE",
                    category="vocabulary",
                    confidence="medium",
                    key="standup",
                    reasoning="No longer relevant.",
                    target_memory_id=2,
                ),
            ]

            result = _dispatch_actions(store, actions, id_map, transcript_name="test.txt")

            assert result.memories_added == 1
            assert result.memories_updated == 1
            assert result.memories_deleted == 1

            # Verify final state.
            memories = store.load_all()
            # Should have: people/Bob (updated) + preferences/default_duration (added)
            assert len(memories) == 2
            keys = {m.key for m in memories}
            assert keys == {"Bob", "default_duration"}

            # Verify Bob was updated.
            bob = next(m for m in memories if m.key == "Bob")
            assert bob.value == "Alice's manager"
        finally:
            store.close()

    def test_audit_log_records_all_actions(self, tmp_path: Path) -> None:
        """Audit log records ADD, UPDATE, DELETE, and NOOP with correct fields."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        try:
            # Seed a memory.
            store.upsert("people", "Carol", "Alice's dentist", "medium")
            existing = store.load_all()
            id_map = _build_memory_id_map(existing)

            actions = [
                MemoryAction(
                    action="ADD",
                    category="vocabulary",
                    confidence="medium",
                    key="wellness hour",
                    new_value="therapy appointment",
                    reasoning="Alice uses this term.",
                ),
                MemoryAction(
                    action="UPDATE",
                    category="people",
                    confidence="high",
                    key="Carol",
                    new_value="Alice's dentist; appointments need 'Dental' title",
                    reasoning="More details about Carol.",
                    target_memory_id=1,
                ),
                MemoryAction(
                    action="NOOP",
                    category="people",
                    confidence="medium",
                    key="Carol",
                    reasoning="Already known.",
                    target_memory_id=1,
                ),
            ]

            _dispatch_actions(store, actions, id_map, transcript_name="convo.txt")

            # Check audit log.
            cursor = store._conn.execute(
                "SELECT action, category, key, old_value, new_value, transcript "
                "FROM memory_log ORDER BY id"
            )
            logs = cursor.fetchall()

            assert len(logs) == 3

            # ADD log.
            assert logs[0]["action"] == "ADD"
            assert logs[0]["category"] == "vocabulary"
            assert logs[0]["key"] == "wellness hour"
            assert logs[0]["new_value"] == "therapy appointment"
            assert logs[0]["transcript"] == "convo.txt"

            # UPDATE log.
            assert logs[1]["action"] == "UPDATE"
            assert logs[1]["category"] == "people"
            assert logs[1]["key"] == "Carol"
            assert logs[1]["old_value"] == "Alice's dentist"
            assert logs[1]["new_value"] == "Alice's dentist; appointments need 'Dental' title"

            # NOOP log.
            assert logs[2]["action"] == "NOOP"
            assert logs[2]["category"] == "people"
        finally:
            store.close()

    def test_file_based_db_persists_across_instances(self, tmp_path: Path) -> None:
        """File-based DB: data written by one MemoryStore is readable by another."""
        db_path = tmp_path / "memory.db"

        # Write with first instance.
        store1 = MemoryStore(db_path)
        try:
            store1.upsert("preferences", "timezone", "America/Vancouver", "high")
        finally:
            store1.close()

        # Read with second instance.
        store2 = MemoryStore(db_path)
        try:
            memories = store2.load_all()
            assert len(memories) == 1
            assert memories[0].key == "timezone"
            assert memories[0].value == "America/Vancouver"
        finally:
            store2.close()


# ---------------------------------------------------------------------------
# End-to-end orchestrator tests (run_memory_write with mocked LLM)
# ---------------------------------------------------------------------------


def _make_mock_call_result(response_json: dict, usage_prompt: int = 100, usage_output: int = 50):
    """Build a mock LLM _call_api return value with text and usage."""
    mock_result = MagicMock()
    mock_result.text = json.dumps(response_json)
    mock_usage = MagicMock()
    mock_usage.prompt_token_count = usage_prompt
    mock_usage.candidates_token_count = usage_output
    mock_result.usage = mock_usage
    return mock_result


class TestMemoryWriteOrchestrator:
    """End-to-end tests for run_memory_write with mocked Gemini client."""

    def test_run_memory_write_add_new_fact(self, tmp_path: Path) -> None:
        """Full orchestrator: fact extraction -> action decision -> DB write."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        try:
            # Mock Gemini client with two sequential _call_api responses.
            mock_gemini = MagicMock()

            # First call: fact extraction returns one candidate fact.
            fact_response = {
                "facts": [
                    {
                        "category": "preferences",
                        "confidence": "high",
                        "key": "meeting_time",
                        "value": "Alice prefers mornings before 11am",
                    }
                ]
            }
            # Second call: action decision returns ADD action.
            action_response = {
                "actions": [
                    {
                        "action": "ADD",
                        "category": "preferences",
                        "confidence": "high",
                        "key": "meeting_time",
                        "new_value": "Alice prefers mornings before 11am",
                        "reasoning": "New preference from conversation.",
                    }
                ]
            }

            mock_gemini._call_api.side_effect = [
                _make_mock_call_result(fact_response, usage_prompt=150, usage_output=80),
                _make_mock_call_result(action_response, usage_prompt=200, usage_output=60),
            ]

            result = run_memory_write(
                gemini_client=mock_gemini,
                store=store,
                transcript_text="[Alice]: I really prefer morning meetings, before 11am.",
                extracted_events=[],
                owner_name="Alice",
                transcript_path="test_convo.txt",
            )

            # Verify result counts.
            assert isinstance(result, MemoryWriteResult)
            assert result.memories_added == 1
            assert result.memories_updated == 0
            assert result.memories_deleted == 0

            # Verify usage metadata collected from both LLM calls.
            assert len(result.usage_metadata) == 2
            assert result.usage_metadata[0].prompt_token_count == 150
            assert result.usage_metadata[1].prompt_token_count == 200

            # Verify DB state.
            memories = store.load_all()
            assert len(memories) == 1
            assert memories[0].category == "preferences"
            assert memories[0].key == "meeting_time"
            assert memories[0].value == "Alice prefers mornings before 11am"
            assert memories[0].confidence == "high"

            # Verify audit log.
            cursor = store._conn.execute("SELECT action, transcript FROM memory_log ORDER BY id")
            logs = cursor.fetchall()
            assert len(logs) == 1
            assert logs[0]["action"] == "ADD"
            assert logs[0]["transcript"] == "test_convo.txt"

            # Verify _call_api was called exactly twice.
            assert mock_gemini._call_api.call_count == 2
        finally:
            store.close()

    def test_run_memory_write_update_existing_fact(self, tmp_path: Path) -> None:
        """Orchestrator with seeded store: extraction -> UPDATE -> verify mutation."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        try:
            # Seed an existing memory.
            store.upsert("people", "Bob", "Alice's colleague", "medium")

            mock_gemini = MagicMock()

            fact_response = {
                "facts": [
                    {
                        "category": "people",
                        "confidence": "high",
                        "key": "Bob",
                        "value": "Alice's manager; weekly 1:1 on Tuesdays",
                    }
                ]
            }
            # The existing memory will be remapped to ID 1 by _build_memory_id_map.
            action_response = {
                "actions": [
                    {
                        "action": "UPDATE",
                        "category": "people",
                        "confidence": "high",
                        "key": "Bob",
                        "new_value": "Alice's manager; weekly 1:1 on Tuesdays",
                        "reasoning": "Bob was promoted from colleague to manager.",
                        "target_memory_id": 1,
                    }
                ]
            }

            mock_gemini._call_api.side_effect = [
                _make_mock_call_result(fact_response),
                _make_mock_call_result(action_response),
            ]

            result = run_memory_write(
                gemini_client=mock_gemini,
                store=store,
                transcript_text="[Alice]: Bob is my new manager now.",
                extracted_events=[],
                owner_name="Alice",
                transcript_path="promo_convo.txt",
            )

            assert result.memories_updated == 1
            assert result.memories_added == 0

            # Verify DB was mutated.
            memories = store.load_all()
            assert len(memories) == 1
            assert memories[0].value == "Alice's manager; weekly 1:1 on Tuesdays"
            assert memories[0].source_count == 2  # incremented by upsert

            # Verify audit log records old and new values.
            cursor = store._conn.execute(
                "SELECT action, old_value, new_value FROM memory_log ORDER BY id"
            )
            logs = cursor.fetchall()
            assert len(logs) == 1
            assert logs[0]["action"] == "UPDATE"
            assert logs[0]["old_value"] == "Alice's colleague"
            assert logs[0]["new_value"] == "Alice's manager; weekly 1:1 on Tuesdays"
        finally:
            store.close()

    def test_run_memory_write_empty_facts_skips_action_decision(self, tmp_path: Path) -> None:
        """Trivial transcript -> no facts -> no action decision call -> empty result."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        try:
            mock_gemini = MagicMock()

            # Fact extraction returns empty facts array.
            fact_response = {"facts": []}
            mock_gemini._call_api.return_value = _make_mock_call_result(fact_response)

            result = run_memory_write(
                gemini_client=mock_gemini,
                store=store,
                transcript_text="[Alice]: Hey, nice weather today!",
                extracted_events=[],
                owner_name="Alice",
            )

            assert result.memories_added == 0
            assert result.memories_updated == 0
            assert result.memories_deleted == 0

            # Only one LLM call (fact extraction), no action decision.
            assert mock_gemini._call_api.call_count == 1

            # Usage metadata should still include the extraction call.
            assert len(result.usage_metadata) == 1

            # DB should be empty.
            assert store.load_all() == []
        finally:
            store.close()

    def test_run_memory_write_mixed_actions(self, tmp_path: Path) -> None:
        """Orchestrator with ADD + DELETE in single batch, verify final DB state."""
        db_path = tmp_path / "memory.db"
        store = MemoryStore(db_path)
        try:
            # Seed existing memory to delete.
            store.upsert("vocabulary", "standup", "daily standup meeting", "low")

            mock_gemini = MagicMock()

            fact_response = {
                "facts": [
                    {
                        "category": "preferences",
                        "confidence": "high",
                        "key": "default_duration",
                        "value": "1 hour for most meetings",
                    },
                    {
                        "category": "vocabulary",
                        "confidence": "low",
                        "key": "standup",
                        "value": "no longer used",
                    },
                ]
            }
            action_response = {
                "actions": [
                    {
                        "action": "ADD",
                        "category": "preferences",
                        "confidence": "high",
                        "key": "default_duration",
                        "new_value": "1 hour for most meetings",
                        "reasoning": "Alice mentioned her preferred duration.",
                    },
                    {
                        "action": "DELETE",
                        "category": "vocabulary",
                        "confidence": "low",
                        "key": "standup",
                        "reasoning": "Term no longer relevant.",
                        "target_memory_id": 1,  # remapped ID for seeded memory
                    },
                ]
            }

            mock_gemini._call_api.side_effect = [
                _make_mock_call_result(fact_response),
                _make_mock_call_result(action_response),
            ]

            result = run_memory_write(
                gemini_client=mock_gemini,
                store=store,
                transcript_text="[Alice]: I like 1-hour meetings. We don't do standups anymore.",
                extracted_events=[],
                owner_name="Alice",
                transcript_path="mixed.txt",
            )

            assert result.memories_added == 1
            assert result.memories_deleted == 1

            # Final DB should only contain the newly added preference.
            memories = store.load_all()
            assert len(memories) == 1
            assert memories[0].category == "preferences"
            assert memories[0].key == "default_duration"
        finally:
            store.close()
