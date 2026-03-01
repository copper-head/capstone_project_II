# fn-9-img.4 Testing & Regression Compatibility

## Description

Ensure the memory system is compatible with the existing regression test suite and benchmark runner. Verify backward compatibility, update schemas for optional memory fields, and add memory-specific test infrastructure.

**Size:** M
**Files:**
- `tests/regression/schema.py` — **already modified** by fn-9-img.3 (SidecarMemoryEntry + memory_context added). Verify only.
- `tests/regression/test_regression.py` — **already modified** by fn-9-img.3 (memory patches in test_mock_extraction). Verify only.
- `src/cal_ai/benchmark/runner.py` — **already modified** by fn-9-img.3 (memory_context="" at line 291). Verify only.
- `tests/unit/test_memory_integration.py` (new) — integration test: full read+write path with mocked LLM. **This is the main remaining deliverable.**
- `tests/regression/conftest.py` (verify) — confirm no changes needed
<!-- Updated by plan-sync: fn-9-img.3 already modified schema.py, test_regression.py, and runner.py -->

## Approach

- **SidecarSpec schema**: **Already implemented by fn-9-img.3.** `SidecarMemoryEntry` (with `category` Literal, `key`, `value`, and optional `confidence`) and `SidecarSpec.memory_context: list[SidecarMemoryEntry] | None = None` already exist in `tests/regression/schema.py` (lines ~61-111). Verify the model validation works and no changes are needed.
<!-- Updated by plan-sync: fn-9-img.3 already added SidecarMemoryEntry and memory_context to SidecarSpec -->
- **Regression memory injection**: **Already implemented by fn-9-img.3.** The regression test `test_mock_extraction` already patches all four memory pipeline targets (`MemoryStore`, `format_memory_context`, `_resolve_memory_db_path`, `run_memory_write`) and reads `sidecar.memory_context`. See `tests/regression/test_regression.py` lines ~81-125. The `_patch_pipeline_deps()` helper in `tests/unit/test_pipeline.py` (lines ~134-271) also patches all four targets and served as the pattern. Verify this works correctly; no new patching code is needed.
<!-- Updated by plan-sync: fn-9-img.3 already implemented regression memory patches and SidecarMemoryEntry/memory_context in schema -->
- **Benchmark runner**: **Already implemented by fn-9-img.3.** The `extract_events()` call at `runner.py:286` already passes `memory_context=""` (line 291). No change needed — verify only.
<!-- Updated by plan-sync: fn-9-img.3 already added memory_context="" to benchmark runner extract_events call -->
- **Integration test**: Test the full round-trip: seed MemoryStore with test data → load → format → verify prompt includes memory section → mock write-path LLM calls → verify store mutations. Use `tmp_path / "memory.db"` fixture (file-based, not `:memory:`).
- **Backward compatibility verification**: Run `make test` and confirm all existing regression samples pass in mock mode with zero sidecar changes. The memory patches in `test_mock_extraction` are already in place from fn-9-img.3, so backward compatibility should already be assured. Note: `test_live_extraction` does NOT yet patch memory targets — it relies on graceful degradation (Stage 1b try/except). Decide if live tests also need memory patches for cleanliness.
<!-- Updated by plan-sync: fn-9-img.3 already added memory patches to test_mock_extraction; live test relies on graceful degradation -->

## Key context

- `SidecarSpec` is a Pydantic model at `tests/regression/schema.py` — `SidecarMemoryEntry` and `memory_context` field already added by fn-9-img.3
- Regression tests run `run_pipeline()`, NOT `extract_events()` directly — memory injection at the pipeline level (patching MemoryStore + 3 other targets) already done in `test_mock_extraction` by fn-9-img.3
- `conftest.py` at `tests/regression/conftest.py` has `pytest_generate_tests` for auto-discovery — it parametrizes `sample_case` but does not call `extract_events()`
- The benchmark runner already passes `memory_context=""` at `runner.py:291` (added by fn-9-img.3)
- No existing sidecar files need modification — new optional fields default to `None`
- `_patch_pipeline_deps()` in `tests/unit/test_pipeline.py` (lines ~134-271) patches all four memory targets: `MemoryStore`, `format_memory_context`, `_resolve_memory_db_path`, and `run_memory_write`
- The pipeline memory write path is **Stage 4** (not Stage 5); summary is Stage 5
- The main remaining work items for this task are: (1) integration test `tests/unit/test_memory_integration.py`, (2) verification that all existing tests pass, (3) any cleanup needed for `test_live_extraction` memory handling

## Acceptance
- [x] `SidecarMemoryEntry` model has `category` (Literal enum), `key`, `value` (required), and `confidence` (optional Literal enum) with validation *(done by fn-9-img.3 — `tests/regression/schema.py:61-79`)*
- [x] `SidecarSpec` has typed optional `memory_context: list[SidecarMemoryEntry] | None = None` *(done by fn-9-img.3 — `tests/regression/schema.py:109`)*
- [ ] All existing regression test samples pass in mock mode with zero sidecar changes
- [x] Regression tests inject memory context by patching `MemoryStore.load_all()` when sidecar includes `memory_context` *(done by fn-9-img.3 — `tests/regression/test_regression.py:81-125`)*
- [x] Benchmark runner calls `extract_events()` with `memory_context=""` (backward compatible) *(done by fn-9-img.3 — `src/cal_ai/benchmark/runner.py:291`)*
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
