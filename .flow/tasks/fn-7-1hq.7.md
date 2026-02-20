# fn-7-1hq.7 Update docs, Makefile, and final validation

## Description
Update all project documentation, add Makefile targets for the regression suite, and perform final validation that everything works end-to-end.

**Size:** M
**Files:** `README.md`, `CLAUDE.md`, `Makefile`, `pyproject.toml` (verify)

## Approach

- **README.md updates:**
  - Update "Sample Transcripts" table (lines 87-98) with new subdirectory paths and expanded categories
  - Update Run section examples (lines 44-66) with new paths like `samples/crud/simple_lunch.txt`
  - Add "Regression Testing" subsection in Development section documenting mock/live modes
  - Update test count if mentioned
- **CLAUDE.md updates:**
  - Add `samples/` subdirectory structure to Project Structure tree (currently omitted)
  - Add regression test commands to Commands section
  - Add sidecar `.expected.json` convention to Key Conventions section
- **Makefile updates:**
  - Add `test-regression` target: `pytest tests/regression/ -v`
  - Add `test-regression-live` target: `pytest tests/regression/ --live -v`
  - Ensure existing `test` target still runs all tests including regression (mock mode)
- **Final validation:**
  - `make lint` passes (ruff check + format check)
  - `make test` passes (all existing + new regression tests in mock mode)
  - Verify 40+ samples exist across all 5 categories (at least 5 per category)
  - Verify all sidecars valid (loader doesn't error)
  - Verify `--live` flag correctly skips live tests when not provided
- **Set fn-8-vyv dependency:**
  - Ensure fn-8-vyv `depends_on_epics` includes `fn-7-1hq`

## Key context

- README currently has a "Sample Transcripts" table at lines 87-98 with 9 entries in flat format
- CLAUDE.md Project Structure tree at lines 16-34 does not show `samples/` at all
- Makefile at root has `test`, `test-cov`, `lint`, `format`, `build`, `run`, `clean` targets
- Follow existing Makefile tab-indentation style
## Acceptance
- [ ] README.md updated: sample paths, run examples, regression testing section
- [ ] CLAUDE.md updated: project structure tree, commands, key conventions
- [ ] Makefile has `test-regression` and `test-regression-live` targets
- [ ] `make lint` passes
- [ ] `make test` passes (all tests including regression mock mode)
- [ ] 40+ total samples across 5 categories (verified count)
- [ ] fn-8-vyv dependency on fn-7-1hq set in .flow
- [ ] `ruff check .` clean
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
