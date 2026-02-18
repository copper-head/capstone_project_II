"""Transcript parser for conversation transcripts with speaker labels.

Parses text in the format ``[Speaker]: dialogue text`` into structured
:class:`~cal_ai.models.transcript.TranscriptParseResult` objects.
"""

from __future__ import annotations

import re
from pathlib import Path

from cal_ai.models.transcript import ParseWarning, TranscriptParseResult, Utterance

# Matches lines like: [Speaker Name]: dialogue text
# Non-greedy capture for speaker to stop at first ']'.
_UTTERANCE_RE = re.compile(r"^\[(.+?)\]:\s*(.*)$")


def parse_transcript(
    text: str,
    source: str = "<string>",
) -> TranscriptParseResult:
    """Parse a conversation transcript string into structured data.

    Args:
        text: The raw transcript text with speaker labels in the format
            ``[Speaker]: dialogue text``.  Multi-line utterances are
            supported: any non-matching, non-blank line following a
            speaker line is treated as a continuation of the current
            utterance.
        source: Label for the transcript origin (e.g. a file path).
            Defaults to ``"<string>"``.

    Returns:
        A :class:`TranscriptParseResult` containing parsed utterances,
        unique speakers ordered by first appearance, and any warnings
        for orphan lines encountered before the first speaker.
    """
    # Fast path: empty or whitespace-only input.
    if not text or not text.strip():
        return TranscriptParseResult(source=source)

    lines = text.split("\n")
    utterances: list[Utterance] = []
    warnings: list[ParseWarning] = []

    # Mutable accumulator for the utterance currently being built.
    cur_speaker: str | None = None
    cur_text_parts: list[str] = []
    cur_line_number: int = 0

    def _flush_current() -> None:
        """Append the accumulated utterance (if any) to the results list."""
        if cur_speaker is not None:
            utterances.append(
                Utterance(
                    speaker=cur_speaker,
                    text="\n".join(cur_text_parts),
                    line_number=cur_line_number,
                )
            )

    for line_idx, raw_line in enumerate(lines):
        line_number = line_idx + 1  # 1-based

        # Skip blank lines -- they are never malformed.
        if not raw_line.strip():
            continue

        match = _UTTERANCE_RE.match(raw_line)

        if match:
            # New speaker line: flush any previous utterance.
            _flush_current()

            cur_speaker = match.group(1).strip()

            # Empty speaker name (e.g. "[]: Hello") is treated as malformed.
            if not cur_speaker:
                warnings.append(
                    ParseWarning(
                        line_number=line_number,
                        message="Empty speaker name",
                        raw_line=raw_line,
                    )
                )
                cur_speaker = None
                cur_text_parts = []
                cur_line_number = 0
                continue

            cur_text_parts = [match.group(2).rstrip()]
            cur_line_number = line_number
        elif cur_speaker is not None:
            # Continuation of the current utterance.
            cur_text_parts.append(raw_line.strip())
        else:
            # Orphan line before any speaker has appeared.
            warnings.append(
                ParseWarning(
                    line_number=line_number,
                    message="Line does not match expected format and no prior speaker context",
                    raw_line=raw_line,
                )
            )

    # Flush the last utterance.
    _flush_current()

    # Build ordered-unique speakers list preserving first-appearance order.
    speakers = list(dict.fromkeys(u.speaker for u in utterances))

    return TranscriptParseResult(
        utterances=utterances,
        speakers=speakers,
        warnings=warnings,
        source=source,
    )


def parse_transcript_file(file_path: str | Path) -> TranscriptParseResult:
    """Parse a transcript file into structured data.

    Reads the file at *file_path* as UTF-8 text and delegates to
    :func:`parse_transcript`.

    Args:
        file_path: Path to the transcript file.  Accepts both
            :class:`str` and :class:`~pathlib.Path`.

    Returns:
        A :class:`TranscriptParseResult` with ``source`` set to the
        string representation of *file_path*.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Transcript file not found: {path}")

    text = path.read_text(encoding="utf-8")
    return parse_transcript(text, source=str(path))
