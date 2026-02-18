"""Transcript data models for parsed conversation transcripts.

These dataclasses represent the structured output of the transcript parser.
They are intentionally simple stdlib dataclasses (not Pydantic) to keep
dependencies minimal.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Utterance:
    """A single speaker turn in a conversation transcript.

    Attributes:
        speaker: Speaker name, stripped of brackets and trimmed.
        text: Dialogue text, which may be multi-line (joined with ``\\n``).
        line_number: 1-based line number where this utterance begins
            in the source transcript.
    """

    speaker: str
    text: str
    line_number: int


@dataclass(frozen=True)
class ParseWarning:
    """A structured warning produced during transcript parsing.

    Attributes:
        line_number: 1-based line number of the problematic line.
        message: Human-readable description of the issue.
        raw_line: The original line text that triggered the warning.
    """

    line_number: int
    message: str
    raw_line: str


@dataclass(frozen=True)
class TranscriptParseResult:
    """Top-level return type from the transcript parser.

    Attributes:
        utterances: Parsed speaker turns, in order of appearance.
        speakers: Unique speaker names, ordered by first appearance.
        warnings: Any parse warnings encountered.
        source: File path of the parsed transcript, or ``"<string>"``
            when parsing from a string.
    """

    utterances: list[Utterance] = field(default_factory=list)
    speakers: list[str] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)
    source: str = "<string>"
