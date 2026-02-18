# fn-4-gyw.5 Implement error handling and retry decorator (calendar/exceptions.py)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Implemented calendar-specific exception hierarchy (CalendarAPIError, CalendarAuthError, CalendarRateLimitError, CalendarNotFoundError) and a @with_retry decorator with exponential backoff for 429/network errors, single-retry token refresh for 401, and immediate raise for 404.
## Evidence
- Commits: a4e07a3ea7638ef94d6afac67af19c5d3d6c457a
- Tests: python3 -m pytest tests/ -v --tb=short
- PRs: