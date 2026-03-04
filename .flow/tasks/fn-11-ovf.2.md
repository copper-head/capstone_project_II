# fn-11-ovf.2 Preference transcript pairs (4 pairs)

## Description
Create 4 preference transcript pairs in `samples/memory/` testing time, location, duration preferences, and an explicit override negative case.

**Size:** M
**Files:** 16 files in `samples/memory/` (4 pairs × 4 files each: `_a.txt`, `_a.expected.json`, `_b.txt`, `_b.expected.json`)

## Approach

Each pair follows the A/B pattern:
- **A transcript**: Natural conversation where Alice establishes a preference
- **A sidecar**: `expected_events` for calendar extraction (may be empty) + `expected_memory_facts` (documentation of what facts should be stored)
- **B transcript**: Later conversation where the preference should influence extraction
- **B sidecar**: `memory_context` (facts from A), `expected_events` (with memory), `expected_events_no_memory` (baseline), both `mock_llm_response` variants

**Delta assertability rule**: All non-negative pair deltas must be on positively assertable fields (`title`, `start_time`, `end_time`, or non-empty `attendees_contain`). Do not rely solely on field absence (`location: null`, `attendees_contain: []`).

### Pair 1: Time Preference (`pref_time_a/b`)
- A: Conversation where Alice mentions "I prefer afternoon meetings, around 2 or 3pm"
- Memory fact: `{category: "preferences", key: "meeting_time", value: "Prefers afternoon meetings around 2-3pm", confidence: "high"}`
- B: "Alice and Bob, let's find a time to meet next Tuesday" — ambiguous timing
- With memory: LLM defaults to afternoon (e.g., 2:00-3:00 PM)
- Without memory: LLM picks default (e.g., 9:00 AM — the typical LLM default for unspecified times)
- **Assertable delta**: `start_time` and `end_time` differ (afternoon vs morning)

### Pair 2: Location Preference (`pref_location_a/b`)
- A: "I always go to Starbucks on Main St for coffee meetings"
- Memory fact: `{category: "preferences", key: "coffee_meeting_location", value: "Starbucks on Main St", confidence: "high"}`
- B: "Let's grab coffee with Sarah on Wednesday"
- With memory: Title includes location reference (e.g., "Coffee with Sarah at Starbucks on Main St"), location set
- Without memory: Generic title (e.g., "Coffee with Sarah"), no location
- **Assertable delta**: `title` differs between passes (location-enriched vs generic). Do NOT rely solely on `location: null` skip.

### Pair 3: Duration Preference (`pref_duration_a/b`)
- A: "My 1:1s are usually 30 minutes, that's plenty of time"
- Memory fact: `{category: "preferences", key: "one_on_one_duration", value: "30 minutes", confidence: "high"}`
- B: "Schedule a 1:1 with David on Thursday"
- With memory: 30-minute event (end_time 30min after start)
- Without memory: Default duration 60 minutes (end_time 60min after start)
- **Assertable delta**: `end_time` differs (30-min vs 60-min duration)

### Pair 4: Override Negative Case (`pref_override_a/b`)
- A: "I prefer afternoon meetings around 2-3pm"
- Memory fact: same as Pair 1
- B: "Let's do 9am on Friday for the team sync" — explicit time overrides preference
- With memory: 9:00 AM (transcript wins over memory)
- Without memory: 9:00 AM (same — explicit time always wins)
- **Zero delta**: `expected_events` == `expected_events_no_memory`

## Key Context
- Use `owner: "Alice"` and `reference_datetime: "2026-02-20T10:00:00"` (follows existing sample convention)
- `tolerance: "moderate"` for all memory pairs
- `mock_llm_response` attendees is a comma-separated string
- Calendar context: provide minimal context (empty or 1-2 existing events)
- Transcripts use `[Speaker Name]: dialogue text` format
- Design scenarios where with-memory vs without-memory produces clearly different LLM-plausible outputs on assertable fields

## Acceptance
- [ ] 4 transcript pairs created: pref_time, pref_location, pref_duration, pref_override
- [ ] Each A-sidecar has valid `expected_events` (may be empty) and `expected_memory_facts`
- [ ] Each B-sidecar has `memory_context`, `expected_events`, `expected_events_no_memory`, both `mock_llm_response` variants
- [ ] Time preference pair: `start_time`/`end_time` differ between with-memory and no-memory expected events (afternoon vs morning)
- [ ] Location preference pair: `title` differs between with-memory and no-memory expected events (location-enriched vs generic)
- [ ] Duration preference pair: `end_time` differs between with-memory and no-memory expected events (30min vs 60min)
- [ ] Override pair: `expected_events` and `expected_events_no_memory` are identical (zero delta)
- [ ] `make test-memory` passes (all 4 pairs in mock mode)
- [ ] `make lint` passes
- [ ] Transcripts are realistic and natural

## Done summary
Created 4 preference memory transcript pairs (pref_time, pref_location, pref_duration, pref_override) with 16 total files in samples/memory/. Each pair follows the A/B convention with dual-outcome sidecars for mock and live testing. All 4 mock tests pass, lint is clean, and the full test suite (613 tests) remains green.
## Evidence
- Commits: 347e84e6514e0461977ced1f77ec90737970bddc, 3993f79
- Tests: make test-memory, make lint, make test
- PRs: