# fn-4-gyw.1 Define shared event models (ExtractedEvent, SyncResult) if not already in models

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Added SyncResult dataclass to cal_ai.models.calendar with counters (created, updated, deleted, skipped), conflict/failure list tracking, and computed properties. ExtractedEvent and ValidatedEvent already existed from fn-3; only SyncResult was missing. Includes 16 unit tests with 100% coverage on the new module.
## Evidence
- Commits: 3688a831598ce3e713846ab4fe766a1bc521e4a8
- Tests: python3 -m pytest tests/unit/test_models_calendar.py -v (16 passed), python3 -m pytest tests/ -v (156 passed, 0 regressions), python3 -m ruff check (all checks passed)
- PRs: