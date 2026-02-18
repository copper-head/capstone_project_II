# fn-4-gyw.10 Write unit tests for exceptions and retry (9 tests)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Added 9 unit tests for the exceptions module and @with_retry decorator covering HTTP 429 rate limit retry and exhaustion, HTTP 401 auth refresh success and failure, network timeout retry and exhaustion, HTTP 404 immediate raise on delete and update, and start_time > end_time validation. Also added a start/end time validation guard to map_to_google_event.
## Evidence
- Commits: 40531f6d248912807b7771c8fec8af3aa9a621a5
- Tests: python3 -m pytest tests/unit/calendar/test_exceptions.py -v, python3 -m pytest tests/unit/calendar/ -v
- PRs: