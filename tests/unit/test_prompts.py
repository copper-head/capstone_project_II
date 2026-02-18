"""Unit tests for the prompt builders (8 tests).

Covers ``build_system_prompt``, ``build_user_prompt``, and
``format_transcript_for_llm`` from :mod:`cal_ai.prompts`.
"""

from __future__ import annotations

from cal_ai.models.transcript import Utterance
from cal_ai.prompts import (
    build_system_prompt,
    build_user_prompt,
    format_transcript_for_llm,
)

# ---------------------------------------------------------------------------
# build_system_prompt tests
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    """Tests for the system prompt builder."""

    def test_build_system_prompt_contains_owner_name(self) -> None:
        """Owner name appears in the generated system prompt."""
        prompt = build_system_prompt(owner_name="Alice", current_datetime="2026-02-18T10:00:00")

        assert "Alice" in prompt

    def test_build_system_prompt_contains_current_datetime(self) -> None:
        """Current date/time is injected into the system prompt."""
        prompt = build_system_prompt(owner_name="Alice", current_datetime="2026-02-18T10:00:00")

        assert "2026-02-18" in prompt

    def test_build_system_prompt_contains_perspective_instructions(self) -> None:
        """System prompt includes owner perspective filtering rules."""
        prompt = build_system_prompt(owner_name="Alice", current_datetime="2026-02-18T10:00:00")
        prompt_lower = prompt.lower()

        assert "perspective" in prompt_lower or "owner" in prompt_lower
        # More specific: the prompt should explain confidence based on involvement
        assert "high" in prompt_lower
        assert "low" in prompt_lower
        assert "overhear" in prompt_lower or "not directly involved" in prompt_lower

    def test_build_system_prompt_contains_ambiguity_instructions(self) -> None:
        """System prompt includes instructions for handling incomplete information."""
        prompt = build_system_prompt(owner_name="Alice", current_datetime="2026-02-18T10:00:00")
        prompt_lower = prompt.lower()

        assert "assumption" in prompt_lower or "ambig" in prompt_lower
        assert "incomplete" in prompt_lower or "missing" in prompt_lower

    def test_build_system_prompt_contains_relative_time_instructions(self) -> None:
        """System prompt tells the LLM how to resolve relative dates."""
        prompt = build_system_prompt(owner_name="Alice", current_datetime="2026-02-18T10:00:00")
        prompt_lower = prompt.lower()

        # Should mention resolving relative references
        assert "relative" in prompt_lower or "tomorrow" in prompt_lower
        assert "resolve" in prompt_lower or "iso 8601" in prompt_lower

    def test_build_system_prompt_contains_json_format_instructions(self) -> None:
        """System prompt describes the expected JSON output fields."""
        prompt = build_system_prompt(owner_name="Alice", current_datetime="2026-02-18T10:00:00")

        # Core field names must be mentioned
        for field_name in ("title", "start_time", "confidence", "reasoning"):
            assert field_name in prompt, f"Expected field '{field_name}' in system prompt"

        # The prompt should mention JSON and the events array
        prompt_lower = prompt.lower()
        assert "json" in prompt_lower
        assert "events" in prompt_lower


# ---------------------------------------------------------------------------
# build_user_prompt tests
# ---------------------------------------------------------------------------


class TestBuildUserPrompt:
    """Tests for the user prompt builder."""

    def test_build_user_prompt_contains_transcript(self) -> None:
        """Full transcript text is embedded in the returned user prompt."""
        transcript = (
            "Alice: Hey, want to grab lunch Thursday at noon?\n"
            "Bob: Sure, how about that new place on 5th?"
        )

        prompt = build_user_prompt(transcript)

        assert transcript in prompt
        # Should also contain framing text
        assert "extract" in prompt.lower() or "calendar" in prompt.lower()


# ---------------------------------------------------------------------------
# format_transcript_for_llm tests
# ---------------------------------------------------------------------------


class TestFormatTranscriptForLlm:
    """Tests for the utterance-to-text formatter."""

    def test_format_transcript_for_llm(self) -> None:
        """Parsed Utterance objects are converted to clean 'Speaker: text' lines."""
        utterances = [
            Utterance(speaker="Alice", text="Hey, want to grab lunch?", line_number=1),
            Utterance(speaker="Bob", text="Sure, how about noon?", line_number=2),
            Utterance(speaker="Alice", text="Perfect.", line_number=3),
        ]

        result = format_transcript_for_llm(utterances)

        expected = (
            "Alice: Hey, want to grab lunch?\n"
            "Bob: Sure, how about noon?\n"
            "Alice: Perfect."
        )
        assert result == expected

    def test_format_transcript_for_llm_empty_list(self) -> None:
        """An empty utterance list produces an empty string."""
        result = format_transcript_for_llm([])

        assert result == ""
