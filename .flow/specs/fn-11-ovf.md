# Memory System Round-Trip Testing

## Overview

Prove that the memory system influences future LLM extraction by creating paired sample transcripts. Conversation A establishes memory-worthy facts; conversation B (with those facts pre-loaded as `memory_context`) should produce different—and better—extraction results than without memory.

## Scope

- 11 paired transcript samples in `samples/memory/` covering preferences, people, and patterns
- Sidecar schema extension for dual-outcome testing (`expected_events_no_memory`, `mock_llm_response_no_memory`)
- Separate test runner that understands A/B pairing and dual-outcome comparison
- Existing regression suite remains untouched (memory samples excluded from auto-discovery)

## Stakeholders

- **Developers**: New test patterns for memory-related samples, new `make` targets
- **End users**: None (test infrastructure only)
- **Operations**: None

## Architecture

### Test Structure

```
samples/memory/
  pref_time_a.txt              # Establishes: "Alice prefers afternoon meetings"
  pref_time_a.expected.json    # Expected events + expected_memory_facts (documentation)
  pref_time_b.txt              # Tests recall: "let's meet sometime"
  pref_time_b.expected.json    # memory_context + dual expected_events + dual mock responses
  ...
```

**Pairing convention**: Files share the same underscore-separated stem before the `_a`/`_b` suffix (e.g., `pref_time_a.txt` pairs with `pref_time_b.txt`). The test runner discovers pairs by globbing `*_b.txt` and replacing the trailing `_b` with `_a` to find the partner.

### Sidecar Schema Extension

Add to `SidecarSpec` (backward-compatible optional fields with `None` defaults):
- `expected_events_no_memory: list[SidecarExpectedEvent] | None = None` — baseline extraction without memory
- `mock_llm_response_no_memory: dict[str, Any] | None = None` — mock response for no-memory extraction pass
- `expected_memory_facts: list[SidecarMemoryEntry] | None = None` — documentation of what memory facts A should produce; NOT programmatically asserted (dry_run skips Stage 4 memory write)

### Delta Assertability Rule

The tolerance engine treats `location: null` as "skip check" and `attendees_contain: []` as "skip check". Therefore, **every non-negative pair must encode its delta on positively assertable fields in BOTH passes** — primarily `title`, `start_time`, `end_time`, or non-empty `attendees_contain`. Do not rely on field absence as the sole proof of memory influence.

Examples of assertable deltas:
- **Time preference**: Different `start_time`/`end_time` between passes (afternoon vs morning)
- **Location preference**: Different `title` between passes (e.g., "Coffee with Sarah at Starbucks" vs "Coffee with Sarah")
- **People resolution**: Different `title` between passes (e.g., "Meeting with Bob" vs "Meeting") and/or different `attendees_contain` (both non-empty)
- **Duration**: Different `end_time` between passes (30min vs 60min)

### Test Runner (`tests/regression/test_memory_roundtrip.py`)

`pytest_generate_tests` lives **inside the test file itself** (no separate conftest). This keeps discovery self-contained.

Discovery logic:
- Glob `samples/memory/*_b.txt`
- For each B-file, derive A-file by replacing trailing `_b.txt` → `_a.txt`
- Assert A-file exists (fail if missing partner)
- Load both sidecars via `SidecarSpec.model_validate()`
- Parametrize with IDs like `pref_time`, `people_relationship`, etc.

Two test functions:
1. **`test_memory_mock_roundtrip`** — For each B-sample, two separate pipeline calls:
   - **Pass 1 (with memory)**: Patch `MemoryStore.load_all()` to return B's `memory_context`, use `mock_llm_response` → assert against `expected_events` via tolerance engine
   - **Pass 2 (without memory)**: Patch `MemoryStore.load_all()` to return `[]`, use `mock_llm_response_no_memory` → assert against `expected_events_no_memory` via tolerance engine
   - For the no-memory pass, construct a temp `SidecarSpec` copy with `expected_events` swapped to `expected_events_no_memory`. No tolerance engine changes.
2. **`test_memory_live_roundtrip`** — Same dual-pass structure as mock mode but with real Gemini API:
   - **Pass 1 (with memory)**: Real extraction with memory context injected → assert against `expected_events` via tolerance engine (`moderate` tolerance)
   - **Pass 2 (without memory)**: Real extraction with empty memory → assert against `expected_events_no_memory` via tolerance engine (`moderate` tolerance)
   - Requires `--live` flag. No xdist parallelism.
   - Uses the same tolerance engine and sidecar copy pattern as mock mode. The difference in `expected_events` vs `expected_events_no_memory` implicitly proves memory influence — if both passes succeed against their respective expected events, the memory system demonstrably changed the outcome.

**Negative cases (zero delta)**: Override, unknown person, and pattern change pairs have IDENTICAL `expected_events` and `expected_events_no_memory`. Both passes produce the same result, proving memory doesn't override explicit instructions. Both passes must succeed in both modes.

### Existing Suite Isolation

Modify `discover_samples()` in `tests/regression/loader.py` to skip files under `samples/memory/` directory. Add a path-based filter: skip any `.txt` file where `'memory'` is a directory component. This excludes BOTH A and B files from auto-discovery.

### A-Sample Handling

A-transcripts are documentation artifacts — they are NOT run by any test runner. They exist to:
- Document the conversation that established the memory facts
- Provide `expected_memory_facts` as reference for what B's `memory_context` represents
- Help developers understand the test pair's intent

A-files are excluded from auto-discovery by the directory-level filter in `discover_samples()`.

## Alternatives Considered

1. **Inline conftest vs memory_conftest.py** — Chose inline `pytest_generate_tests` in test file to avoid conftest naming/scoping issues.
2. **Asserting A's memory write output** — Rejected: `dry_run=True` skips Stage 4. `expected_memory_facts` is documentation-only.
3. **Field-level difference assertions for live mode** — Rejected: introduces an underspecified "delta contract" and requires additional schema fields. Instead, both mock and live modes use the same dual-pass pattern with two independent tolerance assertions. The delta is encoded in the different `expected_events` / `expected_events_no_memory` lists — if both passes succeed, memory demonstrably changed the outcome.
4. **Hyphenated stems** — Rejected: underscores are consistent with existing sample naming (`multi_speaker`, etc.).
5. **Relying on field absence for delta proof** — Rejected: tolerance engine treats `null`/empty as "skip check". All deltas must be on positively assertable fields.

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Memory samples auto-discovered by existing suite | Path-based filter in `discover_samples()` excludes A and B files |
| Flaky live tests (LLM non-determinism) | Moderate tolerance + no xdist; design scenarios with clear, LLM-plausible deltas |
| Schema extension breaks existing sidecars | All new fields `Optional` with `None` default |
| Preference delta not meaningful | Design scenarios where non-default values are expected (e.g., afternoon preference, not the LLM default of morning) |
| Delta relies on field absence | All non-negative deltas use positively assertable fields (title, time, non-empty attendees) |

## Quick Commands

```bash
# Run memory round-trip tests (mock mode)
make test-memory

# Run memory round-trip tests (live Gemini API)
make test-memory-live

# Run all tests (memory tests included via make test)
make test

# Lint check
make lint
```

## Non-Functional Targets

- Mock mode: deterministic, zero API calls, strict dual-outcome matching
- Live mode: moderate tolerance, both passes (with-memory and no-memory) must match their respective expected events
- All 11 pairs pass both passes in mock mode; live mode uses moderate tolerance for both passes
- Zero impact on existing test suite (609+ tests still pass)

## Docs Updates

- CLAUDE.md: Add `samples/memory/` to project structure, new commands
- README.md: Add memory testing section, update samples table
- Makefile: Add `test-memory` and `test-memory-live` targets
- pyproject.toml: Add `memory` pytest marker

## Acceptance

- [ ] `samples/memory/` contains 11 transcript pairs (A + B with sidecars)
- [ ] Each B-sidecar has `memory_context`, `expected_events`, `expected_events_no_memory`, `mock_llm_response`, `mock_llm_response_no_memory`
- [ ] Separate test runner with inline `pytest_generate_tests` discovers pairs and runs dual-outcome assertions
- [ ] Mock mode: deterministic, zero API calls, all 11 pairs pass both with-memory and no-memory assertions
- [ ] Live mode: moderate tolerance, all 11 pairs pass both with-memory and no-memory assertions against respective expected events
- [ ] Negative pairs (override, unknown person, pattern change): `expected_events` and `expected_events_no_memory` are identical; both passes succeed with same outcome
- [ ] Non-negative pairs: `expected_events` and `expected_events_no_memory` differ on positively assertable fields (title, time, or non-empty attendees_contain), demonstrating memory influence
- [ ] No pair relies solely on field absence (null location, empty attendees) as its only delta
- [ ] Existing regression suite still passes (609+ tests, memory samples excluded from both A and B)
- [ ] `make lint` passes
- [ ] Preference scenarios: time (afternoon, non-default slot), location (title delta), duration + override negative case
- [ ] People scenarios: relationships (title + attendee delta), nicknames, contact context + unknown person negative case
- [ ] Pattern scenarios: recurring, habitual + pattern change negative case
- [ ] CLAUDE.md, README.md, Makefile, pyproject.toml updated
- [ ] A-sidecars document `expected_memory_facts` (documentation-only)

## Dependencies

- fn-9-img (Memory system) — already merged
- fn-7-1hq (Regression test infrastructure) — in place

## References

- `tests/regression/schema.py:82-111` — SidecarSpec model
- `tests/regression/loader.py:18-42` — discover_samples (needs memory exclusion)
- `tests/regression/conftest.py:57-106` — pytest_generate_tests pattern (reference, NOT modified)
- `tests/regression/test_regression.py:59-144` — mock extraction test pattern
- `tests/regression/tolerance.py:408-561` — tolerance assertion engine
- `src/cal_ai/memory/formatter.py:21-62` — format_memory_context (duck-typed)
- `src/cal_ai/memory/models.py:22-43` — MemoryRecord model
- `src/cal_ai/pipeline.py:202-275` — Stage 1b + Stage 2 memory integration
- `src/cal_ai/pipeline.py:353-354` — Stage 4 skipped in dry_run mode
