"""Pydantic models for the memory system.

Defines data types for memory storage, LLM fact extraction, and action decisions:

- :class:`MemoryRecord` -- a row from the ``memories`` SQLite table.
- :class:`MemoryFact` -- a candidate fact extracted by the LLM.
- :class:`MemoryAction` -- an action decision made by the LLM (ADD/UPDATE/DELETE/NOOP).
- Response wrappers for Gemini structured output.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# MemoryRecord -- SQLite row representation
# ---------------------------------------------------------------------------


class MemoryRecord(BaseModel):
    """A single memory row from the SQLite ``memories`` table.

    Attributes:
        id: Auto-incremented primary key.
        category: Memory category (preferences, people, vocabulary, patterns, corrections).
        key: Lookup identifier within the category.
        value: The memory content.
        confidence: Confidence level (low, medium, high).
        source_count: Number of conversations confirming this fact.
        created_at: ISO 8601 timestamp of creation.
        updated_at: ISO 8601 timestamp of last update.
    """

    id: int
    category: str
    key: str
    value: str
    confidence: Literal["low", "medium", "high"] = "medium"
    source_count: int = 1
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# MemoryFact -- extracted candidate fact from LLM
# ---------------------------------------------------------------------------

# NOTE: Gemini alphabetically sorts response_schema keys.
# Field names are chosen so alpha order matches logical order:
#   category -> confidence -> key -> value


class MemoryFact(BaseModel):
    """A candidate fact extracted from a conversation by the LLM.

    Attributes:
        category: Memory category for this fact.
        confidence: LLM's confidence in this fact (low, medium, high).
        key: Lookup identifier for this fact.
        value: The fact content.
    """

    category: str
    confidence: Literal["low", "medium", "high"] = "medium"
    key: str
    value: str


class MemoryFactResponse(BaseModel):
    """Wrapper for the LLM fact extraction response.

    Attributes:
        facts: List of extracted candidate facts (may be empty).
    """

    facts: list[MemoryFact] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# MemoryAction -- LLM action decision
# ---------------------------------------------------------------------------

# NOTE: Gemini alphabetically sorts response_schema keys.
# Field names chosen so alpha order matches logical order:
#   action -> category -> confidence -> key -> new_value -> reasoning -> target_memory_id


class MemoryAction(BaseModel):
    """An action decision made by the LLM for a candidate memory fact.

    The action decision LLM compares candidate facts against existing memories
    and decides what to do: ADD, UPDATE, DELETE, or NOOP.

    Attributes:
        action: The action to take (ADD, UPDATE, DELETE, NOOP).
        category: The memory category for this action.
        confidence: Final confidence level set by the action decision LLM
            (may differ from the extraction LLM's proposal).
        key: The memory key for this action.
        new_value: The value to store (for ADD/UPDATE), or None (for DELETE/NOOP).
        reasoning: Explanation of why this action was chosen (required for
            observable AI reasoning -- demo requirement).
        target_memory_id: Remapped integer ID of the existing memory to
            update/delete, or None for ADD/NOOP.
    """

    action: Literal["ADD", "UPDATE", "DELETE", "NOOP"]
    category: str
    confidence: Literal["low", "medium", "high"] = "medium"
    key: str
    new_value: str | None = None
    reasoning: str
    target_memory_id: int | None = None


class MemoryActionResponse(BaseModel):
    """Wrapper for the LLM action decision response.

    Attributes:
        actions: List of action decisions (may be empty).
    """

    actions: list[MemoryAction] = Field(default_factory=list)
