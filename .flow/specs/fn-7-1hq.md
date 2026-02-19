# Comprehensive Regression Test Suite: 40+ Stress-Test Samples

## Problem

The current test suite has 11 sample transcripts, all 3-10 lines long. This is insufficient for evaluating the AI extraction pipeline's reliability across diverse scenarios. We need a comprehensive stress-test suite with 40+ samples covering varied lengths, CRUD edge cases, multi-speaker complexity, adversarial inputs, and real-world messiness — each with automated regression tests that assert structural correctness with configurable per-sample tolerance.

## Key Decisions

1. **Scope: Automated regression only** — benchmarking (precision/recall/F1) is a separate future epic.
2. **Volume: 40+ new samples** — at least 5 per scenario category.
3. **Length: Even spread** — equal mix of short (5 lines), medium (20 lines), long (50+ lines), and very long (100+ lines).
4. **Sidecar JSON files** — each sample.txt gets a sample.expected.json defining expected events, actions, mock calendar context (for CRUD tests), and tolerance level.
5. **Per-sample tolerance** — three levels:
   - **strict**: exact event count, exact action types, times ±30min, exact titles.
   - **moderate**: ±1 event count, times ±2hrs, title keyword matching.
   - **relaxed**: ±2 event count, times ±1 day, fuzzy title matching.
6. **Full setup in sidecar** — sidecar defines both expected output AND mock calendar state the AI should see (for update/delete scenarios).
7. **Subdirectory organization** — `samples/crud/`, `samples/adversarial/`, `samples/multi_speaker/`, `samples/realistic/`, `samples/long/`.
8. **Migrate existing 11 samples** into the new subdirectory structure, update all references (Dockerfile, docker-compose, tests).
9. **Live + mock test modes** — default to mock (pre-recorded responses), explicit `--live` flag for real API calls. Uses `@pytest.mark.live` marker, skipped unless `--live` is passed.
10. **Adversarial: moderate level** — sarcasm, hypotheticals, past-tense events, vague references. No extreme prompt injection or multi-language mixing.
11. **Done criteria: scenario coverage complete** — every category has at least 5 samples each.
12. **Sample style: mix** — some surgical/targeted for specific edge cases, some naturalistic (filler, tangents, natural flow).
13. **Docker paths updated** to match new subdirectory structure.

## Scenario Categories (at least 5 samples each)

### CRUD Edge Cases
- Bulk deletes ("clear my schedule")
- Partial updates (change time but keep location)
- Conflicting instructions (reschedule then cancel same event)
- Ambiguous references to existing events (multiple possible matches)
- Update with no matching event (should fall back to create)
- Delete already-deleted event

### Multi-Speaker Complexity
- 5+ speakers with cross-talk
- Side conversations (2 people plan something while 3 others discuss unrelated topics)
- Speaker references another speaker's calendar ("Bob, don't forget your dentist appointment")
- Multiple events from different speaker pairs in same conversation
- Speakers disagreeing on event details

### Adversarial / Tricky
- Sarcasm ("yeah let's totally have a meeting at 3am")
- Hypotheticals ("what if we scheduled a retreat?")
- Past-tense events ("we met last Thursday" — should NOT create)
- Vague references ("let's catch up sometime")
- Events mentioned in negation ("I'm NOT going to the party")

### Real-World Messy
- Typos and informal language
- Incomplete sentences, interruptions
- Slang and abbreviations ("lmk", "tmr", "nvm")
- Filler words and tangents
- Time zones mentioned casually ("3pm your time")

### Long Conversations
- 50+ line conversations with 1-2 events buried in noise
- 100+ line conversations with 5+ events spread throughout
- Very long tangents with scheduling info at the very end
- Conversations that circle back to modify earlier plans

## Sidecar JSON Schema

```json
{
  "description": "Brief description of what this sample tests",
  "category": "crud|adversarial|multi_speaker|realistic|long",
  "tolerance": "strict|moderate|relaxed",
  "calendar_context": [
    {
      "id": "google-event-uuid",
      "summary": "Team Standup",
      "start": "2026-02-19T09:00:00",
      "end": "2026-02-19T09:30:00",
      "location": "Room 301"
    }
  ],
  "expected_events": [
    {
      "action": "create|update|delete",
      "title": "Event Title",
      "start_time": "2026-02-20T12:00:00",
      "end_time": "2026-02-20T13:00:00",
      "existing_event_id_required": false,
      "location": "optional",
      "attendees_contain": ["Alice", "Bob"]
    }
  ],
  "expected_event_count": 2,
  "notes": "Optional notes about expected AI behavior"
}
```

## Open Questions

- Exact tolerance thresholds may need tuning after initial test runs (e.g., ±30min may be too tight for strict on some edge cases).
- How to handle non-determinism in title wording — keyword matching vs fuzzy string distance.

## Acceptance

- [ ] 40+ sample transcripts across all 5 categories (at least 5 per category)
- [ ] Even spread of conversation lengths (short, medium, long, very long)
- [ ] Each sample has a sidecar .expected.json with tolerance, calendar context, and expected events
- [ ] Existing 11 samples migrated to new subdirectory structure
- [ ] All references updated (Dockerfile, docker-compose, existing tests)
- [ ] Regression test runner loads sidecar files and asserts per tolerance level
- [ ] Mock mode (default) uses pre-recorded responses
- [ ] Live mode via --live flag with @pytest.mark.live marker
- [ ] All existing tests still pass after migration
- [ ] ruff clean
