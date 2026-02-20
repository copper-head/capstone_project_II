# fn-7-1hq.2 Build sidecar JSON schema and tolerance assertion engine

## Description
Build the sidecar JSON schema (Pydantic model), a loader utility that pairs `.txt` files with `.expected.json` sidecars, and the tolerance assertion engine with three levels (strict/moderate/relaxed). Add `rapidfuzz` as a dev dependency.

**Size:** M
**Files:** `tests/regression/__init__.py`, `tests/regression/schema.py`, `tests/regression/tolerance.py`, `tests/regression/loader.py`, `pyproject.toml`, `tests/unit/test_regression_utils.py` (or similar)

## Approach

- Create `tests/regression/` package
- Define Pydantic models in `schema.py`:
  - `SidecarCalendarEvent`: id, summary, start, end, location
  - `SidecarExpectedEvent`: action (create|update|delete), title, start_time, end_time, existing_event_id_required, location, attendees_contain
  - `SidecarSpec`: description, category, tolerance (strict|moderate|relaxed, default moderate), owner (default "Alice"), reference_datetime (default "2026-02-20T10:00:00"), calendar_context (list), expected_events (list), mock_llm_response (dict), notes
- Build `loader.py`:
  - `discover_samples(base_dir)` — glob `**/*.txt`, pair with `.expected.json`, return list of `(txt_path, sidecar)` tuples
  - `load_sidecar(json_path) -> SidecarSpec` — load, validate, return
  - `build_calendar_context(sidecar) -> CalendarContext` — convert sidecar's `calendar_context` array into `CalendarContext` dataclass with `events_text`, `id_map`, `event_meta`
- Build `tolerance.py`:
  - `assert_extraction_result(actual: ExtractionResult, sidecar: SidecarSpec)` — main entry point
  - Best-match event pairing: match actual events to expected by minimizing (action_mismatch + title_distance + time_distance)
  - **strict**: exact event count, exact action types, times ±30min, `token_set_ratio >= 95` for titles
  - **moderate**: ±1 event count, times ±2hrs, `token_set_ratio >= 80`
  - **relaxed**: ±2 event count, times ±1day, `token_set_ratio >= 60`
  - For delete actions: time tolerance applies to the referenced event's time from calendar_context
  - Attendees: subset check (case-insensitive) — `attendees_contain` items must all appear in actual attendees
  - Use `__tracebackhide__ = True` in assertion helpers for clean pytest output
- Add `rapidfuzz` to `[project.optional-dependencies] dev` in pyproject.toml
- Write unit tests for tolerance logic (test all three levels with known inputs)

## Key context

- `CalendarContext` dataclass at `src/cal_ai/calendar/context.py` has: `events_text` (formatted string), `id_map` (int→str), `event_count`, `event_meta` (int→dict)
- Events text format: `[ID] Title | Start - End | Location` per line
- `ExtractedEvent` model at `src/cal_ai/models/extraction.py` — has `action`, `title`, `start_time` (ISO string), `end_time`, `location`, `attendees` (list[str]), `confidence`, `existing_event_id` (int|None)
- rapidfuzz `token_set_ratio` returns 0-100 float, handles word reordering well for event titles
- Do NOT use `pytest.approx` for datetime comparison — use manual `timedelta` comparison
## Acceptance
- [ ] `tests/regression/schema.py` — Pydantic models for sidecar JSON validate correctly
- [ ] `tests/regression/loader.py` — discovers .txt/.expected.json pairs, builds CalendarContext
- [ ] `tests/regression/tolerance.py` — asserts extraction results at strict/moderate/relaxed levels
- [ ] Best-match event pairing works (not positional)
- [ ] `rapidfuzz` added to dev dependencies in pyproject.toml
- [ ] Unit tests for tolerance engine (at least 6 tests: 2 per level)
- [ ] `ruff check .` passes
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
