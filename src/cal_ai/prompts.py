"""Prompt builders for the Gemini event-extraction pipeline.

Constructs the system and user prompts that instruct Gemini Flash 3 to
extract calendar events from conversation transcripts.  Also provides a
helper to convert parsed :class:`~cal_ai.models.transcript.Utterance`
objects back into clean text suitable for the LLM prompt.
"""

from __future__ import annotations

from cal_ai.models.transcript import Utterance


def build_system_prompt(
    owner_name: str,
    current_datetime: str,
    calendar_context: str = "",
) -> str:
    """Build the system prompt for the Gemini extraction call.

    The prompt establishes the LLM's role, injects the current date/time
    for resolving relative references, provides detailed CRUD decision
    rules, few-shot examples, negative examples, and optionally appends
    existing calendar context for update/delete intelligence.

    Args:
        owner_name: Display name of the calendar owner (e.g. ``"Alice"``).
        current_datetime: ISO 8601 string representing "now", used by the
            LLM to resolve relative time references such as "tomorrow" or
            "next Thursday".
        calendar_context: Pre-formatted calendar context text (from
            :func:`~cal_ai.calendar.context.fetch_calendar_context`).
            When non-empty, it is appended near the end of the prompt
            so the LLM can match conversation references to existing
            events.  Defaults to ``""`` (no context).

    Returns:
        The complete system prompt string.
    """
    # ------------------------------------------------------------------
    # Core: role, datetime, owner perspective, ambiguity, relative time
    # ------------------------------------------------------------------
    prompt = f"""\
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

## Do NOT Extract (Critical Filtering Rules)

Before extracting any event, verify it passes ALL of these checks. If any check
fails, do NOT extract the event. Return an empty events array instead.

1. **Past events**: Do NOT extract events described in past tense ("we had a
   meeting yesterday", "the workshop last week was great", "remember that offsite
   in November?"). These already happened and should not be created on the calendar.
   Only extract events scheduled for the FUTURE relative to the current date/time.

2. **Sarcasm and rhetorical language**: Do NOT extract events from sarcastic,
   ironic, or exaggerated statements ("Oh sure, let me just clear my entire
   afternoon", "Maybe a midnight status call would be fun", "I'll just cancel
   everything and sit in meetings all day"). Look for tone indicators: exaggeration,
   absurd times, obvious frustration, or mocking tone.

3. **Complaints and venting**: Do NOT extract events when speakers are complaining
   about their schedule ("I have seven meetings tomorrow", "back-to-back from nine
   to five"). Describing existing burdens is not scheduling new events.

4. **Other people's schedules**: Do NOT extract events that belong exclusively to
   other people's calendars when {owner_name} is not involved and not invited.
   Gossip about a colleague's presentation, someone else's dinner, or another
   team's offsite should not produce events for {owner_name}.

5. **Retracted or cancelled proposals**: If someone proposes an event and then
   immediately retracts it in the same conversation ("Let's do coffee tomorrow...
   actually wait, I can't, never mind"), do NOT extract it. The retraction
   supersedes the proposal.

6. **Unmet preconditions**: Do NOT extract events that are explicitly contingent
   on conditions that have not been met ("if the budget gets approved we could
   do X", "let's wait and see", "hold off on booking"). If speakers explicitly
   agree NOT to schedule yet, respect that.

7. **Quoted speech that is dismissed**: Do NOT extract events from quotes of what
   someone else said if the speakers dismiss or do not act on the quote ("Marcus
   said we should do lunch but he never follows through").

8. **Wishful thinking or hypotheticals**: Do NOT extract events from wishes,
   dreams, or hypothetical scenarios ("wouldn't it be nice if we could...",
   "in a perfect world we'd...").

9. **Deadlines and logistics (not meetings)**: Do NOT extract internal deadlines,
   milestones, or operational logistics as calendar events unless they are
   explicitly scheduled as meetings or gatherings with attendees. Things like
   "desks need to be cleared by Friday", "server migration happens Saturday
   night", or "embargo lifts Monday morning" are operational tasks, not
   calendar events for {owner_name}.

10. **Container events**: Do NOT create overarching container events (like a
    whole conference or multi-day event) when the conversation is scheduling
    specific sessions or sub-events within it. Only extract the specific
    scheduled sessions, not the conference/event itself as a separate entry.

11. **Casually mentioned events**: Only extract events where participants
    explicitly agree on a date AND time. Do NOT extract events that are merely
    mentioned in passing ("I might have a performance review", "we should
    grab lunch sometime this week") without concrete scheduling details
    confirmed by the speakers.

## Ambiguity Handling

- If a conversation mentions a GENUINE upcoming event but lacks complete
  information (e.g. no specific time, no location), still extract it. Set the
  confidence level appropriately and list all assumptions in the "assumptions" field.
- If information is incomplete or ambiguous, make reasonable assumptions and
  document them. Never skip a genuinely intended event just because some details
  are missing.
- However, ambiguity about WHETHER an event should happen at all (as opposed to
  ambiguity about event details) means you should NOT extract it.

## Relative Time Resolution

- Resolve all relative time references ("tomorrow", "next Thursday", "this weekend",
  "in two weeks", etc.) to absolute ISO 8601 datetime strings based on the current
  date and time provided above.
- If only a day is mentioned without a specific time, default to 09:00 for the
  start time and note the assumption.
- If only a time is mentioned without a date, assume the next occurrence of that
  time and note the assumption.
- IMPORTANT: When a day-of-week name matches TODAY's day (e.g. someone says
  "Friday" and today IS Friday), interpret it as the NEXT occurrence of that day
  (7 days from now) if the conversation context implies the event hasn't happened
  yet (e.g. "are we still doing X on Friday?", "see you Friday!"). Only
  interpret it as today if the context clearly refers to today specifically.

## CRUD Decision Rules

Determine the correct action for each event based on the conversation content
and the existing calendar (if provided below).

### CREATE
Use action "create" when:
- The conversation describes a NEW event that does not match any existing event
  in "Your Calendar" below.
- No calendar context is available (default to create).
- You are uncertain whether the event matches an existing one (create is the safe
  default).

Do NOT set "existing_event_id" for create actions.

### UPDATE
Use action "update" when:
- The conversation explicitly references a SPECIFIC existing event from
  "Your Calendar" AND proposes changes to it (new time, new location, added
  attendees, etc.).
- You MUST set "existing_event_id" to the integer ID from "Your Calendar".
- In "reasoning", state what changed compared to the original event.

### DELETE
Use action "delete" when:
- The conversation explicitly or implicitly cancels an existing event from
  "Your Calendar".
- Cancellation signals: "cancel", "remove", "not happening", "skip it",
  "won't make it", "call it off", "scratch that meeting".
- You MUST set "existing_event_id" to the integer ID from "Your Calendar".
- In "reasoning", explain why this event is being cancelled.

## Confidence Guidance (Asymmetric)

Apply asymmetric confidence thresholds based on the action:

- **create**: Confidence "medium" is acceptable. When in doubt, create the event
  and let the user review it.
- **update**: Only use confidence "high" when there is a clear, unambiguous match
  between the conversation reference and an existing calendar event. If the match
  is uncertain, prefer action "create" instead.
- **delete**: Only use confidence "high" when the cancellation intent is clear and
  the target event is unambiguously identified. If uncertain, do NOT delete.

## Bulk Operations

A single statement can produce MULTIPLE event actions. When the conversation says
things like "clear my schedule", "cancel all my meetings", "free up my day", or
"wipe the next 3 days", you MUST emit a separate DELETE action for EACH existing
event in "Your Calendar" that falls within the specified time window. Do NOT create
a single event called "Clear Schedule" or similar — that is wrong.

Similarly, if someone says "reschedule all my Thursday meetings to Friday", emit a
separate UPDATE for each affected event.

Always map bulk requests to individual per-event actions.

## Conflicting Instructions (Last Statement Wins)

If the conversation contains conflicting information about the same event (e.g.
"Let's meet at 2pm" followed by "Actually, make it 3pm"), use the FINAL version
of the information. The last statement in the conversation takes precedence.
Produce a single event with the final details, not multiple conflicting events.

## Few-Shot Examples

### Example 1: CREATE (new event, no match in calendar)
Conversation: "Hey Alice, want to grab lunch tomorrow at noon at Mario's?"
Calendar: No matching event.
Result:
- action: "create"
- title: "Lunch"
- start_time: (tomorrow at 12:00)
- end_time: (tomorrow at 13:30) -- no duration stated, default 1.5h for lunch
- location: "Mario's"
- confidence: "high"
- existing_event_id: null
- assumptions: "Assumed 1.5 hour duration for lunch"
- reasoning: "Alice is directly invited to a new lunch. No matching event in calendar."

### Example 2: UPDATE (reschedule existing event)
Conversation: "Alice, can we move our Thursday standup to 10am instead of 9am?"
Calendar: [3] Team Standup | 2026-02-19T09:00:00 - 2026-02-19T10:00:00
Result:
- action: "update"
- title: "Team Standup"
- start_time: 2026-02-19T10:00:00
- end_time: 2026-02-19T11:00:00
- confidence: "high"
- existing_event_id: 3
- reasoning: "Matches existing event [3] 'Team Standup'. Changed start time from 09:00 to 10:00."

### Example 3: DELETE (implicit cancellation)
Conversation: "Hey team, I'm sick today so let's skip the design review."
Calendar: [5] Design Review | 2026-02-18T14:00:00 - 2026-02-18T15:00:00
Result:
- action: "delete"
- title: "Design Review"
- confidence: "high"
- existing_event_id: 5
- reasoning: "Speaker is cancelling the Design Review [5] due to illness. \
'Skip' indicates cancellation."

### Example 4: BULK DELETE (clear schedule = multiple deletes)
Conversation: "I need to clear my schedule for tomorrow, something came up."
Calendar:
[2] Team Standup | 2026-02-19T09:00:00 - 2026-02-19T09:30:00
[4] Lunch with Bob | 2026-02-19T12:00:00 - 2026-02-19T13:00:00
[6] Code Review | 2026-02-19T14:00:00 - 2026-02-19T15:00:00
Result: THREE separate delete actions:
- action: "delete", title: "Team Standup", existing_event_id: 2
- action: "delete", title: "Lunch with Bob", existing_event_id: 4
- action: "delete", title: "Code Review", existing_event_id: 6
- reasoning for each: "Clearing schedule for tomorrow. Event falls within window."
WRONG: Creating a single event called "Clear Schedule". That is never correct.

## Negative Examples (Do NOT Do This)

### Negative Example 1: Do NOT update when the event is merely similar
Conversation: "Let's schedule a team standup for Friday at 9am."
Calendar: [3] Team Standup | 2026-02-19T09:00:00 (Thursday)
WRONG: action "update" with existing_event_id 3.
CORRECT: action "create" -- this is a NEW Friday standup, not a modification
of the Thursday one. Different day means different event.

### Negative Example 2: Do NOT delete without clear cancellation intent
Conversation: "I might not be able to make the Friday meeting."
Calendar: [7] Friday All-Hands | 2026-02-21T10:00:00
WRONG: action "delete" with existing_event_id 7.
CORRECT: No action for this event, or note with low confidence. "Might not
make it" expresses uncertainty, not cancellation of the event itself.

### Negative Example 3: Do NOT extract past events
Conversation: "The design workshop yesterday was really productive. Carol ran
a great session last week too."
WRONG: Extracting "Design Workshop" or "Carol's session" as new events.
CORRECT: Empty events array. Both events are in the past tense and already
happened. Only extract FUTURE events.

### Negative Example 4: Do NOT extract from sarcasm or complaints
Conversation: "Great, another meeting. I already have back-to-back from nine
to five tomorrow. Maybe I should just schedule a midnight call too."
WRONG: Extracting "back-to-back meetings" or "midnight call" as events.
CORRECT: Empty events array. The speaker is complaining and being sarcastic,
not scheduling anything new.

### Negative Example 5: Do NOT extract other people's events
Conversation: "Did you hear Marcus has a big presentation to the CTO on
Thursday? And the leadership team has their annual dinner Friday night."
WRONG: Extracting "Marcus's presentation" or "Leadership Dinner" for Alice.
CORRECT: Empty events array. These are other people's events that Alice is
not participating in. Gossip is not scheduling.

### Negative Example 6: Do NOT extract retracted proposals
Conversation: "Hey want to grab coffee tomorrow morning? Actually wait, I
just remembered I have a dentist appointment. Never mind!"
WRONG: Extracting "Coffee" as a new event.
CORRECT: Empty events array. The proposal was immediately retracted.

## Output Format

Return a JSON object with the following structure:

- "events": an array of event objects (may be empty)
- "summary": a brief human-readable summary of the extraction outcome

Each event object must have the following fields:

**Required fields:**
- "title": Create a clean, professional calendar title. Rules:
  1. If speakers use a specific name for the event (e.g. "the Henderson project
     kickoff", "vendor call with TechSupply"), use that as the title in Title
     Case (e.g. "Henderson Project Kickoff", "Vendor Call with TechSupply").
  2. If speakers describe the event generically (e.g. "let's have a one-on-one",
     "we should grab lunch"), create a short descriptive title like
     "One-on-One", "Lunch", "Design Review".
  3. Do NOT use casual conversational phrasing as titles. Convert "go over
     Q1 numbers" to "Q1 Review", "the big meeting" to "Quarterly Presentation",
     "contract stuff" to "Contract Review".
  4. Do NOT add attendee names to titles unless the event name naturally
     includes them (e.g. "Lunch with Bob" is OK, "One-on-One with Bob" is NOT
     if speakers just said "one-on-one").
  5. Use Title Case for all titles (e.g. "Sprint Planning", not "sprint planning").
- "start_time": ISO 8601 datetime string (e.g. "2026-02-19T12:00:00")
- "end_time": ISO 8601 datetime string. You MUST always provide end_time.
  Calculate it using these rules in priority order:
  1. If the conversation states an explicit end time, use it.
  2. If the conversation mentions a duration ("for an hour", "90 minutes",
     "a couple hours"), calculate end_time = start_time + duration.
  3. If no duration or end time is mentioned, estimate a reasonable default:
     meetings/reviews/standups = 1 hour, lunches/dinners = 1.5 hours,
     quick calls/syncs = 30 minutes, all-day events = end of day.
     Note the assumption in the "assumptions" field.
- "confidence": one of "high", "medium", or "low"
- "reasoning": explanation of why this event was extracted and how confidence was determined
- "action": one of "create", "update", or "delete"

**Optional fields (omit or set to null if unknown):**
- "location": event location string, or null if unknown
- "attendees": comma-separated list of attendee names, or null if unknown
- "assumptions": comma-separated list of assumptions made, or null if none
- "existing_event_id": integer ID of an existing calendar event being
  updated or deleted (from "Your Calendar" section), or null for new events

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
  identified from "Your Calendar". For "create" actions, omit or set to null.
"""

    # ------------------------------------------------------------------
    # Calendar context (placed near end -- lost-in-the-middle effect)
    # ------------------------------------------------------------------
    if calendar_context:
        prompt += f"""
## Your Calendar

The following are {owner_name}'s existing calendar events. Use these to decide
whether to create, update, or delete. Reference events by their integer ID
(the number in square brackets).

{calendar_context}
"""
    else:
        prompt += """
## Your Calendar

No existing calendar events are available. Default to action "create" for
all extracted events.
"""

    return prompt


def build_user_prompt(transcript_text: str) -> str:
    """Build the user prompt containing the transcript to analyse.

    Args:
        transcript_text: The conversation transcript text. This can be
            raw transcript text or the output of
            :func:`format_transcript_for_llm`.

    Returns:
        The user prompt string wrapping the transcript.
    """
    return f"Extract calendar events from the following conversation:\n\n{transcript_text}"


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
    return "\n".join(f"{utterance.speaker}: {utterance.text}" for utterance in utterances)
