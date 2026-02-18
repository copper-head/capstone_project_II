"""cal-ai: Conversation-to-Calendar AI.

Extracts calendar events from conversation transcripts and syncs them
to Google Calendar.
"""

from __future__ import annotations

from cal_ai.models.transcript import ParseWarning, TranscriptParseResult, Utterance
from cal_ai.parser import parse_transcript, parse_transcript_file

__version__ = "0.1.0"

__all__ = [
    "ParseWarning",
    "TranscriptParseResult",
    "Utterance",
    "parse_transcript",
    "parse_transcript_file",
]
