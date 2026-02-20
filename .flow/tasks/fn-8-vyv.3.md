# fn-8-vyv.3 Build benchmark runner, report generator, and JSONL history

## Description
Build the benchmark runner that discovers samples, executes live Gemini extraction, scores results, and generates reports (console summary, markdown detail, JSONL history).

**Size:** M
**Files:** `src/cal_ai/benchmark/runner.py`, `src/cal_ai/benchmark/report.py`, `tests/unit/test_benchmark_report.py`, `src/cal_ai/__main__.py` (wire up benchmark handler)

## Approach

### Runner (`runner.py`)
- `discover_samples(directory: Path)` → list of `(txt_path, sidecar_path | None, category)`. Category from subdirectory name, or `"uncategorized"` for flat dirs
- `run_benchmark(directory, output_path, gemini_client)` → `BenchmarkResult` dataclass
- For each sample with sidecar:
  1. Load sidecar, build `CalendarContext` from sidecar's `calendar_context` field
  2. Call `gemini_client.extract_events(transcript_text, owner_name, current_datetime, calendar_context=context_text)`
  <!-- Updated by plan-sync: fn-8-vyv.1 used extract_events(transcript_text, owner_name, current_datetime, calendar_context="") not extract_events(text, calendar_context, owner, reference_datetime) -->
  3. Capture `ExtractionResult.usage_metadata` (list of usage objects, one per API attempt) for token counting, `time.monotonic()` for latency
  <!-- Updated by plan-sync: fn-8-vyv.1 stores usage as ExtractionResult.usage_metadata (list[Any]) not LLMCallResult.usage -->
  4. Score via `score_sample()` from Task 2
- For samples without sidecars: extract only, log warning, skip scoring
- Progress indicator: print `[N/M] category/name... P=X.XX R=X.XX (Xs)` to stderr
- `BenchmarkResult`: list of `SampleResult`, aggregate scores, total tokens, total cost, total duration

### Report (`report.py`)
- `format_console_summary(result: BenchmarkResult) → str` — follows `demo_output.py` pattern (list of strings)
- `format_markdown_report(result: BenchmarkResult) → str` — per-sample detail with expected vs actual diff, field comparison, tolerance applied
- Report filename: `benchmark_YYYY-MM-DDTHH-MM-SS.md` (seconds to avoid collision)
- Cost estimation: `(prompt_tokens * 1.25 + output_tokens * 10.00) / 1_000_000`

### History (`runner.py`)
- Append one JSONL line per run to `reports/benchmark_history.jsonl`
- Fields: timestamp, model, sample_count, scored_count, precision, recall, f1, avg_latency_s, est_cost_usd
- Create `reports/` directory if not exists

### CLI wiring
- Replace benchmark stub from Task 1 with actual `run_benchmark()` call
- Handle `--output` flag, default to `reports/`
- Load settings for `GEMINI_API_KEY` only (not calendar credentials)

## Key context

- `extract_events()` signature: `extract_events(transcript_text, owner_name, current_datetime, calendar_context="")` at `llm.py:74-169`
<!-- Updated by plan-sync: fn-8-vyv.1 used extract_events(transcript_text, owner_name, current_datetime, calendar_context="") not extract_events(text, calendar_context, owner, current_datetime); line range updated from 96-103 to 74-169 -->
- `CalendarContext` has `events_text`, `id_map`, `event_count`, `event_meta` at `calendar/context.py`
- Sidecar `calendar_context` from fn-7 is a dict with `events_text` and `id_map` — must be converted to `CalendarContext` dataclass
- Gemini free tier: 15 RPM. Add `time.sleep()` between samples if needed (configurable)
- `demo_output.py:32-58` is the pattern for report formatting
## Acceptance
- [ ] `discover_samples()` finds all `.txt` files across category subdirectories
- [ ] Samples with sidecars are scored; samples without sidecars are extracted and warned
- [ ] Live Gemini extraction called with sidecar's calendar context, owner, and reference_datetime
- [ ] Token counts collected from `ExtractionResult.usage_metadata` (list of usage objects) and used for cost estimation
<!-- Updated by plan-sync: fn-8-vyv.1 stores usage on ExtractionResult.usage_metadata not LLMCallResult.usage -->
- [ ] Latency tracked per sample via `time.monotonic()`
- [ ] Console summary printed to stdout with overall P/R/F1 and per-category breakdown
- [ ] Detailed markdown report written with per-sample expected vs actual diff
- [ ] JSONL history line appended to `reports/benchmark_history.jsonl`
- [ ] Progress indicator printed to stderr during execution
- [ ] `python -m cal_ai benchmark` end-to-end works with live Gemini
- [ ] `ruff check .` passes
- [ ] `pytest` passes with 0 failures
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
