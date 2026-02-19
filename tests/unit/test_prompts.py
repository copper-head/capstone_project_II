"""Unit tests for the prompt builders (18 tests).

Covers ``build_system_prompt``, ``build_user_prompt``, and
``format_transcript_for_llm`` from :mod:`cal_ai.prompts`.

Test matrix:
- build_system_prompt basics (6): owner name, datetime, perspective,
  ambiguity, relative time, JSON format
- CRUD decision rules (4): create rules, update rules, delete rules,
  all three actions present
- Asymmetric confidence (1): create=medium OK, update/delete=high
- Few-shot examples (1): at least 2 examples present
- Negative examples (1): at least 1 negative example present
- Calendar context (2): with context appended, without context default
- Last-statement-wins (1): instruction present
- build_user_prompt (1): transcript embedded
- format_transcript_for_llm (2): normal + empty list
"""

from __future__ import annotations

from cal_ai.models.transcript import Utterance
from cal_ai.prompts import (
    build_system_prompt,
    build_user_prompt,
    format_transcript_for_llm,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OWNER = "Alice"
_DATETIME = "2026-02-18T10:00:00"

_SAMPLE_CALENDAR_CONTEXT = (
    "[1] Team Standup | 2026-02-19T09:00:00 - 2026-02-19T10:00:00\n"
    "[2] Lunch with Bob | 2026-02-19T12:00:00 - 2026-02-19T13:00:00"
)


def _prompt(**kwargs: str) -> str:
    """Build a system prompt with defaults for owner and datetime."""
    return build_system_prompt(
        owner_name=kwargs.get("owner_name", _OWNER),
        current_datetime=kwargs.get("current_datetime", _DATETIME),
        calendar_context=kwargs.get("calendar_context", ""),
    )


# ---------------------------------------------------------------------------
# build_system_prompt -- basics (6 tests, same as before)
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    """Tests for the system prompt builder -- basic sections."""

    def test_build_system_prompt_contains_owner_name(self) -> None:
        """Owner name appears in the generated system prompt."""
        prompt = _prompt()

        assert "Alice" in prompt

    def test_build_system_prompt_contains_current_datetime(self) -> None:
        """Current date/time is injected into the system prompt."""
        prompt = _prompt()

        assert "2026-02-18" in prompt

    def test_build_system_prompt_contains_perspective_instructions(self) -> None:
        """System prompt includes owner perspective filtering rules."""
        prompt = _prompt()
        prompt_lower = prompt.lower()

        assert "perspective" in prompt_lower or "owner" in prompt_lower
        assert "high" in prompt_lower
        assert "low" in prompt_lower
        assert "overhear" in prompt_lower or "not directly involved" in prompt_lower

    def test_build_system_prompt_contains_ambiguity_instructions(self) -> None:
        """System prompt includes instructions for handling incomplete information."""
        prompt = _prompt()
        prompt_lower = prompt.lower()

        assert "assumption" in prompt_lower or "ambig" in prompt_lower
        assert "incomplete" in prompt_lower or "missing" in prompt_lower

    def test_build_system_prompt_contains_relative_time_instructions(self) -> None:
        """System prompt tells the LLM how to resolve relative dates."""
        prompt = _prompt()
        prompt_lower = prompt.lower()

        assert "relative" in prompt_lower or "tomorrow" in prompt_lower
        assert "resolve" in prompt_lower or "iso 8601" in prompt_lower

    def test_build_system_prompt_contains_json_format_instructions(self) -> None:
        """System prompt describes the expected JSON output fields."""
        prompt = _prompt()

        for field_name in ("title", "start_time", "confidence", "reasoning"):
            assert field_name in prompt, f"Expected field '{field_name}' in system prompt"

        prompt_lower = prompt.lower()
        assert "json" in prompt_lower
        assert "events" in prompt_lower


# ---------------------------------------------------------------------------
# build_system_prompt -- CRUD decision rules (4 tests)
# ---------------------------------------------------------------------------


class TestCrudDecisionRules:
    """CRUD decision rules are clearly defined in the prompt."""

    def test_create_rules_present(self) -> None:
        """CREATE action rules are in the prompt."""
        prompt = _prompt()

        assert "### CREATE" in prompt
        assert '"create"' in prompt.lower() or "create" in prompt.lower()
        # Should mention that create is the default / safe action
        assert "default" in prompt.lower() or "safe" in prompt.lower()

    def test_update_rules_present(self) -> None:
        """UPDATE action rules require existing_event_id."""
        prompt = _prompt()

        assert "### UPDATE" in prompt
        assert "existing_event_id" in prompt
        # Should mention matching an existing event
        assert "existing event" in prompt.lower() or "your calendar" in prompt.lower()

    def test_delete_rules_present(self) -> None:
        """DELETE action rules include cancellation signal words."""
        prompt = _prompt()

        assert "### DELETE" in prompt
        # Should list cancellation signals
        prompt_lower = prompt.lower()
        assert "cancel" in prompt_lower
        assert "skip" in prompt_lower

    def test_all_three_actions_defined(self) -> None:
        """All three CRUD actions (create, update, delete) are defined."""
        prompt = _prompt()

        for action_heading in ("### CREATE", "### UPDATE", "### DELETE"):
            assert action_heading in prompt, (
                f"Expected '{action_heading}' section in prompt"
            )


# ---------------------------------------------------------------------------
# build_system_prompt -- asymmetric confidence (1 test)
# ---------------------------------------------------------------------------


class TestAsymmetricConfidence:
    """Asymmetric confidence guidance (create=medium, update/delete=high)."""

    def test_asymmetric_confidence_guidance(self) -> None:
        """Create allows medium confidence; update/delete require high."""
        prompt = _prompt()
        prompt_lower = prompt.lower()

        # The prompt should have a section about asymmetric confidence
        assert "asymmetric" in prompt_lower or "confidence guidance" in prompt_lower

        # Create should accept medium confidence
        assert "create" in prompt_lower and "medium" in prompt_lower

        # Update/delete should require high confidence for clear matches
        assert "update" in prompt_lower and "high" in prompt_lower
        assert "delete" in prompt_lower and "high" in prompt_lower


# ---------------------------------------------------------------------------
# build_system_prompt -- few-shot examples (1 test)
# ---------------------------------------------------------------------------


class TestFewShotExamples:
    """At least 2 few-shot examples (create + update or delete)."""

    def test_few_shot_examples_present(self) -> None:
        """Prompt contains at least 2 few-shot examples with action types."""
        prompt = _prompt()

        # Count example sections
        example_count = prompt.count("### Example")
        assert example_count >= 2, (
            f"Expected at least 2 few-shot examples, found {example_count}"
        )

        # Should have a CREATE example and an UPDATE or DELETE example
        prompt_lower = prompt.lower()
        assert "example" in prompt_lower and "create" in prompt_lower
        # At least one of update or delete
        has_update_example = "update" in prompt_lower and "existing_event_id" in prompt_lower
        has_delete_example = "delete" in prompt_lower and "existing_event_id" in prompt_lower
        assert has_update_example or has_delete_example


# ---------------------------------------------------------------------------
# build_system_prompt -- negative examples (1 test)
# ---------------------------------------------------------------------------


class TestNegativeExamples:
    """At least 1 negative example present."""

    def test_negative_examples_present(self) -> None:
        """Prompt contains at least 1 negative example showing what NOT to do."""
        prompt = _prompt()

        # Count negative example sections
        negative_count = prompt.count("### Negative Example")
        assert negative_count >= 1, (
            f"Expected at least 1 negative example, found {negative_count}"
        )

        # Should explicitly say "do not" or "wrong"
        prompt_lower = prompt.lower()
        assert "wrong" in prompt_lower or "do not" in prompt_lower


# ---------------------------------------------------------------------------
# build_system_prompt -- calendar context (2 tests)
# ---------------------------------------------------------------------------


class TestCalendarContext:
    """Calendar context section placed near end of prompt."""

    def test_calendar_context_appended_when_provided(self) -> None:
        """Calendar events text is injected into 'Your Calendar' section."""
        prompt = build_system_prompt(
            owner_name=_OWNER,
            current_datetime=_DATETIME,
            calendar_context=_SAMPLE_CALENDAR_CONTEXT,
        )

        assert "## Your Calendar" in prompt
        assert "Team Standup" in prompt
        assert "Lunch with Bob" in prompt
        assert "[1]" in prompt
        assert "[2]" in prompt

        # Calendar context should be placed AFTER the examples section
        # (near end of prompt -- lost-in-the-middle effect)
        examples_pos = prompt.find("## Few-Shot Examples")
        calendar_pos = prompt.find("## Your Calendar")
        assert calendar_pos > examples_pos, (
            "Calendar context must appear after examples section"
        )

    def test_calendar_context_default_message_when_empty(self) -> None:
        """Without calendar context, prompt says 'default to create'."""
        prompt = _prompt(calendar_context="")

        assert "## Your Calendar" in prompt
        prompt_lower = prompt.lower()
        assert "no existing calendar events" in prompt_lower or "default" in prompt_lower


# ---------------------------------------------------------------------------
# build_system_prompt -- last-statement-wins (1 test)
# ---------------------------------------------------------------------------


class TestLastStatementWins:
    """Last-statement-wins instruction for conflicting information."""

    def test_last_statement_wins_instruction(self) -> None:
        """Prompt tells the LLM to use the final version when there are conflicts."""
        prompt = _prompt()
        prompt_lower = prompt.lower()

        assert "last statement" in prompt_lower or "final version" in prompt_lower
        assert "conflicting" in prompt_lower or "conflict" in prompt_lower


# ---------------------------------------------------------------------------
# build_system_prompt -- accepts calendar_context parameter (1 test)
# ---------------------------------------------------------------------------


class TestCalendarContextParameter:
    """build_system_prompt accepts calendar_context as optional parameter."""

    def test_accepts_calendar_context_parameter(self) -> None:
        """Function signature accepts calendar_context with default empty string."""
        # Call with no calendar_context -- should use default
        prompt_no_ctx = build_system_prompt(
            owner_name=_OWNER, current_datetime=_DATETIME
        )
        assert isinstance(prompt_no_ctx, str)

        # Call with calendar_context -- should include it
        prompt_with_ctx = build_system_prompt(
            owner_name=_OWNER,
            current_datetime=_DATETIME,
            calendar_context=_SAMPLE_CALENDAR_CONTEXT,
        )
        assert isinstance(prompt_with_ctx, str)
        assert len(prompt_with_ctx) > len(prompt_no_ctx)


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
