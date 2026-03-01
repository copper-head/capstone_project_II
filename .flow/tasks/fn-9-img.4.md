# fn-9-img.4 Testing & Regression Compatibility

## Description

Ensure the memory system is compatible with the existing regression test suite and benchmark runner. Verify backward compatibility, update schemas for optional memory fields, and add memory-specific test infrastructure.

**Size:** M
**Files:**
- `tests/regression/schema.py` (modify) — add typed optional memory fields to `SidecarSpec`
- `tests/regression/test_regression.py` (modify) — inject memory context when present in sidecar, via patching `MemoryStore.load_all()` or the memory-loader function in pipeline
- `src/cal_ai/benchmark/runner.py` (modify) — update `extract_events()` call to accept memory_context
- `tests/unit/test_memory_integration.py` (new) — integration test: full read+write path with mocked LLM
- `tests/regression/conftest.py` (modify if needed) — expose sidecar memory data to test functions

## Approach

- **SidecarSpec schema**: Define a `SidecarMemoryEntry` Pydantic model with required `category: Literal["preferences", "people", "vocabulary", "patterns", "corrections"]`, required `key: str`, required `value: str`, and optional `confidence: Literal["low", "medium", "high"] = "medium"`. Add `memory_context: list[SidecarMemoryEntry] | None = None` to `SidecarSpec`. This provides schema validation and makes formatter inputs unambiguous.
- **Regression memory injection**: Since regression tests run via `run_pipeline()` (not `extract_events()` directly), memory injection must happen by patching `MemoryStore.load_all()` to return the sidecar's memory entries. Because `format_memory_context()` is duck-typed (accepts objects with `category`/`key`/`value` attributes), `SidecarMemoryEntry` objects can be returned directly from the patched `load_all()` — no conversion to `MemoryRecord` needed. Patch in `test_regression.py` via `monkeypatch` or `unittest.mock.patch`. If the sidecar has no `memory_context`, the pipeline uses its normal empty-DB behavior.
- **Benchmark runner**: Update the `extract_events()` call at `runner.py:286` to pass `memory_context=""` explicitly. The benchmark runs without memory context by default — memory-specific benchmark samples are out of scope (V2).
- **Integration test**: Test the full round-trip: seed MemoryStore with test data → load → format → verify prompt includes memory section → mock write-path LLM calls → verify store mutations. Use `tmp_path / "memory.db"` fixture (file-based, not `:memory:`).
- **Backward compatibility verification**: Run `make test` and confirm all 40 existing regression samples pass in mock mode with zero sidecar changes.

## Key context

- `SidecarSpec` is a Pydantic model at `tests/regression/schema.py` — adding optional fields is non-breaking
- Regression tests run `run_pipeline()`, NOT `extract_events()` directly — memory injection must happen at the pipeline level (patching MemoryStore), not at the extraction level
- `conftest.py` at `tests/regression/conftest.py` has `pytest_generate_tests` for auto-discovery — it parametrizes `sample_case` but does not call `extract_events()`
- The benchmark runner builds calendar context from sidecar data via `build_calendar_context()` at `runner.py:~270` — memory context follows the same opt-in pattern
- No existing sidecar files need modification — new optional fields default to `None`

## Acceptance
- [ ] `SidecarMemoryEntry` model has `category` (Literal enum), `key`, `value` (required), and `confidence` (optional Literal enum) with validation
- [ ] `SidecarSpec` has typed optional `memory_context: list[SidecarMemoryEntry] | None = None`
- [ ] All existing regression test samples pass in mock mode with zero sidecar changes
- [ ] Regression tests inject memory context by patching `MemoryStore.load_all()` when sidecar includes `memory_context`
- [ ] Benchmark runner calls `extract_events()` with `memory_context=""` (backward compatible)
- [ ] Integration test covers full read path: seed store → load → format → verify prompt section
- [ ] Integration test covers full write path: mock LLM → dispatch actions → verify store mutations (upsert/delete)
- [ ] Integration test uses `tmp_path / "memory.db"` (file-based, isolated)
- [ ] `make test` passes with all new and existing tests
- [ ] `make lint` passes

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
