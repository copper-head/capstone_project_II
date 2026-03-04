# fn-11-ovf.3 People transcript pairs (4 pairs)

## Description
Create 4 people transcript pairs in `samples/memory/` testing relationship resolution, nickname aliasing, contact context, and an unknown person negative case.

**Size:** M
**Files:** 16 files in `samples/memory/` (4 pairs × 4 files each)

## Approach

**Delta assertability rule**: All non-negative pair deltas must be on positively assertable fields (`title`, `start_time`, `end_time`, or non-empty `attendees_contain`). Do not rely solely on field absence.

### Pair 1: Relationship Resolution (`people_relationship_a/b`)
- A: Conversation establishing "Bob is Alice's manager" / "Bob is my boss"
- Memory fact: `{category: "people", key: "Bob", value: "Alice's manager/boss", confidence: "high"}`
- B: "I need to schedule a meeting with my boss next week"
- With memory: Title resolves to "Meeting with Bob", `attendees_contain: ["Bob"]`
- Without memory: Generic title "Meeting with boss" or "Meeting", `attendees_contain: []`
- **Assertable delta**: `title` differs (resolved name vs generic reference). `attendees_contain` also differs but is supplementary (empty = skip check in tolerance engine).

### Pair 2: Nickname Aliasing (`people_nickname_a/b`)
- A: Conversation establishing "We call Robert Smith 'Bobby'"
- Memory fact: `{category: "people", key: "Bobby", value: "Robert Smith (nickname Bobby)", confidence: "high"}`
- B: "Lunch with Bobby on Friday"
- With memory: `attendees_contain: ["Robert Smith"]`, title "Lunch with Robert Smith"
- Without memory: `attendees_contain: ["Bobby"]`, title "Lunch with Bobby"
- **Assertable delta**: `title` and `attendees_contain` both differ (both are non-empty and positively assertable)

### Pair 3: Contact Context (`people_contact_a/b`)
- A: Conversation establishing "Sarah is my dentist at Downtown Dental"
- Memory fact: `{category: "people", key: "Sarah_dentist", value: "Alice's dentist at Downtown Dental", confidence: "high"}`
- B: "Schedule my appointment with Sarah"
- With memory: Title "Dentist Appointment with Sarah" (contextual title)
- Without memory: Title "Appointment with Sarah" (generic title)
- **Assertable delta**: `title` differs (context-enriched vs generic)

### Pair 4: Unknown Person Negative Case (`people_unknown_a/b`)
- A: Same as Pair 1 (establishes facts about Bob)
- Memory fact: same Bob fact
- B: "Meeting with Carlos on Tuesday" — Carlos is unknown, not in memory
- With memory: Event has "Carlos" as attendee — memory about Bob does NOT get applied to Carlos
- Without memory: Same result — "Carlos" attendee
- **Zero delta**: `expected_events` == `expected_events_no_memory`

## Key Context
- Follow same conventions as Task 2 (owner, reference_datetime, tolerance, format)
- People category memories use the person's name as the key
- Attendees in mock_llm_response are comma-separated strings (e.g., "Alice, Bob")
- `attendees_contain` in expected events is a list of strings for subset matching

## Acceptance
- [ ] 4 transcript pairs created: people_relationship, people_nickname, people_contact, people_unknown
- [ ] Each A-sidecar has valid `expected_events` and `expected_memory_facts`
- [ ] Each B-sidecar has full dual-outcome structure
- [ ] Relationship pair: `title` differs between with-memory and no-memory (resolved name vs generic)
- [ ] Nickname pair: both `title` and `attendees_contain` differ between passes (both non-empty)
- [ ] Contact pair: `title` differs between passes (context-enriched vs generic)
- [ ] Unknown person pair: `expected_events` and `expected_events_no_memory` are identical (zero delta)
- [ ] No pair relies solely on field absence as its only delta
- [ ] `make test-memory` passes (all pairs in mock mode)
- [ ] `make lint` passes
- [ ] Transcripts demonstrate natural speech with names and relationships

## Done summary
Created 4 people memory transcript pairs (16 files) in samples/memory/: relationship resolution (boss->Bob), nickname aliasing (Bobby->Robert Smith), contact context (Sarah->Dr. Sarah Chen), and unknown person negative case (zero delta). All 8 mock memory tests pass, full suite (617 tests) passes with no regressions.
## Evidence
- Commits: 7a04f882f2b7dcff5e0ed04c2ce1a5f2fc1faa3f, 62d33cba90b4f05486505c8adfbd1e8a2047f963
- Tests: make test-memory, make lint, make test
- PRs: