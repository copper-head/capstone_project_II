# fn-7-1hq.3 Build regression test infrastructure (conftest, --live flag, parametrize)

## Description
Build the regression test infrastructure: conftest.py with `pytest_generate_tests` for auto-discovery, `--live` CLI flag, custom marker registration, and the main parametrized test function that wires together the sidecar loader, mock/live modes, and tolerance assertions.

**Size:** M
**Files:** `tests/regression/conftest.py`, `tests/regression/test_regression.py`, `pyproject.toml`

## Approach

- Create `tests/regression/conftest.py`:
  - `pytest_addoption(parser)` — register `--live` flag
  - `pytest_configure(config)` — register `live` and `regression` markers via `addinivalue_line`
  - `pytest_collection_modifyitems(config, items)` — skip `@pytest.mark.live` tests unless `--live` passed
  - `pytest_generate_tests(metafunc)` — if `"sample_case"` in fixturenames, glob all `samples/**/*.expected.json`, pair with `.txt`, parametrize with ids from `category/filename`
  - Auto-apply `@pytest.mark.slow` to tests from `samples/long/` directory
- Register markers in `pyproject.toml` under `[tool.pytest.ini_options]`:
  ```
  markers = ["live: requires real Gemini API credentials", "regression: regression test suite", "slow: long-running test"]
  ```
- Create `tests/regression/test_regression.py`:
  - `test_mock_extraction(sample_case, monkeypatch_env)` — mock mode test:
    1. Load sidecar via `load_sidecar()`
    2. Build CalendarContext from sidecar
    3. Patch `genai.Client.models.generate_content` to return `mock_llm_response` from sidecar
    4. Patch `fetch_calendar_context` to return built CalendarContext
    5. Call `run_pipeline()` with `dry_run=True`
    6. Assert result via `assert_extraction_result()`
  - `test_live_extraction(sample_case, monkeypatch_env)` — live mode test:
    1. Marked `@pytest.mark.live`
    2. Same flow but NO mock on generate_content
    3. Requires real `GEMINI_API_KEY` env var
    4. Same tolerance assertions

## Key context

- Follow `pytest_collection_modifyitems` pattern from pytest docs: skip marked tests by default, run when flag passed
- Existing `monkeypatch_env` fixture at `tests/conftest.py:L11-28` sets required env vars — reuse it
- Existing `_patch_pipeline_deps()` at `tests/unit/test_pipeline.py:L130-224` shows how to mock all pipeline deps
- `run_pipeline()` at `src/cal_ai/pipeline.py:L116` accepts `transcript_path, owner, dry_run, current_datetime`
- Use `sorted()` on glob results for deterministic test ordering across platforms
- IDs should be `category/stem` format (e.g., `crud/simple_lunch`) for `-k` filtering
## Acceptance
- [ ] `tests/regression/conftest.py` with pytest_generate_tests auto-discovery
- [ ] `--live` CLI flag works: `pytest tests/regression/` runs mock only; `pytest tests/regression/ --live` runs live tests
- [ ] `live`, `regression`, `slow` markers registered in pyproject.toml (no PytestUnknownMarkWarning)
- [ ] `test_mock_extraction` parametrized over all sample/sidecar pairs
- [ ] `test_live_extraction` skipped unless --live flag passed
- [ ] Tests from `samples/long/` auto-tagged with `@pytest.mark.slow`
- [ ] All existing tests still pass
- [ ] `ruff check .` passes
## Done summary
Built regression test infrastructure: conftest.py with pytest_generate_tests auto-discovery from samples/**/*.expected.json sidecars, --live CLI flag for live Gemini API tests, marker registration (live/regression/slow) in pyproject.toml, auto-tagging of samples/long/ tests with @pytest.mark.slow, and parametrized test_mock_extraction/test_live_extraction functions in test_regression.py.
## Evidence
- Commits: b7ceeb1, aae5da3
- Tests: pytest tests/ -v --tb=short, pytest tests/regression/ -v --tb=long, pytest tests/regression/ --live -v, ruff check tests/regression/conftest.py tests/regression/test_regression.py
- PRs: