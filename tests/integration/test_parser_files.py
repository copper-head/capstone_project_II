"""Integration tests for file-based transcript parsing (7 tests).

These tests exercise :func:`~cal_ai.parser.parse_transcript_file` against
the fixture files in ``tests/fixtures/``, verifying end-to-end behaviour
including file I/O, encoding, and error handling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cal_ai.parser import parse_transcript_file

# Resolve the fixtures directory relative to this test file.
_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class TestParserFiles:
    """Integration tests for parse_transcript_file against fixture files."""

    def test_parse_spec_example_file(self) -> None:
        """sample_transcript.txt produces 3 utterances, 2 speakers, 0 warnings."""
        fixture = _FIXTURES / "sample_transcript.txt"

        result = parse_transcript_file(fixture)

        assert len(result.utterances) == 3
        assert result.utterances[0].speaker == "Alice"
        assert result.utterances[0].text == "Hey, want to grab lunch Thursday at noon?"
        assert result.utterances[0].line_number == 1
        assert result.utterances[1].speaker == "Bob"
        assert result.utterances[1].text == "Sure, how about that new place on 5th?"
        assert result.utterances[1].line_number == 2
        assert result.utterances[2].speaker == "Alice"
        assert result.utterances[2].text == "Perfect, see you there."
        assert result.utterances[2].line_number == 3
        assert result.speakers == ["Alice", "Bob"]
        assert len(result.warnings) == 0
        assert result.source == str(fixture)

    def test_parse_multiline_file(self) -> None:
        """multiline_transcript.txt parses multi-line utterances correctly."""
        fixture = _FIXTURES / "multiline_transcript.txt"

        result = parse_transcript_file(fixture)

        assert len(result.utterances) == 3
        assert result.speakers == ["Alice", "Bob"]

        # First utterance: Alice with continuation lines.
        assert result.utterances[0].speaker == "Alice"
        assert result.utterances[0].line_number == 1
        assert "meet up this weekend" in result.utterances[0].text
        assert "Saturday afternoon?" in result.utterances[0].text

        # Second utterance: Bob with continuation lines.
        assert result.utterances[1].speaker == "Bob"
        assert result.utterances[1].line_number == 5
        assert "Saturday works" in result.utterances[1].text
        assert "budget section" in result.utterances[1].text

        # Third utterance: Alice again.
        assert result.utterances[2].speaker == "Alice"
        assert result.utterances[2].line_number == 9
        assert "coffee shop" in result.utterances[2].text

        assert len(result.warnings) == 0

    def test_parse_malformed_file(self) -> None:
        """malformed_transcript.txt produces warnings for bad lines and parses valid ones."""
        fixture = _FIXTURES / "malformed_transcript.txt"

        result = parse_transcript_file(fixture)

        # Lines 1-4 are orphan/malformed (before first speaker), line 5 is
        # [Alice], line 6 is continuation of Alice, line 7 is [Bob].
        assert len(result.utterances) == 2
        assert result.utterances[0].speaker == "Alice"
        assert result.utterances[1].speaker == "Bob"

        # First 4 lines are orphan (no prior speaker context) -> 4 warnings.
        assert len(result.warnings) == 4
        assert result.warnings[0].line_number == 1
        assert result.warnings[0].raw_line == "This line has no speaker label at all."

    def test_parse_empty_file(self) -> None:
        """empty_transcript.txt produces an empty result with no warnings."""
        fixture = _FIXTURES / "empty_transcript.txt"

        result = parse_transcript_file(fixture)

        assert result.utterances == []
        assert result.speakers == []
        assert result.warnings == []

    def test_parse_unicode_file(self) -> None:
        """unicode_transcript.txt preserves Unicode speakers and text."""
        fixture = _FIXTURES / "unicode_transcript.txt"

        result = parse_transcript_file(fixture)

        assert len(result.utterances) == 3
        assert result.speakers == ["Ren\u00e9", "\u7530\u4e2d\u592a\u90ce"]

        assert result.utterances[0].speaker == "Ren\u00e9"
        assert result.utterances[0].text == "Bonjour, comment allez-vous?"
        assert result.utterances[1].speaker == "\u7530\u4e2d\u592a\u90ce"
        assert "\u5143\u6c17\u3067\u3059" in result.utterances[1].text
        assert result.utterances[2].speaker == "Ren\u00e9"

        assert len(result.warnings) == 0

    def test_parse_nonexistent_file(self) -> None:
        """A nonexistent file path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_transcript_file("does/not/exist.txt")

    def test_parse_file_source_field(self) -> None:
        """result.source equals the string representation of the file path."""
        fixture = _FIXTURES / "sample_transcript.txt"

        result = parse_transcript_file(fixture)

        assert result.source == str(fixture)
