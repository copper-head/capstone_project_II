# fn-7-1hq.4 Write CRUD and Multi-Speaker category samples with sidecars

## Description
Write 8+ CRUD category samples and 5+ Multi-Speaker category samples, each with a sidecar `.expected.json` file containing mock LLM response, expected events, calendar context (for CRUD), and tolerance level.

**Size:** M
**Files:** `samples/crud/*.txt` + `*.expected.json` (8+ pairs), `samples/multi_speaker/*.txt` + `*.expected.json` (5+ pairs)

## Approach

**CRUD samples (8+):**
- `bulk_delete.txt` — "clear my schedule" / "cancel everything tomorrow" (strict, 2+ delete actions)
- `partial_update.txt` — change time but keep location (strict, 1 update action with calendar_context)
- `conflicting_instructions.txt` — reschedule then cancel same event (moderate, tests last-instruction-wins)
- `ambiguous_reference.txt` — multiple possible calendar matches (moderate, calendar_context with similar events)
- `update_no_match.txt` — update references non-existent event, should fall back to create (moderate)
- `delete_already_gone.txt` — delete event not in calendar (relaxed, idempotent success)
- `reschedule_recurring.txt` — move a recurring meeting instance (moderate)
- `create_with_conflict.txt` — create event overlapping existing calendar event (strict)
- Each sidecar must include `calendar_context` array with mock existing events and integer IDs
- Each sidecar must include `mock_llm_response` — a valid JSON dict matching `LLMResponseSchema`

**Multi-Speaker samples (5+):**
- `five_speakers_crosstalk.txt` — 5+ speakers, cross-talk, multiple events from different pairs (relaxed)
- `side_conversation.txt` — 2 people plan something while 3 others discuss unrelated (moderate)
- `reference_others_calendar.txt` — "Bob, don't forget your dentist" (moderate, tests owner perspective)
- `multiple_pairs_events.txt` — different speaker pairs each plan distinct events (moderate)
- `speakers_disagree.txt` — speakers disagree on event details (relaxed)
- Multi-speaker samples should use diverse speaker names and test owner-perspective filtering

## Key context

- LLMResponseSchema at `src/cal_ai/models/extraction.py` — `{"events": [...], "summary": "..."}`
- Each event in mock_llm_response: `{"title": "...", "start_time": "...", "end_time": "...", "location": "...", "attendees": "comma,separated", "confidence": "high|medium|low", "reasoning": "...", "assumptions": "comma,separated", "action": "create|update|delete", "existing_event_id": null|int}`
- Note: LLM returns attendees/assumptions as comma-separated strings, NOT lists (the parser splits them)
- Calendar context IDs are integers (1, 2, 3...) — never expose real Google UUIDs to LLM
- Even spread of lengths: some short (5 lines), some medium (15-20 lines)
- Use `[Speaker Name]: dialogue text` format, blank lines between turns
## Acceptance
- [ ] 8+ CRUD sample pairs (.txt + .expected.json) in `samples/crud/`
- [ ] 5+ Multi-Speaker sample pairs in `samples/multi_speaker/`
- [ ] Each sidecar validates against SidecarSpec Pydantic model
- [ ] CRUD sidecars include calendar_context with realistic mock events
- [ ] mock_llm_response in each sidecar is valid LLMResponseSchema JSON
- [ ] Attendees/assumptions in mock_llm_response are comma-separated strings (not lists)
- [ ] Even mix of conversation lengths (short/medium)
- [ ] Scenarios from spec are all covered: bulk deletes, partial updates, conflicting, ambiguous, no-match, already-deleted, 5+ speakers, side conversations, cross-calendar references
## Done summary
- Task completed
## Evidence
- Commits:
- Tests:
- PRs: