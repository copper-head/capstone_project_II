"""Unit tests for the memory write path (extraction + action decision + dispatch).

Tests cover: fact extraction LLM call, action decision LLM call, action
dispatch (upsert/delete), integer ID remapping, error handling, empty
inputs, and the top-level ``run_memory_write`` orchestrator.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from cal_ai.memory.extraction import (
    _build_memory_id_map,
    _decide_actions,
    _dispatch_actions,
    _extract_facts,
    run_memory_write,
)
from cal_ai.memory.models import (
    MemoryAction,
    MemoryFact,
    MemoryRecord,
)
from cal_ai.memory.prompts import (
    format_candidate_facts_for_prompt,
    format_existing_memories_for_prompt,
    format_extracted_events_for_prompt,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_memory_record(
    id: int = 1,
    category: str = "preferences",
    key: str = "meeting_time",
    value: str = "Prefers mornings",
    confidence: str = "medium",
) -> MemoryRecord:
    return MemoryRecord(id=id, category=category, key=key, value=value, confidence=confidence)


def _make_memory_fact(
    category: str = "preferences",
    key: str = "meeting_time",
    value: str = "Owner prefers mornings",
    confidence: str = "medium",
) -> MemoryFact:
    return MemoryFact(category=category, key=key, value=value, confidence=confidence)


def _make_memory_action(
    action: str = "ADD",
    category: str = "preferences",
    key: str = "meeting_time",
    new_value: str | None = "Owner prefers mornings",
    confidence: str = "medium",
    reasoning: str = "New fact",
    target_memory_id: int | None = None,
) -> MemoryAction:
    return MemoryAction(
        action=action,
        category=category,
        key=key,
        new_value=new_value,
        confidence=confidence,
        reasoning=reasoning,
        target_memory_id=target_memory_id,
    )


def _mock_gemini_call_result(response_dict: dict) -> MagicMock:
    """Create a mock LLMCallResult from a dict."""
    result = MagicMock()
    result.text = json.dumps(response_dict)
    result.usage = MagicMock()
    return result


# ---------------------------------------------------------------------------
# Tests: Prompt formatting
# ---------------------------------------------------------------------------


class TestPromptFormatting:
    """Tests for prompt text formatting helpers."""

    def test_format_extracted_events_empty(self) -> None:
        assert format_extracted_events_for_prompt([]) == ""

    def test_format_extracted_events_with_events(self) -> None:
        event = MagicMock()
        event.action = "create"
        event.title = "Lunch"
        event.start_time = "2026-02-19T12:00:00"
        event.location = "Cafe"
        event.attendees = ["Alice", "Bob"]

        text = format_extracted_events_for_prompt([event])
        assert 'CREATE: "Lunch"' in text
        assert "2026-02-19T12:00:00" in text
        assert "Cafe" in text
        assert "Alice, Bob" in text

    def test_format_candidate_facts_empty(self) -> None:
        assert format_candidate_facts_for_prompt([]) == "(no candidate facts)"

    def test_format_candidate_facts_with_facts(self) -> None:
        fact = _make_memory_fact()
        text = format_candidate_facts_for_prompt([fact])
        assert "1." in text
        assert "[preferences]" in text
        assert "meeting_time" in text

    def test_format_existing_memories_empty(self) -> None:
        assert format_existing_memories_for_prompt([], {}) == "(no existing memories)"

    def test_format_existing_memories_with_remapped_ids(self) -> None:
        mem = _make_memory_record(id=42)
        id_map = {1: 42}
        text = format_existing_memories_for_prompt([mem], id_map)
        assert "[1]" in text
        assert "preferences" in text
        assert "meeting_time" in text


# ---------------------------------------------------------------------------
# Tests: Integer ID remapping
# ---------------------------------------------------------------------------


class TestIdRemapping:
    """Tests for memory ID remapping."""

    def test_build_memory_id_map_empty(self) -> None:
        assert _build_memory_id_map([]) == {}

    def test_build_memory_id_map_sequential(self) -> None:
        records = [
            _make_memory_record(id=10),
            _make_memory_record(id=20, key="lunch"),
            _make_memory_record(id=30, key="standup"),
        ]
        id_map = _build_memory_id_map(records)
        assert id_map == {1: 10, 2: 20, 3: 30}


# ---------------------------------------------------------------------------
# Tests: Fact extraction LLM call
# ---------------------------------------------------------------------------


class TestFactExtraction:
    """Tests for the fact extraction LLM call."""

    def test_extract_facts_returns_facts(self) -> None:
        mock_gemini = MagicMock()
        response = {
            "facts": [
                {
                    "category": "preferences",
                    "key": "meeting_time",
                    "value": "Owner prefers mornings",
                    "confidence": "high",
                },
            ]
        }
        mock_gemini._call_api.return_value = _mock_gemini_call_result(response)

        facts, usage = _extract_facts(
            gemini_client=mock_gemini,
            transcript_text="[Alice]: I prefer mornings",
            extracted_events=[],
            owner_name="Alice",
        )

        assert len(facts) == 1
        assert facts[0].category == "preferences"
        assert facts[0].key == "meeting_time"
        assert usage is not None
        mock_gemini._call_api.assert_called_once()

    def test_extract_facts_empty_response(self) -> None:
        mock_gemini = MagicMock()
        response = {"facts": []}
        mock_gemini._call_api.return_value = _mock_gemini_call_result(response)

        facts, usage = _extract_facts(
            gemini_client=mock_gemini,
            transcript_text="[Alice]: Nice weather",
            extracted_events=[],
            owner_name="Alice",
        )

        assert facts == []

    def test_extract_facts_multiple_categories(self) -> None:
        mock_gemini = MagicMock()
        response = {
            "facts": [
                {
                    "category": "preferences",
                    "key": "meeting_time",
                    "value": "Alice prefers mornings",
                    "confidence": "high",
                },
                {
                    "category": "people",
                    "key": "bob",
                    "value": "Bob is Alice's manager",
                    "confidence": "high",
                },
                {
                    "category": "vocabulary",
                    "key": "wellness hour",
                    "value": "Alice's therapy appointment",
                    "confidence": "medium",
                },
            ]
        }
        mock_gemini._call_api.return_value = _mock_gemini_call_result(response)

        facts, _ = _extract_facts(
            gemini_client=mock_gemini,
            transcript_text="[Alice]: Test",
            extracted_events=[],
            owner_name="Alice",
        )

        assert len(facts) == 3
        categories = {f.category for f in facts}
        assert categories == {"preferences", "people", "vocabulary"}


# ---------------------------------------------------------------------------
# Tests: Action decision LLM call
# ---------------------------------------------------------------------------


class TestActionDecision:
    """Tests for the action decision LLM call."""

    def test_decide_actions_returns_actions(self) -> None:
        mock_gemini = MagicMock()
        response = {
            "actions": [
                {
                    "action": "ADD",
                    "category": "preferences",
                    "key": "meeting_time",
                    "new_value": "Owner prefers mornings",
                    "confidence": "high",
                    "reasoning": "New fact",
                    "target_memory_id": None,
                },
            ]
        }
        mock_gemini._call_api.return_value = _mock_gemini_call_result(response)

        facts = [_make_memory_fact()]
        memories = []
        id_map = {}

        actions, usage = _decide_actions(
            gemini_client=mock_gemini,
            candidate_facts=facts,
            existing_memories=memories,
            owner_name="Alice",
            id_map=id_map,
        )

        assert len(actions) == 1
        assert actions[0].action == "ADD"
        mock_gemini._call_api.assert_called_once()

    def test_decide_actions_all_four_types(self) -> None:
        mock_gemini = MagicMock()
        response = {
            "actions": [
                {
                    "action": "ADD",
                    "category": "people",
                    "key": "carol",
                    "new_value": "Carol is Alice's colleague",
                    "confidence": "high",
                    "reasoning": "New person",
                    "target_memory_id": None,
                },
                {
                    "action": "UPDATE",
                    "category": "people",
                    "key": "bob",
                    "new_value": "Bob was Alice's former manager",
                    "confidence": "high",
                    "reasoning": "Past tense",
                    "target_memory_id": 1,
                },
                {
                    "action": "DELETE",
                    "category": "corrections",
                    "key": "old_fact",
                    "new_value": None,
                    "confidence": "high",
                    "reasoning": "Obsolete",
                    "target_memory_id": 2,
                },
                {
                    "action": "NOOP",
                    "category": "preferences",
                    "key": "meeting_time",
                    "new_value": None,
                    "confidence": "medium",
                    "reasoning": "Already known",
                    "target_memory_id": 3,
                },
            ]
        }
        mock_gemini._call_api.return_value = _mock_gemini_call_result(response)

        actions, _ = _decide_actions(
            gemini_client=mock_gemini,
            candidate_facts=[_make_memory_fact()],
            existing_memories=[],
            owner_name="Alice",
            id_map={},
        )

        action_types = [a.action for a in actions]
        assert action_types == ["ADD", "UPDATE", "DELETE", "NOOP"]


# ---------------------------------------------------------------------------
# Tests: Action dispatch
# ---------------------------------------------------------------------------


class TestActionDispatch:
    """Tests for dispatching actions to the memory store."""

    def test_dispatch_add_action(self, tmp_path: Path) -> None:
        from cal_ai.memory.store import MemoryStore

        store = MemoryStore(tmp_path / "memory.db")
        try:
            actions = [_make_memory_action(action="ADD", new_value="Prefers mornings")]
            id_map: dict[int, int] = {}

            result = _dispatch_actions(store, actions, id_map, transcript_name="test.txt")

            assert result.memories_added == 1
            assert result.memories_updated == 0
            assert result.memories_deleted == 0

            # Verify the memory was stored.
            memories = store.load_all()
            assert len(memories) == 1
            assert memories[0].value == "Prefers mornings"
        finally:
            store.close()

    def test_dispatch_update_action(self, tmp_path: Path) -> None:
        from cal_ai.memory.store import MemoryStore

        store = MemoryStore(tmp_path / "memory.db")
        try:
            # Seed an existing memory.
            db_id = store.upsert("people", "bob", "Bob is manager", "medium")

            actions = [
                _make_memory_action(
                    action="UPDATE",
                    category="people",
                    key="bob",
                    new_value="Bob was former manager",
                    target_memory_id=1,  # Remapped ID
                )
            ]
            id_map = {1: db_id}

            result = _dispatch_actions(store, actions, id_map, transcript_name="test.txt")

            assert result.memories_updated == 1

            # Verify the memory was updated.
            memories = store.load_all()
            assert len(memories) == 1
            assert memories[0].value == "Bob was former manager"
        finally:
            store.close()

    def test_dispatch_delete_action(self, tmp_path: Path) -> None:
        from cal_ai.memory.store import MemoryStore

        store = MemoryStore(tmp_path / "memory.db")
        try:
            db_id = store.upsert("corrections", "old_fact", "Wrong info", "low")

            actions = [
                _make_memory_action(
                    action="DELETE",
                    category="corrections",
                    key="old_fact",
                    new_value=None,
                    target_memory_id=1,
                )
            ]
            id_map = {1: db_id}

            result = _dispatch_actions(store, actions, id_map, transcript_name="test.txt")

            assert result.memories_deleted == 1

            # Verify the memory was deleted.
            memories = store.load_all()
            assert len(memories) == 0
        finally:
            store.close()

    def test_dispatch_noop_action_does_not_modify_store(self, tmp_path: Path) -> None:
        from cal_ai.memory.store import MemoryStore

        store = MemoryStore(tmp_path / "memory.db")
        try:
            db_id = store.upsert("preferences", "meeting_time", "Mornings", "high")

            actions = [
                _make_memory_action(
                    action="NOOP",
                    key="meeting_time",
                    new_value=None,
                    reasoning="Already known",
                    target_memory_id=1,
                )
            ]
            id_map = {1: db_id}

            result = _dispatch_actions(store, actions, id_map, transcript_name="test.txt")

            assert result.memories_added == 0
            assert result.memories_updated == 0
            assert result.memories_deleted == 0

            # Memory unchanged.
            memories = store.load_all()
            assert len(memories) == 1
            assert memories[0].value == "Mornings"
        finally:
            store.close()

    def test_dispatch_update_nonexistent_id_skips_gracefully(self, tmp_path: Path) -> None:
        from cal_ai.memory.store import MemoryStore

        store = MemoryStore(tmp_path / "memory.db")
        try:
            actions = [
                _make_memory_action(
                    action="UPDATE",
                    new_value="New value",
                    target_memory_id=99,  # Not in id_map
                )
            ]
            id_map: dict[int, int] = {}

            result = _dispatch_actions(store, actions, id_map, transcript_name="test.txt")

            assert result.memories_updated == 0
        finally:
            store.close()

    def test_dispatch_delete_nonexistent_id_skips_gracefully(self, tmp_path: Path) -> None:
        from cal_ai.memory.store import MemoryStore

        store = MemoryStore(tmp_path / "memory.db")
        try:
            actions = [
                _make_memory_action(
                    action="DELETE",
                    new_value=None,
                    target_memory_id=99,
                )
            ]
            id_map: dict[int, int] = {}

            result = _dispatch_actions(store, actions, id_map, transcript_name="test.txt")

            assert result.memories_deleted == 0
        finally:
            store.close()

    def test_dispatch_add_without_value_skips(self, tmp_path: Path) -> None:
        from cal_ai.memory.store import MemoryStore

        store = MemoryStore(tmp_path / "memory.db")
        try:
            actions = [_make_memory_action(action="ADD", new_value=None)]
            result = _dispatch_actions(store, actions, {}, transcript_name="test.txt")
            assert result.memories_added == 0
        finally:
            store.close()

    def test_dispatch_logs_actions_to_audit_trail(self, tmp_path: Path) -> None:
        from cal_ai.memory.store import MemoryStore

        store = MemoryStore(tmp_path / "memory.db")
        try:
            actions = [_make_memory_action(action="ADD", new_value="Test value")]
            _dispatch_actions(store, actions, {}, transcript_name="test.txt")

            # Check audit log.
            cursor = store._conn.execute(
                "SELECT action, category, key, new_value, transcript FROM memory_log"
            )
            rows = cursor.fetchall()
            assert len(rows) == 1
            assert rows[0]["action"] == "ADD"
            assert rows[0]["transcript"] == "test.txt"
        finally:
            store.close()

    def test_dispatch_mixed_actions(self, tmp_path: Path) -> None:
        from cal_ai.memory.store import MemoryStore

        store = MemoryStore(tmp_path / "memory.db")
        try:
            # Seed existing memories.
            id_bob = store.upsert("people", "bob", "Bob is manager", "medium")
            id_old = store.upsert("corrections", "old", "Wrong info", "low")

            actions = [
                _make_memory_action(
                    action="ADD",
                    category="preferences",
                    key="lunch",
                    new_value="Prefers noon",
                    reasoning="New",
                ),
                _make_memory_action(
                    action="UPDATE",
                    category="people",
                    key="bob",
                    new_value="Bob was former manager",
                    target_memory_id=1,
                    reasoning="Past tense",
                ),
                _make_memory_action(
                    action="DELETE",
                    category="corrections",
                    key="old",
                    new_value=None,
                    target_memory_id=2,
                    reasoning="Obsolete",
                ),
                _make_memory_action(
                    action="NOOP",
                    category="preferences",
                    key="meeting_time",
                    new_value=None,
                    reasoning="Already known",
                ),
            ]
            id_map = {1: id_bob, 2: id_old}

            result = _dispatch_actions(store, actions, id_map, transcript_name="test.txt")

            assert result.memories_added == 1
            assert result.memories_updated == 1
            assert result.memories_deleted == 1
        finally:
            store.close()


# ---------------------------------------------------------------------------
# Tests: Top-level orchestrator
# ---------------------------------------------------------------------------


class TestRunMemoryWrite:
    """Tests for the run_memory_write orchestrator."""

    def test_run_memory_write_full_flow(self, tmp_path: Path) -> None:
        from cal_ai.memory.store import MemoryStore

        store = MemoryStore(tmp_path / "memory.db")
        try:
            mock_gemini = MagicMock()

            # First call: fact extraction
            extraction_response = {
                "facts": [
                    {
                        "category": "preferences",
                        "key": "meeting_time",
                        "value": "Alice prefers mornings",
                        "confidence": "high",
                    },
                ]
            }
            # Second call: action decision
            decision_response = {
                "actions": [
                    {
                        "action": "ADD",
                        "category": "preferences",
                        "key": "meeting_time",
                        "new_value": "Alice prefers mornings",
                        "confidence": "high",
                        "reasoning": "New fact",
                        "target_memory_id": None,
                    },
                ]
            }
            mock_gemini._call_api.side_effect = [
                _mock_gemini_call_result(extraction_response),
                _mock_gemini_call_result(decision_response),
            ]

            result = run_memory_write(
                gemini_client=mock_gemini,
                store=store,
                transcript_text="[Alice]: I prefer mornings",
                extracted_events=[],
                owner_name="Alice",
                transcript_path=Path("/tmp/test.txt"),
            )

            assert result.memories_added == 1
            assert result.memories_updated == 0
            assert result.memories_deleted == 0
            assert len(result.usage_metadata) == 2

            # Verify the memory was stored.
            memories = store.load_all()
            assert len(memories) == 1
            assert memories[0].value == "Alice prefers mornings"
        finally:
            store.close()

    def test_run_memory_write_no_facts_skips_decision(self, tmp_path: Path) -> None:
        from cal_ai.memory.store import MemoryStore

        store = MemoryStore(tmp_path / "memory.db")
        try:
            mock_gemini = MagicMock()

            extraction_response = {"facts": []}
            mock_gemini._call_api.return_value = _mock_gemini_call_result(extraction_response)

            result = run_memory_write(
                gemini_client=mock_gemini,
                store=store,
                transcript_text="[Alice]: Hi",
                extracted_events=[],
                owner_name="Alice",
            )

            assert result.memories_added == 0
            # Only one call (extraction), not two.
            assert mock_gemini._call_api.call_count == 1
        finally:
            store.close()

    def test_run_memory_write_no_actions(self, tmp_path: Path) -> None:
        from cal_ai.memory.store import MemoryStore

        store = MemoryStore(tmp_path / "memory.db")
        try:
            mock_gemini = MagicMock()

            extraction_response = {
                "facts": [
                    {"category": "preferences", "key": "x", "value": "y", "confidence": "medium"},
                ]
            }
            decision_response = {"actions": []}
            mock_gemini._call_api.side_effect = [
                _mock_gemini_call_result(extraction_response),
                _mock_gemini_call_result(decision_response),
            ]

            result = run_memory_write(
                gemini_client=mock_gemini,
                store=store,
                transcript_text="[Alice]: Test",
                extracted_events=[],
                owner_name="Alice",
            )

            assert result.memories_added == 0
            assert result.memories_updated == 0
            assert result.memories_deleted == 0
        finally:
            store.close()

    def test_run_memory_write_with_existing_memories(self, tmp_path: Path) -> None:
        from cal_ai.memory.store import MemoryStore

        store = MemoryStore(tmp_path / "memory.db")
        try:
            # Seed a memory.
            store.upsert("people", "bob", "Bob is manager", "medium")

            mock_gemini = MagicMock()

            extraction_response = {
                "facts": [
                    {
                        "category": "people",
                        "key": "bob",
                        "value": "Bob used to be manager",
                        "confidence": "high",
                    },
                ]
            }
            decision_response = {
                "actions": [
                    {
                        "action": "UPDATE",
                        "category": "people",
                        "key": "bob",
                        "new_value": "Bob was Alice's former manager",
                        "confidence": "high",
                        "reasoning": "Past tense update",
                        "target_memory_id": 1,
                    },
                ]
            }
            mock_gemini._call_api.side_effect = [
                _mock_gemini_call_result(extraction_response),
                _mock_gemini_call_result(decision_response),
            ]

            result = run_memory_write(
                gemini_client=mock_gemini,
                store=store,
                transcript_text="[Alice]: Bob used to be my manager",
                extracted_events=[],
                owner_name="Alice",
            )

            assert result.memories_updated == 1

            # Verify the memory was updated.
            memories = store.load_all()
            assert len(memories) == 1
            assert "former manager" in memories[0].value
        finally:
            store.close()

    def test_run_memory_write_transcript_name_in_log(self, tmp_path: Path) -> None:
        from cal_ai.memory.store import MemoryStore

        store = MemoryStore(tmp_path / "memory.db")
        try:
            mock_gemini = MagicMock()

            extraction_response = {
                "facts": [
                    {
                        "category": "preferences",
                        "key": "test",
                        "value": "Test value",
                        "confidence": "medium",
                    },
                ]
            }
            decision_response = {
                "actions": [
                    {
                        "action": "ADD",
                        "category": "preferences",
                        "key": "test",
                        "new_value": "Test value",
                        "confidence": "medium",
                        "reasoning": "New",
                        "target_memory_id": None,
                    },
                ]
            }
            mock_gemini._call_api.side_effect = [
                _mock_gemini_call_result(extraction_response),
                _mock_gemini_call_result(decision_response),
            ]

            run_memory_write(
                gemini_client=mock_gemini,
                store=store,
                transcript_text="test",
                extracted_events=[],
                owner_name="Alice",
                transcript_path=Path("/data/samples/crud/meeting.txt"),
            )

            # Check that the transcript filename is in the audit log.
            cursor = store._conn.execute("SELECT transcript FROM memory_log WHERE action='ADD'")
            row = cursor.fetchone()
            assert row["transcript"] == "meeting.txt"
        finally:
            store.close()
