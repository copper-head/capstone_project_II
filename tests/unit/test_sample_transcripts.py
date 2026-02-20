"""Unit tests for sample transcript validation (10 tests).

Tests verify: all sample files exist, each is parseable by the transcript
parser, expected speaker counts, utterance counts, content
characteristics, and new CRUD sample transcripts.
"""

from __future__ import annotations

from pathlib import Path

from cal_ai.parser import parse_transcript_file

SAMPLES_DIR = Path("samples")

EXPECTED_FILES = [
    "crud/simple_lunch.txt",
    "crud/update_meeting.txt",
    "crud/cancel_event.txt",
    "crud/cancellation.txt",
    "crud/mixed_crud.txt",
    "crud/clear_schedule.txt",
    "multi_speaker/complex.txt",
    "multi_speaker/multiple_events.txt",
    "adversarial/no_events.txt",
    "realistic/ambiguous_time.txt",
]


class TestSampleTranscripts:
    """Validate that all sample transcript files are present and well-formed."""

    def test_all_sample_files_exist(self) -> None:
        """All 10 sample transcript files are present in samples/."""
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
        result = parse_transcript_file(SAMPLES_DIR / "crud/simple_lunch.txt")
        assert len(result.speakers) >= 2, (
            f"Expected at least 2 speakers, got {len(result.speakers)}: {result.speakers}"
        )

    def test_multiple_events_has_enough_content(self) -> None:
        """multiple_events.txt has at least 6 utterances."""
        result = parse_transcript_file(SAMPLES_DIR / "multi_speaker/multiple_events.txt")
        assert len(result.utterances) >= 6, (
            f"Expected at least 6 utterances, got {len(result.utterances)}"
        )

    def test_complex_has_multiple_speakers(self) -> None:
        """complex.txt has at least 3 distinct speakers."""
        result = parse_transcript_file(SAMPLES_DIR / "multi_speaker/complex.txt")
        assert len(result.speakers) >= 3, (
            f"Expected at least 3 speakers, got {len(result.speakers)}: {result.speakers}"
        )

    def test_no_events_is_casual_conversation(self) -> None:
        """no_events.txt parses successfully and contains no scheduling keywords."""
        result = parse_transcript_file(SAMPLES_DIR / "adversarial/no_events.txt")
        assert len(result.utterances) > 0, "no_events.txt should have utterances"

        # Combine all utterance text and check for scheduling-related keywords.
        full_text = " ".join(u.text.lower() for u in result.utterances)
        scheduling_keywords = ["meeting", "schedule", "calendar", "appointment"]
        for keyword in scheduling_keywords:
            assert keyword not in full_text, (
                f"Casual conversation file should not contain scheduling keyword '{keyword}'"
            )

    def test_update_meeting_has_rescheduling_language(self) -> None:
        """update_meeting.txt contains rescheduling/update language."""
        result = parse_transcript_file(SAMPLES_DIR / "crud/update_meeting.txt")
        assert len(result.utterances) > 0, "update_meeting.txt should have utterances"
        assert len(result.speakers) >= 2, (
            f"Expected at least 2 speakers, got {len(result.speakers)}"
        )
        full_text = " ".join(u.text.lower() for u in result.utterances)
        # Should reference rescheduling an existing event.
        assert "push" in full_text or "move" in full_text or "instead" in full_text, (
            "update_meeting.txt should contain rescheduling language"
        )

    def test_cancel_event_has_cancellation_language(self) -> None:
        """cancel_event.txt contains cancellation language."""
        result = parse_transcript_file(SAMPLES_DIR / "crud/cancel_event.txt")
        assert len(result.utterances) > 0, "cancel_event.txt should have utterances"
        assert len(result.speakers) >= 2, (
            f"Expected at least 2 speakers, got {len(result.speakers)}"
        )
        full_text = " ".join(u.text.lower() for u in result.utterances)
        assert "cancel" in full_text, (
            "cancel_event.txt should contain cancellation language"
        )

    def test_mixed_crud_has_all_action_types(self) -> None:
        """mixed_crud.txt contains create, update, and delete language."""
        result = parse_transcript_file(SAMPLES_DIR / "crud/mixed_crud.txt")
        assert len(result.utterances) >= 6, (
            f"Expected at least 6 utterances, got {len(result.utterances)}"
        )
        assert len(result.speakers) >= 2, (
            f"Expected at least 2 speakers, got {len(result.speakers)}"
        )
        full_text = " ".join(u.text.lower() for u in result.utterances)
        # Should contain language for all three CRUD actions.
        assert "set up" in full_text or "new" in full_text, (
            "mixed_crud.txt should contain create language"
        )
        assert "move" in full_text or "push" in full_text, (
            "mixed_crud.txt should contain update/reschedule language"
        )
        assert "cancel" in full_text, (
            "mixed_crud.txt should contain cancellation language"
        )

    def test_new_crud_samples_use_speaker_format(self) -> None:
        """All new CRUD sample files use [Speaker]: text format."""
        crud_files = ["crud/update_meeting.txt", "crud/cancel_event.txt", "crud/mixed_crud.txt"]
        for name in crud_files:
            result = parse_transcript_file(SAMPLES_DIR / name)
            assert len(result.utterances) > 0, (
                f"{name} should have parseable utterances"
            )
            # Verify all utterances have non-empty speakers.
            for utterance in result.utterances:
                assert utterance.speaker, (
                    f"{name}: utterance has empty speaker: {utterance.text!r}"
                )
