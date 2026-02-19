"""Prompt builders for the Gemini event-extraction pipeline.

Constructs the system and user prompts that instruct Gemini Flash 3 to
extract calendar events from conversation transcripts.  Also provides a
helper to convert parsed :class:`~cal_ai.models.transcript.Utterance`
objects back into clean text suitable for the LLM prompt.
"""

from __future__ import annotations

from cal_ai.models.transcript import Utterance


def build_system_prompt(owner_name: str, current_datetime: str) -> str:
    """Build the system prompt for the Gemini extraction call.

    The prompt establishes the LLM's role, injects the current date/time
    for resolving relative references, and provides detailed instructions
    on owner-perspective filtering, ambiguity handling, confidence levels,
    and output format.

    Args:
        owner_name: Display name of the calendar owner (e.g. ``"Alice"``).
        current_datetime: ISO 8601 string representing "now", used by the
            LLM to resolve relative time references such as "tomorrow" or
            "next Thursday".

    Returns:
        The complete system prompt string.
    """
    return f"""\
You are an AI assistant that extracts calendar events from conversation transcripts.
You are extracting calendar events for {owner_name}. All events should be evaluated
from {owner_name}'s perspective as the calendar owner.

## Current Date and Time

The current date and time is: {current_datetime}
Use this to resolve any relative time references in the conversation.

## Owner Perspective Rules

- Events where {owner_name} directly participates or is explicitly invited should
  have confidence "high".
- Events where {owner_name} is mentioned as a potential attendee but not confirmed
  should have confidence "medium".
- Events that {owner_name} merely overhears others discussing (without being
  involved) should have confidence "low". Still extract these, but note in the
  reasoning that {owner_name} was not directly involved.

## Ambiguity Handling

- If a conversation mentions a possible event but lacks complete information (e.g.
  no specific time, no location), still extract it. Set the confidence level
  appropriately and list all assumptions in the "assumptions" field.
- If information is incomplete or ambiguous, make reasonable assumptions and
  document them. Never skip an event just because some details are missing.

## Relative Time Resolution

- Resolve all relative time references ("tomorrow", "next Thursday", "this weekend",
  "in two weeks", etc.) to absolute ISO 8601 datetime strings based on the current
  date and time provided above.
- If only a day is mentioned without a specific time, default to 09:00 for the
  start time and note the assumption.
- If only a time is mentioned without a date, assume the next occurrence of that
  time and note the assumption.

## Output Format

Return a JSON object with the following structure:

- "events": an array of event objects (may be empty)
- "summary": a brief human-readable summary of the extraction outcome

Each event object must have the following fields:

**Required fields:**
- "title": a short descriptive title for the event
- "start_time": ISO 8601 datetime string (e.g. "2026-02-19T12:00:00")
- "confidence": one of "high", "medium", or "low"
- "reasoning": explanation of why this event was extracted and how confidence was determined
- "action": one of "create", "update", or "delete" (default to "create" for new events)

**Optional fields (omit or set to null if unknown):**
- "end_time": ISO 8601 datetime string, or null if unknown
- "location": event location string, or null if unknown
- "attendees": comma-separated list of attendee names, or null if unknown
- "assumptions": comma-separated list of assumptions made, or null if none
- "existing_event_id": integer ID of an existing calendar event being
  updated or deleted, or null for new events

## Confidence Level Guidelines

- "high": The event has a clear date/time, {owner_name} is directly involved,
  and details are explicit in the conversation.
- "medium": The event is likely but some details are ambiguous or {owner_name}'s
  involvement is not fully confirmed.
- "low": The event is speculative, vaguely mentioned, or {owner_name} is not
  directly involved.

## Empty Results

If the conversation contains no calendar-relevant information, return an empty
events array with a summary explaining why no events were found.

## Important Notes

- For optional fields where the value is not available, omit the field or
  set it to null. Do NOT use the string "none" as a placeholder.
- For the "attendees" field, use a comma-separated string of names.
  Include {owner_name} in the attendees list when they are participating.
- For the "assumptions" field, use a comma-separated string of assumptions.
  Omit or set to null if no assumptions were made.
- For the "existing_event_id" field, only provide an integer ID when the
  action is "update" or "delete" and a matching existing event has been
  identified. For "create" actions, omit or set to null.
"""


def build_user_prompt(transcript_text: str) -> str:
    """Build the user prompt containing the transcript to analyse.

    Args:
        transcript_text: The conversation transcript text. This can be
            raw transcript text or the output of
            :func:`format_transcript_for_llm`.

    Returns:
        The user prompt string wrapping the transcript.
    """
    return (
        "Extract calendar events from the following conversation:\n\n"
        f"{transcript_text}"
    )


def format_transcript_for_llm(utterances: list[Utterance]) -> str:
    """Convert parsed utterances into clean text for the LLM prompt.

    Each utterance is formatted as ``Speaker: text`` on its own line,
    producing a clean, readable transcript without the bracket notation
    used in the raw input format.

    Args:
        utterances: Parsed utterance objects from the transcript parser.

    Returns:
        A newline-separated string of ``Speaker: text`` lines.  Returns
        an empty string if *utterances* is empty.
    """
    return "\n".join(
        f"{utterance.speaker}: {utterance.text}" for utterance in utterances
    )
