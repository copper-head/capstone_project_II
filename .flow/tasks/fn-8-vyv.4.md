# fn-8-vyv.4 AI summary generation, docs, Makefile, and final validation

## Description
Add AI-generated summary to benchmark reports (Gemini self-evaluation), update documentation, add Makefile targets, gitignore reports directory, and run final validation.

**Size:** M
**Files:** `src/cal_ai/benchmark/summary.py`, `src/cal_ai/benchmark/runner.py` (integrate summary), `Makefile`, `.gitignore`, `README.md`, `CLAUDE.md`

## Approach

### AI Summary (`summary.py`)
- `generate_ai_summary(benchmark_result, gemini_client) → str`
- Compose a prompt that includes: overall P/R/F1, per-category breakdown, worst-performing samples (bottom 5 by F1), confidence calibration stats, common failure patterns
- Ask Gemini to: summarize what went well, identify failure patterns, suggest prompt/pipeline improvements
- Use structured prompt with clear sections (not free-form) — follow LLM-as-a-judge best practice (one criterion per section, CoT reasoning)
- Graceful failure: if Gemini call fails, return a note like "AI summary unavailable: {error}" — report is still complete without it
- Include AI summary cost in total cost tracking

### Integration
- Call `generate_ai_summary()` at end of `run_benchmark()`, append to markdown report
- Track summary generation latency and token cost separately in report metadata

### Docs & Build
- `.gitignore`: add `reports/` entry
- `Makefile`: add `benchmark` target — `python -m cal_ai benchmark`
- `README.md`: add Benchmarking section describing `python -m cal_ai benchmark`, output formats, history tracking
- `CLAUDE.md`: add `make benchmark` to Commands section, note `reports/` directory, document benchmark architecture

### Final validation
- `ruff check .` and `ruff format --check .` clean
- `pytest` all existing + new tests pass
- `python -m cal_ai --help` shows both subcommands
- `python -m cal_ai benchmark --help` shows usage
- Verify backward compatibility: `python -m cal_ai samples/crud/simple_lunch.txt --dry-run`

## Key context

- AI summary prompt should be <2000 tokens to keep cost low
- Follow `demo_output.py` list-of-strings pattern for report sections
- LLM-as-a-judge best practice: binary/low-precision scores per criterion, CoT reasoning, structured output
- Gemini pricing: summary call ≈ 2K input + 1K output ≈ $0.01 per run
## Acceptance
- [ ] `generate_ai_summary()` produces coherent self-evaluation of benchmark results
- [ ] AI summary gracefully handles Gemini API failure (report still complete)
- [ ] AI summary cost included in total cost tracking
- [ ] `reports/` added to `.gitignore`
- [ ] `make benchmark` target works
- [ ] README.md has Benchmarking section
- [ ] CLAUDE.md updated with benchmark commands and architecture
- [ ] `ruff check .` and `ruff format --check .` pass
- [ ] All tests pass (existing + new)
- [ ] `python -m cal_ai --help` shows run and benchmark subcommands
- [ ] `python -m cal_ai benchmark --help` shows benchmark usage
- [ ] Backward compatibility verified: `python -m cal_ai file.txt` still works
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
