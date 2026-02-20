# fn-8-vyv.2 Build scoring engine — P/R/F1, confidence calibration, event matching

## Description
Build the scoring engine that calculates Precision/Recall/F1 metrics and confidence calibration stats for benchmark results. Reuses fn-7's tolerance engine and best-match event alignment.

**Size:** M
**Files:** `src/cal_ai/benchmark/__init__.py`, `src/cal_ai/benchmark/scoring.py`, `tests/unit/test_benchmark_scoring.py`

## Approach

- Create `src/cal_ai/benchmark/` package
- Build `scoring.py` with:
  - `score_sample(actual_events, expected_events, tolerance_level)` → `SampleScore` dataclass
  - Uses fn-7's best-match algorithm to align actual events to expected events
  - Classifies each match as TP (within tolerance) or mismatch
  - Unmatched actual = FP, unmatched expected = FN
  - `SampleScore`: tp, fp, fn, precision, recall, f1, per_event_details
  - `aggregate_scores(sample_scores)` → `AggregateScore` with overall and per-category P/R/F1
  - `calibrate_confidence(sample_scores)` → dict mapping confidence level to accuracy percentage
- Edge cases:
  - Both actual and expected empty: P=1.0, R=1.0, F1=1.0 (vacuous truth)
  - Actual empty, expected non-empty: P=1.0, R=0.0
  - Expected empty, actual non-empty: P=0.0, R=1.0
- Import fn-7's tolerance assertion functions and best-match algorithm (from `tests/regression/` or `src/cal_ai/`)
- Confidence calibration: group all scored events by their `confidence` field, calculate % that are TPs

## Key context

- fn-7's tolerance engine (Task fn-7-1hq.2) must be built first — it provides `assert_event_matches()` and best-match pairing
- The tolerance levels (strict/moderate/relaxed) come from the sidecar `.expected.json`
- Event matching uses `rapidfuzz.fuzz.token_set_ratio` for title comparison (fn-7 dependency)
- `ExtractedEvent` has `confidence: Literal["high", "medium", "low"]` at `models/extraction.py:56`
- F1 = 2 * (P * R) / (P + R), with F1=0.0 when P+R=0
## Acceptance
- [ ] `score_sample()` correctly computes TP/FP/FN using fn-7's best-match + tolerance
- [ ] P/R/F1 calculated per sample with correct edge case handling (0/0 cases)
- [ ] `aggregate_scores()` produces overall and per-category breakdown
- [ ] `calibrate_confidence()` maps high/medium/low to accuracy percentages
- [ ] Unit tests cover: all-correct, all-wrong, partial match, empty expected, empty actual, mixed actions
- [ ] `ruff check .` passes
- [ ] `pytest` passes with 0 failures
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
