# fn-8-vyv.1 Surface token usage from GeminiClient and add CLI subcommand infrastructure

## Description
Two infrastructure changes required before the benchmark module can be built: (1) surface Gemini API token usage metadata from `GeminiClient._call_api()`, and (2) convert the flat argparse CLI to subparsers with backward compatibility.

**Size:** M
**Files:** `src/cal_ai/llm.py`, `src/cal_ai/__main__.py`, `tests/unit/test_llm.py`, `tests/unit/test_cli.py`

## Approach

### Token usage surfacing
- Create a small dataclass `LLMCallResult(text: str, usage: object | None)` in `llm.py`
- Modify `_call_api()` (line 198-208) to return `LLMCallResult` instead of bare `str`, capturing `response.usage_metadata`
- Update `extract_events()` to unpack `LLMCallResult.text` where it currently uses the string return
- Store accumulated `usage_metadata` on `ExtractionResult` or as a separate return — the benchmark will read it
- Guard with `getattr(response, 'usage_metadata', None)` for SDK version safety
- Update all mocks in `test_llm.py` — `_mock_client()` pattern (line 51-63) must set `mock_response.usage_metadata`

### CLI subcommands
- Convert `build_parser()` (line 25-59 of `__main__.py`) to use `parser.add_subparsers()`
- Add `run` subcommand (default) with existing `transcript_file`, `--dry-run`, `-v`, `--owner` args
- Add `benchmark` subcommand with positional `directory` (optional, default `samples/`), `--output` flag
- Ensure `python -m cal_ai file.txt` still works by setting default subparser when no subcommand given
- `benchmark` subcommand handler: stub that prints "Not implemented" (actual logic in Task 3)
- Update all 7 CLI tests in `test_cli.py` — especially `test_cli_missing_file_argument_shows_usage`

## Key context

- `_call_api()` has 2-attempt retry logic (line 180-208). The `LLMCallResult` should come from the successful attempt
- `usage_metadata` fields: `prompt_token_count`, `candidates_token_count`, `total_token_count`, `thoughts_token_count`
- Existing CLI tests call `main(["path/to/file.txt"])` directly — this must continue working
- The `--owner` flag falls back to `OWNER_NAME` from `.env` via `load_settings()` (line 93-95)
## Acceptance
- [ ] `_call_api()` returns `LLMCallResult` with both `text` and `usage` fields
- [ ] `extract_events()` works correctly with the new return type
- [ ] Token counts accessible after extraction (for benchmark to consume)
- [ ] All existing `test_llm.py` tests pass with updated mocks
- [ ] `python -m cal_ai benchmark` invokes benchmark subcommand (stub OK)
- [ ] `python -m cal_ai samples/crud/simple_lunch.txt` still works (backward compatible)
- [ ] `python -m cal_ai --help` shows both subcommands
- [ ] All 7 existing CLI tests pass
- [ ] `ruff check .` passes
- [ ] `pytest` passes with 0 failures
## Done summary
Surfaced Gemini token usage metadata from _call_api() via LLMCallResult dataclass and added CLI subcommand infrastructure (run + benchmark) with full backward compatibility.
## Evidence
- Commits: 6ce7ffa9378d89ee9b7f67edcc11cc68958bae24
- Tests: ruff check ., pytest
- PRs: