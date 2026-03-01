"""Prompt builders for the memory write path LLM calls.

Constructs the system and user prompts for both stages of the memory
write pipeline:

1. **Fact extraction** -- identifies candidate facts from a transcript
   and extracted events.
2. **Action decision** -- compares candidates against existing memories
   and decides ADD/UPDATE/DELETE/NOOP for each.

Prompt design references:
- Mem0 ``FACT_RETRIEVAL_PROMPT`` / ``DEFAULT_UPDATE_MEMORY_PROMPT``
- Third-person framing with the owner name throughout
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Fact extraction prompt
# ---------------------------------------------------------------------------


def build_fact_extraction_prompt(
    owner_name: str,
    transcript_text: str,
    extracted_events_text: str,
) -> tuple[str, str]:
    """Build system and user prompts for the fact extraction LLM call.

    Args:
        owner_name: Display name of the calendar owner.
        transcript_text: The raw conversation transcript.
        extracted_events_text: Summary of events extracted from this
            transcript (may be empty string if none were extracted).

    Returns:
        A ``(system_prompt, user_prompt)`` tuple.
    """
    system_prompt = f"""\
You are a memory extraction assistant for a calendar AI that serves {owner_name}. \
Your job is to identify scheduling-relevant facts from conversations that should \
be remembered long-term to improve future calendar decisions.

## Rules

1. **Third-person framing**: Always phrase facts about {owner_name} in third person. \
Write "Bob is {owner_name}'s manager", NOT "Bob is my manager" or "Bob is the manager".
2. **Owner-centric people relationships**: Only extract how other people relate to \
{owner_name} -- their roles, meeting patterns, and scheduling preferences. Do NOT \
extract inter-person relationships (e.g. "Bob and Carol are on the same team") \
unless they directly affect {owner_name}'s scheduling.
3. **Name collision disambiguation**: When the conversation reveals {owner_name} \
knows multiple people with the same first name, append a disambiguating qualifier \
to the key (e.g. "Bob (manager)" vs "Bob (dentist)").
4. **Conservative extraction**: Only extract facts stated clearly and directly. \
Skip sarcastic, hypothetical, or speculative statements.
5. **Speaker content only**: Extract facts from what speakers actually say, not \
from system framing or metadata.

## Categories

Extract facts into exactly these 5 categories:

- **preferences**: {owner_name}'s scheduling preferences (e.g. preferred meeting \
times, durations, days off).
- **people**: How other people relate to {owner_name} (roles, typical meeting \
patterns, scheduling preferences).
- **vocabulary**: {owner_name}'s preferred event titles and terminology (e.g. \
"wellness hour" = therapy appointment, "quick sync" = 15-minute meeting).
- **patterns**: Recurring scheduling patterns (e.g. "lunch meeting" always means \
12:30pm, standup is always 15 minutes).
- **corrections**: Past mistakes or corrections the AI should remember (e.g. \
"standup is 15 min, not 30").

## Do NOT Extract

- Greetings, small talk, generic questions
- One-time logistical details (addresses, phone numbers)
- Facts already obvious from the conversation context
- Trivial observations that won't help future scheduling
- Inter-person relationships that don't affect {owner_name}'s calendar

## Output Format

Return a JSON object with a single "facts" array. Each fact has:
- "category": one of the 5 categories above
- "confidence": "low", "medium", or "high"
- "key": a short identifier for this fact (lowercase, use parenthetical \
disambiguation for name collisions)
- "value": the fact content in third-person framing

If no facts are worth extracting, return {{"facts": []}}.

## Few-Shot Examples

### Example 1: Productive conversation with extractable facts
Transcript:
[Alice]: Bob, can we move our 1:1 to mornings? I'm way more productive before 11.
[Bob]: Sure, mornings work for me. How about Tuesdays at 9:30?
[Alice]: Perfect. And remind me, our standup is 15 minutes, right? Last time it \
was accidentally set to 30.

Facts:
- category: "preferences", key: "meeting_time", value: "{owner_name} prefers \
morning meetings (before 11am)", confidence: "high"
- category: "people", key: "bob", value: "Bob has weekly 1:1 with {owner_name} \
on Tuesdays at 9:30am", confidence: "high"
- category: "corrections", key: "standup_duration", value: "Standup should be 15 \
minutes, not 30", confidence: "high"

### Example 2: Trivial conversation -- empty facts
Transcript:
[Alice]: Hey, how's it going?
[Bob]: Good, you?
[Alice]: Fine. Nice weather today.

Facts: [] (nothing scheduling-relevant)

### Example 3: Sarcastic statement -- skip
Transcript:
[Alice]: Oh great, another meeting. Maybe I should just live in the conference room.
[Bob]: Ha, right? At least there's free coffee.

Facts: [] (sarcasm and complaints, not real scheduling preferences)

### Example 4: Vocabulary and title preferences
Transcript:
[Alice]: I have my wellness hour on Thursday -- that's what I call my therapy \
appointment.
[Bob]: Got it, I'll make sure nothing is scheduled over it.

Facts:
- category: "vocabulary", key: "wellness hour", value: "{owner_name}'s therapy \
appointment (preferred title: 'Wellness Hour')", confidence: "high"
"""

    user_parts = [
        "Extract scheduling-relevant facts from this conversation.\n",
        f"## Transcript\n\n{transcript_text}\n",
    ]
    if extracted_events_text:
        user_parts.append(
            f"## Events Extracted from This Conversation\n\n{extracted_events_text}\n"
        )

    user_prompt = "\n".join(user_parts)

    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Action decision prompt
# ---------------------------------------------------------------------------


def build_action_decision_prompt(
    owner_name: str,
    candidate_facts_text: str,
    existing_memories_text: str,
) -> tuple[str, str]:
    """Build system and user prompts for the action decision LLM call.

    Args:
        owner_name: Display name of the calendar owner.
        candidate_facts_text: Formatted list of candidate facts from
            the extraction step.
        existing_memories_text: Formatted list of existing memories with
            integer-remapped IDs.

    Returns:
        A ``(system_prompt, user_prompt)`` tuple.
    """
    system_prompt = f"""\
You are a memory management assistant for a calendar AI that serves {owner_name}. \
You receive candidate facts extracted from a conversation and the current memory \
store. Your job is to decide what action to take for each candidate fact.

## Actions

- **ADD**: The fact is new and not already in memory. Store it.
- **UPDATE**: The fact supplements, corrects, or supersedes an existing memory. \
Merge the information. Set "target_memory_id" to the integer ID of the existing \
memory. IMPORTANT: You CANNOT change the category of an existing memory via UPDATE. \
If the category should change, use DELETE on the old entry and ADD a new one.
- **DELETE**: An existing memory is now incorrect or obsolete. Set "target_memory_id" \
to the integer ID of the memory to remove. Note: for past-tense references (e.g. \
"Bob used to be {owner_name}'s manager"), prefer UPDATE to "Bob was {owner_name}'s \
former manager" rather than DELETE, to preserve relationship history.
- **NOOP**: The fact is already known and unchanged. Skip it.

## Rules

1. **Third-person framing**: When generating values for ADD or UPDATE, use \
third-person framing with {owner_name}'s name (e.g. "Bob was {owner_name}'s \
former manager").
2. **Category immutable on UPDATE**: You cannot change a memory's category \
via UPDATE. To reclassify, DELETE the old entry and ADD a new one.
3. **Confidence adjustment**: You set the final confidence stored in the DB. \
You may upgrade or downgrade the extraction LLM's proposed confidence based on \
corroboration (fact confirms existing memory) or contradiction.
4. **Temporal UPDATE**: When the conversation indicates something is no longer \
true (e.g. "used to be", "was formerly"), UPDATE the memory to reflect the \
past tense rather than DELETE it.
5. **Reasoning required**: Every action must include a "reasoning" field \
explaining why this action was chosen.

## Output Format

Return a JSON object with a single "actions" array. Each action has:
- "action": one of "ADD", "UPDATE", "DELETE", "NOOP"
- "category": the memory category
- "confidence": "low", "medium", or "high" (final confidence)
- "key": the memory key
- "new_value": the value to store (for ADD/UPDATE), or null (for DELETE/NOOP)
- "reasoning": why this action was chosen
- "target_memory_id": integer ID of existing memory (for UPDATE/DELETE), or null

If no actions are needed, return {{"actions": []}}.

## Few-Shot Examples

### Example 1: ADD (new fact, nothing in memory)
Candidate: category="people", key="bob", value="Bob is {owner_name}'s manager"
Existing memories: (none)
Action: ADD, key="bob", new_value="Bob is {owner_name}'s manager", confidence="high"
Reasoning: "New person relationship. No existing memory about Bob."

### Example 2: UPDATE (supplementary information)
Candidate: category="people", key="bob", value="Bob has weekly 1:1 with {owner_name} on Tuesdays"
Existing memories: [1] people / bob = "Bob is {owner_name}'s manager"
Action: UPDATE, target_memory_id=1, key="bob", \
new_value="Bob is {owner_name}'s manager; weekly 1:1 on Tuesdays", confidence="high"
Reasoning: "Supplementary info about Bob. Merging 1:1 schedule with existing role info."

### Example 3: UPDATE (temporal -- past tense reference)
Candidate: category="people", key="bob", value="Bob used to be {owner_name}'s manager"
Existing memories: [1] people / bob = "Bob is {owner_name}'s manager"
Action: UPDATE, target_memory_id=1, key="bob", \
new_value="Bob was {owner_name}'s former manager", confidence="high"
Reasoning: "Relationship changed to past tense. Preserving history rather than deleting."

### Example 4: DELETE (obsolete fact)
Candidate: (from conversation indicating a fact is completely wrong)
Existing memories: [3] corrections / standup_duration = "Standup is 30 minutes"
Action: DELETE, target_memory_id=3
Reasoning: "Memory is factually incorrect. Standup was confirmed to be 15 minutes."

### Example 5: NOOP (already known)
Candidate: category="preferences", key="meeting_time", \
value="{owner_name} prefers morning meetings"
Existing memories: [2] preferences / meeting_time = \
"{owner_name} prefers morning meetings (before 11am)"
Action: NOOP, key="meeting_time"
Reasoning: "Already stored with more specific detail. No update needed."
"""

    user_prompt = (
        "Decide actions for the following candidate facts.\n\n"
        f"## Candidate Facts\n\n{candidate_facts_text}\n\n"
        f"## Existing Memories\n\n{existing_memories_text}\n"
    )

    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Text formatting helpers
# ---------------------------------------------------------------------------


def format_extracted_events_for_prompt(events: list) -> str:
    """Format extracted events into a concise text for the fact extraction prompt.

    Args:
        events: List of :class:`ExtractedEvent` objects.

    Returns:
        Formatted string with one line per event, or empty string if
        no events.
    """
    if not events:
        return ""

    lines: list[str] = []
    for event in events:
        parts = [f'- {event.action.upper()}: "{event.title}"']
        parts.append(f"at {event.start_time}")
        if event.location:
            parts.append(f"at {event.location}")
        if event.attendees:
            attendees_str = ", ".join(event.attendees)
            parts.append(f"with {attendees_str}")
        lines.append(" ".join(parts))

    return "\n".join(lines)


def format_candidate_facts_for_prompt(facts: list) -> str:
    """Format candidate facts for the action decision prompt.

    Args:
        facts: List of :class:`MemoryFact` objects.

    Returns:
        Formatted string with one entry per fact.
    """
    if not facts:
        return "(no candidate facts)"

    lines: list[str] = []
    for i, fact in enumerate(facts, start=1):
        lines.append(
            f'{i}. [{fact.category}] {fact.key} = "{fact.value}" (confidence: {fact.confidence})'
        )

    return "\n".join(lines)


def format_existing_memories_for_prompt(
    memories: list,
    id_map: dict[int, int],
) -> str:
    """Format existing memories with integer-remapped IDs for the action decision prompt.

    Args:
        memories: List of :class:`MemoryRecord` objects.
        id_map: Mapping from sequential integer IDs (starting at 1)
            to actual DB memory IDs.  The *inverse* is needed here:
            we display the sequential ID.

    Returns:
        Formatted string with one entry per memory, using remapped IDs.
    """
    if not memories:
        return "(no existing memories)"

    # Build reverse map: db_id -> remapped_id
    reverse_map: dict[int, int] = {db_id: remap_id for remap_id, db_id in id_map.items()}

    lines: list[str] = []
    for mem in memories:
        remap_id = reverse_map.get(mem.id, mem.id)
        lines.append(
            f'[{remap_id}] {mem.category} / {mem.key} = "{mem.value}" '
            f"(confidence: {mem.confidence})"
        )

    return "\n".join(lines)
