"""Long-term memory system for cal-ai.

Provides persistent storage of scheduling-relevant facts about the owner
and the people they interact with, enabling the AI to make better calendar
decisions over time.
"""

from __future__ import annotations

from cal_ai.memory.formatter import format_memory_context
from cal_ai.memory.models import (
    MemoryAction,
    MemoryActionResponse,
    MemoryFact,
    MemoryFactResponse,
    MemoryRecord,
)
from cal_ai.memory.store import MemoryStore

__all__ = [
    "MemoryAction",
    "MemoryActionResponse",
    "MemoryFact",
    "MemoryFactResponse",
    "MemoryRecord",
    "MemoryStore",
    "format_memory_context",
]
