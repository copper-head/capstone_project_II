"""Unit tests for sample transcript validation (6 tests).

Tests verify: all sample files exist, each is parseable by the transcript
parser, expected speaker counts, utterance counts, and content
characteristics.
"""

from __future__ import annotations

from pathlib import Path

from cal_ai.parser import parse_transcript_file

SAMPLES_DIR = Path("samples")

EXPECTED_FILES = [
    "simple_lunch.txt",
    "multiple_events.txt",
    "cancellation.txt",
    "ambiguous_time.txt",
    "no_events.txt",
    "complex.txt",
]


class TestSampleTranscripts:
    """Validate that all sample transcript files are present and well-formed."""

    def test_all_sample_files_exist(self) -> None:
        """All 6 sample transcript files are present in samples/."""
        for name in EXPECTED_FILES:
            assert (SAMPLES_DIR / name).exists(), f"Missing sample file: {name}"

    def test_sample_files_are_parseable(self) -> None:
        """Each sample file is parseable by the transcript parser without exceptions."""
        for name in EXPECTED_FILES:
            result = parse_transcript_file(SAMPLES_DIR / name)
            assert result.utterances is not None, f"{name}: returned None utterances"
            assert len(result.utterances) > 0, f"{name}: returned 0 utterances"

    def test_simple_lunch_has_expected_speakers(self) -> None:
        """simple_lunch.txt has at least 2 distinct speakers."""
        result = parse_transcript_file(SAMPLES_DIR / "simple_lunch.txt")
        assert len(result.speakers) >= 2, (
            f"Expected at least 2 speakers, got {len(result.speakers)}: {result.speakers}"
        )

    def test_multiple_events_has_enough_content(self) -> None:
        """multiple_events.txt has at least 6 utterances."""
        result = parse_transcript_file(SAMPLES_DIR / "multiple_events.txt")
        assert len(result.utterances) >= 6, (
            f"Expected at least 6 utterances, got {len(result.utterances)}"
        )

    def test_complex_has_multiple_speakers(self) -> None:
        """complex.txt has at least 3 distinct speakers."""
        result = parse_transcript_file(SAMPLES_DIR / "complex.txt")
        assert len(result.speakers) >= 3, (
            f"Expected at least 3 speakers, got {len(result.speakers)}: {result.speakers}"
        )

    def test_no_events_is_casual_conversation(self) -> None:
        """no_events.txt parses successfully and contains no scheduling keywords."""
        result = parse_transcript_file(SAMPLES_DIR / "no_events.txt")
        assert len(result.utterances) > 0, "no_events.txt should have utterances"

        # Combine all utterance text and check for scheduling-related keywords.
        full_text = " ".join(u.text.lower() for u in result.utterances)
        scheduling_keywords = ["meeting", "schedule", "calendar", "appointment"]
        for keyword in scheduling_keywords:
            assert keyword not in full_text, (
                f"Casual conversation file should not contain scheduling keyword '{keyword}'"
            )
