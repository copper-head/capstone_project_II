# fn-11-ovf.4 Pattern transcript pairs (3 pairs) + docs updates

## Description
Create 3 pattern transcript pairs in `samples/memory/` testing recurring meetings, habitual activities, and a pattern change negative case. Update documentation (CLAUDE.md, README.md, Makefile comment, pyproject.toml).

**Size:** M
**Files:** 12 files in `samples/memory/` (3 pairs × 4 files) + `CLAUDE.md`, `README.md`

## Approach

**Delta assertability rule**: All non-negative pair deltas must be on positively assertable fields (`title`, `start_time`, `end_time`, or non-empty `attendees_contain`). Do not rely solely on field absence.

### Pair 1: Recurring Meeting (`pattern_recurring_a/b`)
- A: Conversation establishing "Our team standup is every Monday at 9am in the huddle room"
- Memory fact: `{category: "patterns", key: "team_standup", value: "Every Monday at 9am in the huddle room", confidence: "high"}`
- B: "Don't forget about standup this week" or "Is standup still happening?"
- With memory: Creates event on Monday 9am with specific title "Team Standup"
- Without memory: Ambiguous — may create event but with different time/day
- **Assertable delta**: `start_time` differs (Monday 9am from memory vs arbitrary time without memory), `title` may also differ

### Pair 2: Habitual Activity (`pattern_habitual_a/b`)
- A: Conversation establishing "I go to yoga every Tuesday and Thursday at 6pm"
- Memory fact: `{category: "patterns", key: "yoga_schedule", value: "Tuesday and Thursday at 6pm", confidence: "high"}`
- B: "I need to block off my usual yoga time this week"
- With memory: Creates 2 events — Tuesday 6pm and Thursday 6pm
- Without memory: Creates 1 generic event (ambiguous "yoga time")
- **Assertable delta**: Different number of `expected_events` (2 vs 1), different `start_time` values

### Pair 3: Pattern Change Negative Case (`pattern_change_a/b`)
- A: Conversation establishing "Team standup is Monday 9am"
- Memory fact: same as Pair 1
- B: "We moved standup to Wednesday at 10am starting this week"
- With memory: Creates event Wednesday 10am (transcript overrides memory pattern)
- Without memory: Same result — Wednesday 10am from explicit transcript
- **Zero delta**: `expected_events` == `expected_events_no_memory`

### Documentation Updates

**CLAUDE.md:**
- Add `samples/memory/` to Project Structure (after `long/`)
- Add `make test-memory` and `make test-memory-live` to Commands section
- Add note about memory round-trip testing convention in Key Conventions

**README.md:**
- Add `memory/` row to samples category table
- Add "Memory Round-Trip Testing" subsection to testing docs
- Update project structure

## Key Context
- Pattern-related memories may produce multiple events (e.g., yoga: 2 events)
- `expected_events` can be a list with multiple events
- Follow tolerance conventions: `moderate` for memory pairs
- Habitual pair is the most complex (2 events expected) — craft mock responses carefully

## Acceptance
- [ ] 3 transcript pairs created: pattern_recurring, pattern_habitual, pattern_change
- [ ] Each pair has full A/B structure with sidecars
- [ ] Recurring pair: `start_time` differs between with-memory and no-memory expected events
- [ ] Habitual pair: different number of expected events between passes (2 vs 1), different `start_time` values
- [ ] Pattern change pair: `expected_events` and `expected_events_no_memory` are identical (zero delta)
- [ ] No pair relies solely on field absence as its only delta
- [ ] `make test-memory` passes (all 11 pairs total in mock mode)
- [ ] CLAUDE.md updated: project structure, commands, conventions
- [ ] README.md updated: samples table, memory testing section
- [ ] `make test` passes (all existing + memory tests)
- [ ] `make lint` passes
- [ ] Final validation: `make test-memory-live` passes with real Gemini API

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
