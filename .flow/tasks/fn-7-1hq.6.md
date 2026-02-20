# fn-7-1hq.6 Create sidecars for migrated existing samples

## Description
Create sidecar `.expected.json` files for the 10 existing samples that were migrated in Task 1. Each sidecar needs expected events, tolerance level, mock LLM response, and (for CRUD samples) calendar context.

**Size:** M
**Files:** 10 sidecar `.expected.json` files across `samples/{crud,multi_speaker,adversarial,realistic}/`

## Approach

- For each migrated sample, analyze the transcript content and create a matching sidecar:
  - `crud/simple_lunch.expected.json` — 1 create event, strict, no calendar_context
  - `crud/update_meeting.expected.json` — 1 update event, strict, calendar_context with existing meeting
  - `crud/cancel_event.expected.json` — 1 delete event, strict, calendar_context with existing event
  - `crud/cancellation.expected.json` — 1 delete event, strict, calendar_context
  - `crud/mixed_crud.expected.json` — 3 events (create+update+delete), moderate, calendar_context
  - `crud/clear_schedule.expected.json` — 2+ delete events, moderate, calendar_context with multiple events
  - `multi_speaker/complex.expected.json` — 3-4 events from 4 speakers, moderate
  - `multi_speaker/multiple_events.expected.json` — 3 events, moderate
  - `adversarial/no_events.expected.json` — 0 events, strict
  - `realistic/ambiguous_time.expected.json` — 1 event with vague time, relaxed
- Each sidecar must include `mock_llm_response` with a valid LLM JSON response that matches the expected events
- Use `owner: "Alice"` and `reference_datetime: "2026-02-20T10:00:00"` to match existing test conventions
- Read each transcript file to determine correct expected events, speaker names, times

## Key context

- Existing tests in `test_end_to_end.py` and `test_crud_flows.py` already define expected events for these samples — use as reference for sidecar content
- `test_end_to_end.py:L170-180` defines events for simple_lunch (1 lunch event)
- `test_crud_flows.py:L223-250` defines events for update_meeting (update action)
- `test_crud_flows.py:L267-290` defines events for cancel_event (delete action)
- LLM response attendees/assumptions are comma-separated strings
## Acceptance
- [ ] 10 sidecar `.expected.json` files created, one per migrated sample
- [ ] Each sidecar validates against SidecarSpec Pydantic model
- [ ] Expected events match the actual transcript content
- [ ] CRUD sidecars have calendar_context with realistic existing events
- [ ] mock_llm_response is valid LLMResponseSchema JSON in each sidecar
- [ ] Tolerance levels appropriate: strict for simple cases, moderate for complex, relaxed for ambiguous
- [ ] `owner` and `reference_datetime` fields present in all sidecars
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
