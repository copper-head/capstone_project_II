"""Memory write path: fact extraction and action decision orchestration.

Implements the two-call memory write pipeline:

1. **Fact extraction** -- sends the transcript + extracted events to Gemini,
   receives candidate facts with category/key/value/confidence.
2. **Action decision** -- sends candidate facts + existing memories
   (integer-remapped) to Gemini, receives ADD/UPDATE/DELETE/NOOP actions.

Both calls reuse :meth:`GeminiClient._call_api` with structured JSON output
via Pydantic response schemas (same pattern as ``benchmark/summary.py``).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google.genai import types as genai_types

from cal_ai.memory.models import (
    MemoryAction,
    MemoryActionResponse,
    MemoryFact,
    MemoryFactResponse,
    MemoryRecord,
)
from cal_ai.memory.prompts import (
    build_action_decision_prompt,
    build_fact_extraction_prompt,
    format_candidate_facts_for_prompt,
    format_existing_memories_for_prompt,
    format_extracted_events_for_prompt,
)
from cal_ai.memory.store import MemoryStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class MemoryWriteResult:
    """Result of the memory write path.

    Attributes:
        memories_added: Count of ADD actions dispatched.
        memories_updated: Count of UPDATE actions dispatched.
        memories_deleted: Count of DELETE actions dispatched.
        usage_metadata: Token usage from both LLM calls.
        actions: The raw action decisions (for logging/debugging).
    """

    memories_added: int = 0
    memories_updated: int = 0
    memories_deleted: int = 0
    usage_metadata: list[Any] = field(default_factory=list)
    actions: list[MemoryAction] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Integer ID remapping
# ---------------------------------------------------------------------------


def _build_memory_id_map(
    memories: list[MemoryRecord],
) -> dict[int, int]:
    """Build a sequential integer ID map for memories.

    Maps 1-based sequential IDs to actual DB memory IDs, following the
    same pattern as calendar context in ``context.py``.

    Args:
        memories: List of memory records from the store.

    Returns:
        Mapping from sequential integer (1, 2, ...) to DB ``memory.id``.
    """
    return {i: mem.id for i, mem in enumerate(memories, start=1)}


def _reverse_id_map(id_map: dict[int, int]) -> dict[int, int]:
    """Reverse the ID map: remapped_id -> db_id becomes db_id -> remapped_id.

    Args:
        id_map: Mapping from sequential IDs to DB IDs.

    Returns:
        Mapping from DB IDs to sequential IDs.
    """
    return {db_id: remap_id for remap_id, db_id in id_map.items()}


# ---------------------------------------------------------------------------
# LLM call: fact extraction
# ---------------------------------------------------------------------------


def _extract_facts(
    gemini_client: Any,
    transcript_text: str,
    extracted_events: list,
    owner_name: str,
) -> tuple[list[MemoryFact], Any]:
    """Run the fact extraction LLM call.

    Args:
        gemini_client: An initialized :class:`GeminiClient`.
        transcript_text: The conversation transcript text.
        extracted_events: List of :class:`ExtractedEvent` objects.
        owner_name: Display name of the calendar owner.

    Returns:
        A tuple of ``(facts, usage_metadata)``.

    Raises:
        Exception: On LLM API or parsing errors (caller handles).
    """
    events_text = format_extracted_events_for_prompt(extracted_events)
    system_prompt, user_prompt = build_fact_extraction_prompt(
        owner_name=owner_name,
        transcript_text=transcript_text,
        extracted_events_text=events_text,
    )

    config = genai_types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        response_schema=MemoryFactResponse,
    )

    call_result = gemini_client._call_api(user_prompt, config)

    # Parse the response.
    data = json.loads(call_result.text)
    response = MemoryFactResponse.model_validate(data)

    logger.info(
        "Memory fact extraction: %d candidate fact(s) extracted",
        len(response.facts),
    )
    for fact in response.facts:
        logger.debug(
            "  Candidate fact: [%s] %s = %s (confidence: %s)",
            fact.category,
            fact.key,
            fact.value,
            fact.confidence,
        )

    return response.facts, call_result.usage


# ---------------------------------------------------------------------------
# LLM call: action decision
# ---------------------------------------------------------------------------


def _decide_actions(
    gemini_client: Any,
    candidate_facts: list[MemoryFact],
    existing_memories: list[MemoryRecord],
    owner_name: str,
    id_map: dict[int, int],
) -> tuple[list[MemoryAction], Any]:
    """Run the action decision LLM call.

    Args:
        gemini_client: An initialized :class:`GeminiClient`.
        candidate_facts: Facts from the extraction step.
        existing_memories: Current memories from the store.
        owner_name: Display name of the calendar owner.
        id_map: Mapping from sequential IDs to DB memory IDs.

    Returns:
        A tuple of ``(actions, usage_metadata)``.

    Raises:
        Exception: On LLM API or parsing errors (caller handles).
    """
    facts_text = format_candidate_facts_for_prompt(candidate_facts)
    memories_text = format_existing_memories_for_prompt(existing_memories, id_map)

    system_prompt, user_prompt = build_action_decision_prompt(
        owner_name=owner_name,
        candidate_facts_text=facts_text,
        existing_memories_text=memories_text,
    )

    config = genai_types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        response_schema=MemoryActionResponse,
    )

    call_result = gemini_client._call_api(user_prompt, config)

    # Parse the response.
    data = json.loads(call_result.text)
    response = MemoryActionResponse.model_validate(data)

    logger.info(
        "Memory action decision: %d action(s) decided",
        len(response.actions),
    )
    for action in response.actions:
        logger.info(
            "  Memory action: %s [%s] %s -- %s",
            action.action,
            action.category,
            action.key,
            action.reasoning,
        )

    return response.actions, call_result.usage


# ---------------------------------------------------------------------------
# Action dispatch
# ---------------------------------------------------------------------------


def _dispatch_actions(
    store: MemoryStore,
    actions: list[MemoryAction],
    id_map: dict[int, int],
    transcript_name: str | None = None,
) -> MemoryWriteResult:
    """Dispatch memory actions to the store.

    ADD and UPDATE both use :meth:`MemoryStore.upsert`.
    DELETE uses :meth:`MemoryStore.delete`.
    All actions are logged via :meth:`MemoryStore.log_action`.

    Invalid targets (UPDATE/DELETE referencing nonexistent remapped ID)
    are logged as warnings and skipped.

    Args:
        store: The memory store instance.
        actions: List of action decisions from the LLM.
        id_map: Mapping from sequential integer IDs to DB memory IDs.
        transcript_name: Source transcript filename for audit log.

    Returns:
        A :class:`MemoryWriteResult` with counts.
    """
    result = MemoryWriteResult(actions=actions)

    # Build a lookup for existing memory values by DB ID for old_value logging.
    # We need to look up existing memories to get old_value for UPDATE/DELETE.
    existing_by_db_id: dict[int, MemoryRecord] = {}
    all_memories = store.load_all()
    for mem in all_memories:
        existing_by_db_id[mem.id] = mem

    for action in actions:
        if action.action == "NOOP":
            # Log it but don't touch the store.
            store.log_action(
                action="NOOP",
                memory_id=id_map.get(action.target_memory_id) if action.target_memory_id else None,
                category=action.category,
                key=action.key,
                old_value=None,
                new_value=None,
                transcript=transcript_name,
            )
            continue

        if action.action == "ADD":
            if action.new_value is None:
                logger.warning(
                    "ADD action for [%s] %s has no new_value, skipping",
                    action.category,
                    action.key,
                )
                continue

            mem_id = store.upsert(
                category=action.category,
                key=action.key,
                value=action.new_value,
                confidence=action.confidence,
            )
            store.log_action(
                action="ADD",
                memory_id=mem_id,
                category=action.category,
                key=action.key,
                old_value=None,
                new_value=action.new_value,
                transcript=transcript_name,
            )
            result.memories_added += 1
            logger.info(
                "Memory ADD: [%s] %s = %s",
                action.category,
                action.key,
                action.new_value,
            )

        elif action.action == "UPDATE":
            if action.target_memory_id is None:
                logger.warning(
                    "UPDATE action for [%s] %s has no target_memory_id, skipping",
                    action.category,
                    action.key,
                )
                continue

            db_id = id_map.get(action.target_memory_id)
            if db_id is None:
                logger.warning(
                    "UPDATE target_memory_id %d not found in id_map, skipping",
                    action.target_memory_id,
                )
                continue

            existing = existing_by_db_id.get(db_id)
            if existing is None:
                logger.warning(
                    "UPDATE target DB id %d not found in store, skipping",
                    db_id,
                )
                continue

            if action.new_value is None:
                logger.warning(
                    "UPDATE action for [%s] %s has no new_value, skipping",
                    action.category,
                    action.key,
                )
                continue

            old_value = existing.value
            mem_id = store.upsert(
                category=action.category,
                key=action.key,
                value=action.new_value,
                confidence=action.confidence,
            )
            store.log_action(
                action="UPDATE",
                memory_id=mem_id,
                category=action.category,
                key=action.key,
                old_value=old_value,
                new_value=action.new_value,
                transcript=transcript_name,
            )
            result.memories_updated += 1
            logger.info(
                "Memory UPDATE: [%s] %s: %s -> %s",
                action.category,
                action.key,
                old_value,
                action.new_value,
            )

        elif action.action == "DELETE":
            if action.target_memory_id is None:
                logger.warning(
                    "DELETE action for [%s] %s has no target_memory_id, skipping",
                    action.category,
                    action.key,
                )
                continue

            db_id = id_map.get(action.target_memory_id)
            if db_id is None:
                logger.warning(
                    "DELETE target_memory_id %d not found in id_map, skipping",
                    action.target_memory_id,
                )
                continue

            existing = existing_by_db_id.get(db_id)
            old_value = existing.value if existing else None

            deleted = store.delete(db_id)
            if not deleted:
                logger.warning(
                    "DELETE target DB id %d not found in store (already deleted?)",
                    db_id,
                )

            store.log_action(
                action="DELETE",
                memory_id=db_id,
                category=action.category,
                key=action.key,
                old_value=old_value,
                new_value=None,
                transcript=transcript_name,
            )
            result.memories_deleted += 1
            logger.info(
                "Memory DELETE: [%s] %s (was: %s)",
                action.category,
                action.key,
                old_value,
            )

    return result


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def run_memory_write(
    gemini_client: Any,
    store: MemoryStore,
    transcript_text: str,
    extracted_events: list,
    owner_name: str,
    transcript_path: Path | str | None = None,
) -> MemoryWriteResult:
    """Run the full memory write pipeline.

    Orchestrates fact extraction, action decision, and dispatch.
    Both LLM calls' usage metadata is collected into the result.

    Args:
        gemini_client: An initialized :class:`GeminiClient`.
        store: The memory store instance.
        transcript_text: The conversation transcript text.
        extracted_events: List of :class:`ExtractedEvent` objects
            (may be empty).
        owner_name: Display name of the calendar owner.
        transcript_path: Path to the source transcript (for audit log).

    Returns:
        A :class:`MemoryWriteResult` with counts and usage metadata.
    """
    transcript_name = Path(transcript_path).name if transcript_path else None

    # Step 1: Extract candidate facts.
    facts, extraction_usage = _extract_facts(
        gemini_client=gemini_client,
        transcript_text=transcript_text,
        extracted_events=extracted_events,
        owner_name=owner_name,
    )

    usage_metadata: list[Any] = []
    if extraction_usage is not None:
        usage_metadata.append(extraction_usage)

    if not facts:
        logger.info("No candidate facts extracted, skipping action decision")
        return MemoryWriteResult(usage_metadata=usage_metadata)

    # Step 2: Load existing memories and build ID map.
    existing_memories = store.load_all()
    id_map = _build_memory_id_map(existing_memories)

    # Step 3: Decide actions.
    actions, decision_usage = _decide_actions(
        gemini_client=gemini_client,
        candidate_facts=facts,
        existing_memories=existing_memories,
        owner_name=owner_name,
        id_map=id_map,
    )

    if decision_usage is not None:
        usage_metadata.append(decision_usage)

    if not actions:
        logger.info("No memory actions decided")
        return MemoryWriteResult(usage_metadata=usage_metadata)

    # Step 4: Dispatch actions to the store.
    write_result = _dispatch_actions(
        store=store,
        actions=actions,
        id_map=id_map,
        transcript_name=transcript_name,
    )
    write_result.usage_metadata = usage_metadata

    return write_result
