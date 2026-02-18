"""Tests for transcript data models."""

from __future__ import annotations

from cal_ai.models.transcript import ParseWarning, TranscriptParseResult, Utterance


class TestUtterance:
    """Tests for the Utterance dataclass."""

    def test_utterance_creation(self) -> None:
        """Basic instantiation: all fields are accessible."""
        u = Utterance(speaker="Alice", text="Hello there", line_number=1)

        assert u.speaker == "Alice"
        assert u.text == "Hello there"
        assert u.line_number == 1

    def test_utterance_equality(self) -> None:
        """Two Utterances with identical fields are equal."""
        u1 = Utterance(speaker="Alice", text="Hello", line_number=1)
        u2 = Utterance(speaker="Alice", text="Hello", line_number=1)

        assert u1 == u2

    def test_utterance_inequality(self) -> None:
        """Two Utterances with different fields are not equal."""
        u1 = Utterance(speaker="Alice", text="Hello", line_number=1)
        u2 = Utterance(speaker="Bob", text="Hi", line_number=2)

        assert u1 != u2


class TestParseWarning:
    """Tests for the ParseWarning dataclass."""

    def test_parse_warning_creation(self) -> None:
        """Basic instantiation: all fields are set correctly."""
        w = ParseWarning(
            line_number=5,
            message="Line does not match expected format",
            raw_line="some garbled text",
        )

        assert w.line_number == 5
        assert w.message == "Line does not match expected format"
        assert w.raw_line == "some garbled text"


class TestTranscriptParseResult:
    """Tests for the TranscriptParseResult dataclass."""

    def test_transcript_parse_result_creation(self) -> None:
        """All fields are accessible when explicitly provided."""
        u = Utterance(speaker="Alice", text="Hello", line_number=1)
        w = ParseWarning(line_number=3, message="bad line", raw_line="???")

        result = TranscriptParseResult(
            utterances=[u],
            speakers=["Alice"],
            warnings=[w],
            source="test.txt",
        )

        assert result.utterances == [u]
        assert result.speakers == ["Alice"]
        assert result.warnings == [w]
        assert result.source == "test.txt"

    def test_transcript_parse_result_empty(self) -> None:
        """Default construction yields valid empty result."""
        result = TranscriptParseResult()

        assert result.utterances == []
        assert result.speakers == []
        assert result.warnings == []
        assert result.source == "<string>"
