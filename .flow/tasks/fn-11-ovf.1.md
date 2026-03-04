# fn-11-ovf.1 Schema extension + test runner + suite isolation

## Description
Build the test infrastructure for memory round-trip testing: extend the sidecar schema, create the test runner with inline discovery, isolate memory samples from existing suite, and add Makefile targets.

**Size:** M
**Files:** `tests/regression/schema.py`, `tests/regression/loader.py`, `tests/regression/test_memory_roundtrip.py`, `Makefile`, `pyproject.toml`, `samples/memory/.gitkeep`

## Approach

### 1. Schema Extension (`tests/regression/schema.py`)
Add three optional fields to `SidecarSpec` (backward-compatible, `None` defaults):
- `expected_events_no_memory: list[SidecarExpectedEvent] | None = None`
- `mock_llm_response_no_memory: dict[str, Any] | None = None`
- `expected_memory_facts: list[SidecarMemoryEntry] | None = None`

Follow existing pattern at `schema.py:82-111`. Existing sidecars continue to parse without changes.

### 2. Existing Suite Isolation (`tests/regression/loader.py`)
Modify `discover_samples()` at `loader.py:18-42` to exclude files under `samples/memory/`. Add a path filter: skip any `.txt` file whose resolved path has `memory` as a directory component. This prevents memory samples from being auto-discovered by `conftest.py:57-106`.

### 3. Test Runner (`tests/regression/test_memory_roundtrip.py`)
Create new test file with `pytest_generate_tests` **inline** (NOT in a separate conftest):
- Glob `samples/memory/*_b.txt` to find B-samples
- For each B, derive A by replacing `_b.txt` → `_a.txt`; assert A exists
- Load sidecars via `SidecarSpec.model_validate(json.loads(...))`
- Parametrize with IDs like `pref_time`, `people_relationship`, etc.

Two test functions following `test_regression.py:59-144` mock pattern:

**`test_memory_mock_roundtrip(memory_pair)`**: Two pipeline calls per B-sample:
- **Pass 1 (with memory)**: Patch `MemoryStore.load_all()` → B's `memory_context`, patch `genai.Client` → B's `mock_llm_response`, assert `expected_events` via `assert_extraction_result()`
- **Pass 2 (without memory)**: Patch `MemoryStore.load_all()` → `[]`, patch `genai.Client` → B's `mock_llm_response_no_memory`, assert `expected_events_no_memory`. Construct a temp `SidecarSpec` copy with `expected_events` set to `expected_events_no_memory`.

**`test_memory_live_roundtrip(memory_pair)`**: Same dual-pass structure with real Gemini API:
- **Pass 1 (with memory)**: Real extraction with memory context → assert against `expected_events` via tolerance engine (`moderate` tolerance)
- **Pass 2 (without memory)**: Real extraction with empty memory → assert against `expected_events_no_memory` via tolerance engine (`moderate` tolerance)
- Uses the same tolerance engine and sidecar copy pattern as mock mode. Both passes must succeed independently.
- Requires `--live` flag. Mark with `@pytest.mark.live` and `@pytest.mark.memory`. No xdist.
- Negative pairs (zero-delta): `expected_events` == `expected_events_no_memory`, so both passes assert against the same expected output.

Reuse patches from `test_regression.py:81-126`: `fetch_calendar_context`, `_resolve_memory_db_path`, `run_memory_write`.

### 4. Makefile + pyproject.toml
- Add `test-memory`: `pytest tests/regression/test_memory_roundtrip.py -v`
- Add `test-memory-live`: `pytest tests/regression/test_memory_roundtrip.py --live -v` (no `-n` flag — avoids rate limits)
- Register `memory` marker in pyproject.toml `[tool.pytest.ini_options]` markers list
- Create empty `samples/memory/` directory (with `.gitkeep`)

## Key Context
- `mock_llm_response` `attendees` field is a comma-separated **string**, not list
- Memory formatter is duck-typed: `SidecarMemoryEntry` already satisfies the contract
- `dry_run=True` skips Stage 4 (memory write) — A-sidecar `expected_memory_facts` is documentation-only
- Existing `test_regression.py` patches: `genai.Client`, `fetch_calendar_context`, `MemoryStore`, `format_memory_context`, `_resolve_memory_db_path`, `run_memory_write`
- For no-memory pass tolerance, swap `expected_events` on a copy of the sidecar — don't modify the tolerance engine

## Acceptance
- [ ] `SidecarSpec` has `expected_events_no_memory`, `mock_llm_response_no_memory`, `expected_memory_facts` (all optional, `None` default)
- [ ] Existing sidecars still parse without error (backward compatible)
- [ ] `discover_samples()` in `loader.py` excludes `samples/memory/` directory
- [ ] Existing regression tests still pass (609+ tests)
- [ ] `test_memory_roundtrip.py` has inline `pytest_generate_tests` (no separate conftest)
- [ ] Discovers B-samples and infers A-pairs correctly
- [ ] Mock test runs dual-pass extraction (with/without memory), both passes assert independently
- [ ] No-memory pass uses `expected_events_no_memory` via sidecar copy pattern
- [ ] Live test uses same dual-pass pattern with moderate tolerance for both passes
- [ ] Live test: negative pairs (zero-delta) succeed with identical expected events on both passes
- [ ] Live test requires `--live` flag, marked with `@pytest.mark.live` and `@pytest.mark.memory`
- [ ] `make test-memory` and `make test-memory-live` targets work
- [ ] `memory` marker registered in pyproject.toml
- [ ] `make lint` passes

## Done summary
Built memory round-trip test infrastructure: extended SidecarSpec with dual-outcome fields (expected_events_no_memory, mock_llm_response_no_memory, expected_memory_facts), isolated samples/memory/ from existing suite discovery, created test_memory_roundtrip.py with inline pytest_generate_tests and dual-pass mock/live test functions, added Makefile targets and pytest marker.
## Evidence
- Commits: 8c8909a43bb695a7a41823a3cd6a03cd8cdbc22f, e2fcaa3
- Tests: make lint, pytest tests/ -v --tb=short (609 passed, 42 skipped), make test-memory (2 skipped - no samples yet)
- PRs: