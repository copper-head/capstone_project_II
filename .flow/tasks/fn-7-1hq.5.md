# fn-7-1hq.5 Write Adversarial, Realistic, and Long category samples with sidecars

## Description
Write 5+ Adversarial/Tricky samples, 5+ Real-World Messy samples, and 5+ Long Conversation samples, each with sidecar `.expected.json` files.

**Size:** M
**Files:** `samples/adversarial/*.txt` + `*.expected.json` (5+ pairs), `samples/realistic/*.txt` + `*.expected.json` (5+ pairs), `samples/long/*.txt` + `*.expected.json` (5+ pairs)

## Approach

**Adversarial samples (5+):**
- `sarcasm.txt` — "yeah let's totally have a meeting at 3am" (moderate, expected: 0 events)
- `hypothetical.txt` — "what if we scheduled a retreat?" (moderate, expected: 0 events)
- `past_tense.txt` — "we met last Thursday" — should NOT create (strict, expected: 0 events)
- `vague_reference.txt` — "let's catch up sometime" (relaxed, expected: 0 or 1 low-confidence)
- `negation.txt` — "I'm NOT going to the party" (moderate, expected: 0 events)
- `mixed_signals.txt` — mix of real events + sarcasm/hypotheticals (relaxed)

**Realistic samples (5+):**
- `typos_informal.txt` — typos, informal language ("def", "prolly", "tmr") (moderate)
- `interruptions.txt` — incomplete sentences, speakers cutting each other off (moderate)
- `slang_abbreviations.txt` — "lmk", "tmr", "nvm", "w/", casual tone (moderate)
- `filler_tangents.txt` — lots of filler words, off-topic tangents, 1 event buried (relaxed)
- `timezone_casual.txt` — "3pm your time", casual timezone references (relaxed)

**Long conversation samples (5+):**
- `long_noise_few_events.txt` — 50+ lines, 1-2 events buried in noise (relaxed)
- `long_many_events.txt` — 100+ lines, 5+ events spread throughout (relaxed)
- `long_tangent_end.txt` — very long tangents, scheduling info at the very end (relaxed)
- `long_circular_planning.txt` — conversations that circle back and modify earlier plans (relaxed)
- `long_meeting_notes.txt` — 80+ lines of meeting discussion with 3-4 action items (moderate)

## Key context

- Adversarial samples with 0 expected events: `expected_events: []` in sidecar. Tolerance still applies to count (relaxed allows ±2, so up to 2 false positives pass)
- Long samples should be at least 50 lines (some 100+), with realistic filler, tangents, speaker changes
- `reference_datetime` in sidecar matters for samples using relative time ("tomorrow", "next week")
- Use `[Speaker Name]: dialogue text` format throughout
- Long samples should be marked implicitly as slow by test infrastructure (auto-tagged in conftest)
## Acceptance
- [ ] 5+ Adversarial sample pairs in `samples/adversarial/`
- [ ] 5+ Realistic sample pairs in `samples/realistic/`
- [ ] 5+ Long Conversation sample pairs in `samples/long/`
- [ ] Long samples are genuinely long: at least 3 are 50+ lines, at least 2 are 100+ lines
- [ ] Each sidecar validates against SidecarSpec Pydantic model
- [ ] Adversarial samples with 0 events have `expected_events: []`
- [ ] mock_llm_response in each sidecar is valid LLMResponseSchema JSON
- [ ] All spec scenarios covered: sarcasm, hypotheticals, past-tense, vague, negation, typos, slang, tangents, timezone, noise, circular planning
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
