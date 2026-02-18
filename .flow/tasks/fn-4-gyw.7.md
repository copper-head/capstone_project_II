# fn-4-gyw.7 Write unit tests for auth (7 tests)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Added 7 unit tests for the OAuth 2.0 auth module covering all authentication paths: valid cached token, expired token refresh, refresh failure fallback, browser flow launch, missing credentials error, token persistence, and scope verification.
## Evidence
- Commits: 3ccc8f2ff560ff888ed17d78bc49ad3c350c8b33
- Tests: python3 -m pytest tests/unit/calendar/test_auth.py -v --tb=short, python3 -m ruff check tests/unit/calendar/
- PRs: