# Benchmark Suite: Precision/Recall Scoring with AI-Summarized Reports

## Problem

There is no way to quantitatively measure the AI extraction pipeline's accuracy. We need a benchmarking tool that scores the system across sample transcripts using precision/recall/F1, produces detailed markdown reports with full expected-vs-actual diffs, tracks performance history across model/prompt changes, and uses the AI itself to generate a reasoning summary of the results.

## Key Decisions

1. **Metrics: Precision + Recall + F1** — standard information retrieval metrics per sample and aggregate.
2. **Data source: reuse fn-7 samples** — no duplication. Runs against the same samples/sidecars from the regression suite.
3. **Custom directory support** — `python -m cal_ai benchmark /path/to/any/samples/`. If sidecars (.expected.json) are present, score against them. If missing, run extraction and log output with a warning.
4. **Live Gemini calls only** — benchmarking is meaningless without real model output. No mock mode.
5. **CLI: subcommand of cal-ai** — `python -m cal_ai benchmark [dir] [--output path]`.
6. **Output: console summary + detailed markdown report + log file.**
   - Console: table with overall scores and per-category breakdown.
   - Markdown report: full diff per sample (expected vs actual events side-by-side, field-by-field comparison, AI reasoning excerpt).
   - Log file: detailed pipeline logs for each sample.
7. **Output path: default `reports/` with `--output` override.**
8. **History tracking** — each run appends a summary row to `reports/benchmark_history.json`. Enables charting improvement over time.
9. **Latency + cost tracking** — record wall-clock time per sample and estimate API cost (tokens * price).
10. **Confidence calibration** — check whether the AI's confidence ratings (high/medium/low) correlate with actual accuracy. Report calibration stats (e.g., "high confidence events were correct 95% of the time").
11. **AI-generated summary** — at the end of the markdown report, call Gemini to summarize the benchmark results: what went well, what failed, patterns in failures, suggestions for improvement. The AI reasons about its own performance.

## Output Structure

### Console Output
```
Benchmark Results — 2026-02-19T14:30:00
========================================
Samples: 45 | Scored: 42 | No ground truth: 3

Overall:  P=0.91  R=0.87  F1=0.89
Category breakdown:
  crud:          P=0.95  R=0.90  F1=0.92  (12 samples)
  adversarial:   P=0.82  R=0.75  F1=0.78  (8 samples)
  multi_speaker: P=0.88  R=0.85  F1=0.86  (7 samples)
  realistic:     P=0.93  R=0.91  F1=0.92  (9 samples)
  long:          P=0.90  R=0.84  F1=0.87  (6 samples)

Confidence calibration:
  high:   94% correct
  medium: 71% correct
  low:    45% correct

Avg latency: 2.3s/sample | Est. cost: $0.12
```

### Markdown Report (reports/benchmark_YYYY-MM-DDTHH-MM.md)
- Header with run metadata (model, timestamp, sample count)
- Per-category summary table
- Per-sample detail: expected vs actual diff, field comparisons, tolerance applied, AI reasoning
- Confidence calibration breakdown
- Latency + cost stats
- AI-generated summary section at the end (Gemini reasons about the results)

### History File (reports/benchmark_history.json)
```json
[
  {
    "timestamp": "2026-02-19T14:30:00",
    "model": "gemini-2.5-pro",
    "samples": 45,
    "precision": 0.91,
    "recall": 0.87,
    "f1": 0.89,
    "avg_latency_s": 2.3,
    "est_cost_usd": 0.12
  }
]
```

## Dependencies

- **Depends on fn-7-1hq** (regression test suite) — needs the samples, sidecars, and subdirectory structure to exist first.
- Reuses fn-7's tolerance system for scoring flexibility.

## Edge Cases

- Samples without sidecars: run extraction, log output, warn, exclude from scoring.
- Empty sample directory: exit with clear error message.
- Gemini API failure mid-benchmark: log the failure for that sample, continue with remaining samples, mark failed samples in report.
- AI summary generation failure: still produce the full report, just skip the AI summary section with a note.
- History file doesn't exist yet: create it on first run.
- Custom directory with different sidecar schema: validate schema on load, skip malformed sidecars with warning.

## Open Questions

- Token counting for cost estimation — use the Gemini API's usage metadata if available, or estimate from prompt/response length.
- Whether to support comparing two specific runs side-by-side in the report (vs just tracking history).

## Acceptance

- [ ] `python -m cal_ai benchmark` subcommand works
- [ ] Accepts optional directory argument (defaults to built-in samples)
- [ ] `--output` flag for custom report location
- [ ] Precision/Recall/F1 calculated per sample and aggregate
- [ ] Per-category breakdown in console and report
- [ ] Full expected vs actual diff per sample in markdown report
- [ ] Confidence calibration stats (high/medium/low accuracy correlation)
- [ ] Latency per sample tracked
- [ ] API cost estimated
- [ ] History appended to benchmark_history.json
- [ ] AI-generated summary at end of markdown report
- [ ] Graceful handling of samples without sidecars
- [ ] ruff clean, all existing tests pass
