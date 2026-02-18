"""Unit tests for the transcript parser (40 tests).

Tests cover: happy path, multi-line utterances, empty/whitespace input,
malformed input, speaker label edge cases, Unicode, colon/bracket edge
cases, large input, and logging.
"""

from __future__ import annotations

import logging
import time

import pytest

from cal_ai.parser import parse_transcript

# ---------------------------------------------------------------------------
# Happy Path (6 tests)
# ---------------------------------------------------------------------------


class TestHappyPath:
    """Basic parsing scenarios that follow the expected format."""

    def test_parse_spec_example(self) -> None:
        """SPEC.md example transcript produces 3 utterances, 2 speakers, 0 warnings."""
        text = (
            "[Alice]: Hey, want to grab lunch Thursday at noon?\n"
            "[Bob]: Sure, how about that new place on 5th?\n"
            "[Alice]: Perfect, see you there."
        )

        result = parse_transcript(text)

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

    def test_parse_single_utterance(self) -> None:
        """A single speaker line yields 1 utterance with correct fields."""
        result = parse_transcript("[Alice]: Hello")

        assert len(result.utterances) == 1
        assert result.utterances[0].speaker == "Alice"
        assert result.utterances[0].text == "Hello"
        assert result.utterances[0].line_number == 1

    def test_parse_two_speakers(self) -> None:
        """Two different speakers yield 2 utterances with correct fields."""
        text = "[Alice]: Hello\n[Bob]: Hi there"

        result = parse_transcript(text)

        assert len(result.utterances) == 2
        assert result.utterances[0].speaker == "Alice"
        assert result.utterances[0].text == "Hello"
        assert result.utterances[0].line_number == 1
        assert result.utterances[1].speaker == "Bob"
        assert result.utterances[1].text == "Hi there"
        assert result.utterances[1].line_number == 2

    def test_speakers_list_ordered_by_first_appearance(self) -> None:
        """Speakers list preserves first-appearance order, no duplicates."""
        text = "[Alice]: First\n[Bob]: Second\n[Alice]: Third"

        result = parse_transcript(text)

        assert result.speakers == ["Alice", "Bob"]

    def test_source_default(self) -> None:
        """Default source is '<string>' when none is provided."""
        result = parse_transcript("[Alice]: Hello")

        assert result.source == "<string>"

    def test_source_custom(self) -> None:
        """Custom source is preserved in the result."""
        result = parse_transcript("[Alice]: Hello", source="my_file.txt")

        assert result.source == "my_file.txt"


# ---------------------------------------------------------------------------
# Multi-line Utterances (4 tests)
# ---------------------------------------------------------------------------


class TestMultilineUtterances:
    """Non-matching lines after a speaker line are continuations."""

    def test_multiline_continuation(self) -> None:
        """Continuation lines are joined to the current utterance with newlines."""
        text = "[Alice]: I was thinking\nwe could meet up\non Saturday."

        result = parse_transcript(text)

        assert len(result.utterances) == 1
        assert result.utterances[0].text == "I was thinking\nwe could meet up\non Saturday."
        assert len(result.warnings) == 0

    def test_multiline_then_new_speaker(self) -> None:
        """Multi-line Alice followed by Bob yields 2 utterances."""
        text = "[Alice]: Let me think about\nthat for a moment.\n[Bob]: Take your time."

        result = parse_transcript(text)

        assert len(result.utterances) == 2
        assert result.utterances[0].speaker == "Alice"
        assert result.utterances[0].text == "Let me think about\nthat for a moment."
        assert result.utterances[1].speaker == "Bob"
        assert result.utterances[1].text == "Take your time."

    def test_multiline_with_blank_lines_between(self) -> None:
        """Blank lines between continuation lines are skipped, not appended."""
        text = "[Alice]: First line\n\nSecond line after blank"

        result = parse_transcript(text)

        assert len(result.utterances) == 1
        assert result.utterances[0].text == "First line\nSecond line after blank"
        assert len(result.warnings) == 0

    def test_multiline_indented_continuation(self) -> None:
        """Continuation with leading whitespace is stripped."""
        text = "[Alice]: Main point\n   indented continuation"

        result = parse_transcript(text)

        assert len(result.utterances) == 1
        assert result.utterances[0].text == "Main point\nindented continuation"


# ---------------------------------------------------------------------------
# Empty and Whitespace Input (3 tests)
# ---------------------------------------------------------------------------


class TestEmptyInput:
    """Empty or whitespace-only input yields empty results with no warnings."""

    def test_parse_empty_string(self) -> None:
        """Empty string produces an empty result with no warnings."""
        result = parse_transcript("")

        assert result.utterances == []
        assert result.speakers == []
        assert result.warnings == []

    def test_parse_whitespace_only(self) -> None:
        """Whitespace-only input produces an empty result with no warnings."""
        result = parse_transcript("   \n  \n\t")

        assert result.utterances == []
        assert result.speakers == []
        assert result.warnings == []

    def test_parse_only_blank_lines(self) -> None:
        """Multiple newlines produce an empty result with no warnings."""
        result = parse_transcript("\n\n\n")

        assert result.utterances == []
        assert result.speakers == []
        assert result.warnings == []


# ---------------------------------------------------------------------------
# Malformed Input (7 tests)
# ---------------------------------------------------------------------------


class TestMalformedInput:
    """Lines that do not match the speaker format generate warnings or continuations."""

    def test_malformed_missing_closing_bracket(self) -> None:
        """Missing ']' means no match: orphan line warning."""
        result = parse_transcript("[Alice: Hello")

        assert len(result.utterances) == 0
        assert len(result.warnings) == 1
        assert result.warnings[0].line_number == 1
        assert result.warnings[0].raw_line == "[Alice: Hello"

    def test_malformed_missing_opening_bracket(self) -> None:
        """Missing '[' means no match: orphan line warning."""
        result = parse_transcript("Alice]: Hello")

        assert len(result.utterances) == 0
        assert len(result.warnings) == 1
        assert result.warnings[0].line_number == 1

    def test_malformed_no_colon(self) -> None:
        """Missing ':' after brackets means no match: orphan line warning."""
        result = parse_transcript("[Alice] Hello")

        assert len(result.utterances) == 0
        assert len(result.warnings) == 1
        assert result.warnings[0].line_number == 1

    def test_malformed_no_brackets_at_all(self) -> None:
        """Plain text with no speaker format: orphan line warning."""
        result = parse_transcript("Alice said hello")

        assert len(result.utterances) == 0
        assert len(result.warnings) == 1
        assert result.warnings[0].line_number == 1

    def test_malformed_line_before_first_speaker(self) -> None:
        """Orphan text before first speaker produces a warning; speaker line is parsed."""
        text = "Some orphan text\n[Alice]: Hi"

        result = parse_transcript(text)

        assert len(result.utterances) == 1
        assert result.utterances[0].speaker == "Alice"
        assert len(result.warnings) == 1
        assert result.warnings[0].line_number == 1

    def test_malformed_line_between_speakers(self) -> None:
        """Garbled text between speakers is treated as continuation of the previous speaker."""
        text = "[Alice]: Hi\nsome garbled text\n[Bob]: Hey"

        result = parse_transcript(text)

        assert len(result.utterances) == 2
        assert result.utterances[0].speaker == "Alice"
        assert result.utterances[0].text == "Hi\nsome garbled text"
        assert result.utterances[1].speaker == "Bob"
        assert len(result.warnings) == 0

    def test_entirely_malformed_input(self) -> None:
        """Multiple non-matching lines produce multiple warnings."""
        text = "line one\nline two\nline three"

        result = parse_transcript(text)

        assert len(result.utterances) == 0
        assert len(result.warnings) == 3


# ---------------------------------------------------------------------------
# Speaker Label Edge Cases (8 tests)
# ---------------------------------------------------------------------------


class TestSpeakerLabelEdgeCases:
    """Edge cases in speaker name formatting."""

    def test_speaker_with_no_text(self) -> None:
        """Speaker with colon but no text: text is empty string."""
        result = parse_transcript("[Alice]:")

        assert len(result.utterances) == 1
        assert result.utterances[0].speaker == "Alice"
        assert result.utterances[0].text == ""

    def test_speaker_with_only_whitespace_text(self) -> None:
        """Speaker with only whitespace after colon: text is stripped to empty."""
        result = parse_transcript("[Alice]:   ")

        assert len(result.utterances) == 1
        assert result.utterances[0].speaker == "Alice"
        assert result.utterances[0].text == ""

    def test_speaker_name_with_spaces(self) -> None:
        """Speaker name with internal spaces is preserved."""
        result = parse_transcript("[Dr. Jane Smith]: Hello")

        assert len(result.utterances) == 1
        assert result.utterances[0].speaker == "Dr. Jane Smith"

    def test_speaker_name_with_special_characters(self) -> None:
        """Speaker name with special characters is preserved."""
        result = parse_transcript("[O'Brien (host)]: Welcome")

        assert len(result.utterances) == 1
        assert result.utterances[0].speaker == "O'Brien (host)"

    def test_speaker_name_with_numbers(self) -> None:
        """Speaker names with numbers are parsed correctly."""
        text = "[Speaker 1]: Hello\n[Speaker 2]: Hi"

        result = parse_transcript(text)

        assert result.speakers == ["Speaker 1", "Speaker 2"]

    def test_speaker_name_trimmed(self) -> None:
        """Whitespace around speaker name inside brackets is trimmed."""
        result = parse_transcript("[ Alice ]: Hello")

        assert len(result.utterances) == 1
        assert result.utterances[0].speaker == "Alice"

    def test_consecutive_same_speaker(self) -> None:
        """Consecutive utterances from the same speaker are NOT merged."""
        text = "[Alice]: First thing\n[Alice]: Second thing"

        result = parse_transcript(text)

        assert len(result.utterances) == 2
        assert result.utterances[0].text == "First thing"
        assert result.utterances[1].text == "Second thing"

    def test_many_speakers(self) -> None:
        """Five or more speakers are all captured in first-appearance order."""
        text = "[Alice]: One\n[Bob]: Two\n[Charlie]: Three\n[Diana]: Four\n[Eve]: Five"

        result = parse_transcript(text)

        assert len(result.utterances) == 5
        assert result.speakers == ["Alice", "Bob", "Charlie", "Diana", "Eve"]


# ---------------------------------------------------------------------------
# Unicode (3 tests)
# ---------------------------------------------------------------------------


class TestUnicode:
    """Unicode characters in speaker names and dialogue text."""

    def test_unicode_speaker_name(self) -> None:
        """Unicode speaker name is preserved."""
        result = parse_transcript("[Ren\u00e9]: Bonjour")

        assert result.utterances[0].speaker == "Ren\u00e9"

    def test_unicode_dialogue_text(self) -> None:
        """Unicode dialogue text is preserved."""
        result = parse_transcript("[Alice]: Caf\u00e9 at 3\u2019s")

        assert result.utterances[0].text == "Caf\u00e9 at 3\u2019s"

    def test_cjk_characters(self) -> None:
        """CJK characters in speaker names and text are parsed correctly."""
        result = parse_transcript("[\u7530\u4e2d\u592a\u90ce]: \u5143\u6c17\u3067\u3059\u3002")

        assert result.utterances[0].speaker == "\u7530\u4e2d\u592a\u90ce"
        assert result.utterances[0].text == "\u5143\u6c17\u3067\u3059\u3002"


# ---------------------------------------------------------------------------
# Colon/Bracket Edge Cases (4 tests)
# ---------------------------------------------------------------------------


class TestColonBracketEdgeCases:
    """Edge cases involving colons and brackets within the content."""

    def test_colon_in_dialogue_text(self) -> None:
        """Colon inside dialogue text does not interfere with parsing."""
        result = parse_transcript("[Alice]: Time is 3:00 PM")

        assert result.utterances[0].text == "Time is 3:00 PM"

    def test_brackets_in_dialogue_text(self) -> None:
        """Brackets inside dialogue text are included verbatim."""
        result = parse_transcript("[Alice]: He said [wow]")

        assert result.utterances[0].text == "He said [wow]"

    def test_nested_brackets_in_speaker(self) -> None:
        """Nested brackets in speaker position are handled gracefully.

        The regex ``^\\[(.+?)\\]:\\s*(.*)$`` with non-greedy capture on
        ``[[Editor]]: Note``: the outer ``[`` is consumed by the literal
        ``\\[``, then ``.+?`` captures ``[Editor]`` (the shortest match
        that reaches ``]:\\s*``), yielding speaker ``[Editor]`` and text
        ``Note``. This is accepted behaviour for an unusual edge case.
        """
        result = parse_transcript("[[Editor]]: Note")

        assert len(result.utterances) == 1
        assert result.utterances[0].speaker == "[Editor]"
        assert result.utterances[0].text == "Note"

    def test_empty_brackets(self) -> None:
        """Empty brackets '[]' do not match the regex and produce a warning.

        The regex requires ``.+?`` (at least one character) inside brackets,
        so ``[]: Hello`` does not match and is treated as an orphan line.
        """
        result = parse_transcript("[]: Hello")

        assert len(result.utterances) == 0
        assert len(result.warnings) == 1
        assert result.warnings[0].line_number == 1
        assert result.warnings[0].raw_line == "[]: Hello"


# ---------------------------------------------------------------------------
# Large Input (2 tests)
# ---------------------------------------------------------------------------


class TestLargeInput:
    """Performance and correctness with large inputs."""

    def test_very_long_line(self) -> None:
        """A single utterance with 10,000+ characters is parsed and preserved."""
        long_text = "x" * 10_001
        text = f"[Alice]: {long_text}"

        result = parse_transcript(text)

        assert len(result.utterances) == 1
        assert result.utterances[0].text == long_text

    def test_many_utterances(self) -> None:
        """1,000 utterances parse correctly with proper line numbers in < 1 second."""
        lines = [f"[Speaker{i}]: Message number {i}" for i in range(1_000)]
        text = "\n".join(lines)

        start = time.monotonic()
        result = parse_transcript(text)
        elapsed = time.monotonic() - start

        assert len(result.utterances) == 1_000
        assert result.utterances[0].line_number == 1
        assert result.utterances[999].line_number == 1_000
        assert elapsed < 1.0, f"Parsing 1,000 utterances took {elapsed:.2f}s (limit: 1.0s)"


# ---------------------------------------------------------------------------
# Logging (3 tests)
# ---------------------------------------------------------------------------


class TestLogging:
    """Verify that the parser emits expected log messages."""

    def test_logging_on_successful_parse(self, caplog: pytest.LogCaptureFixture) -> None:
        """Successful parse emits INFO with utterance and speaker counts."""
        text = (
            "[Alice]: Hey, want to grab lunch Thursday at noon?\n"
            "[Bob]: Sure, how about that new place on 5th?\n"
            "[Alice]: Perfect, see you there."
        )

        with caplog.at_level(logging.INFO, logger="cal_ai.parser"):
            parse_transcript(text)

        assert any(
            "3 utterance(s)" in record.message and "2 speaker(s)" in record.message
            for record in caplog.records
        ), f"Expected utterance/speaker count in logs, got: {[r.message for r in caplog.records]}"

    def test_logging_on_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Malformed line emits WARNING with line number and raw line."""
        with caplog.at_level(logging.WARNING, logger="cal_ai.parser"):
            parse_transcript("garbled text here")

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) >= 1
        msg = warning_records[0].message
        assert "1" in msg  # line number
        assert "garbled text here" in msg

    def test_logging_on_empty_input(self, caplog: pytest.LogCaptureFixture) -> None:
        """Empty input emits INFO message about empty transcript."""
        with caplog.at_level(logging.INFO, logger="cal_ai.parser"):
            parse_transcript("")

        assert any("Empty transcript" in record.message for record in caplog.records), (
            f"Expected 'Empty transcript' in logs, got: {[r.message for r in caplog.records]}"
        )
