"""cal-ai: Conversation-to-Calendar AI.

Extracts calendar events from conversation transcripts and syncs them
to Google Calendar.
"""

from __future__ import annotations

from cal_ai.exceptions import ExtractionError, MalformedResponseError
from cal_ai.models.extraction import (
    ExtractedEvent,
    ExtractionResult,
    LLMResponseEvent,
    LLMResponseSchema,
    ValidatedEvent,
)
from cal_ai.models.transcript import ParseWarning, TranscriptParseResult, Utterance
from cal_ai.parser import parse_transcript, parse_transcript_file
from cal_ai.prompts import build_system_prompt, build_user_prompt, format_transcript_for_llm

__version__ = "0.1.0"

__all__ = [
    "ExtractedEvent",
    "ExtractionResult",
    "ExtractionError",
    "LLMResponseEvent",
    "LLMResponseSchema",
    "MalformedResponseError",
    "ParseWarning",
    "TranscriptParseResult",
    "Utterance",
    "ValidatedEvent",
    "build_system_prompt",
    "build_user_prompt",
    "format_transcript_for_llm",
    "parse_transcript",
    "parse_transcript_file",
]
