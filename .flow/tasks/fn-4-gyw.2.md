# fn-4-gyw.2 Implement OAuth 2.0 auth (calendar/auth.py)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Implemented OAuth 2.0 auth module at `src/cal_ai/calendar/auth.py` with `get_calendar_credentials()` function that follows a 3-step strategy: load cached token, refresh expired token, or launch browser-based InstalledAppFlow. Missing credentials.json raises CalendarAuthError. Every auth step is logged at INFO level.
## Evidence
- Commits: 92fb4a0ec8d7c072aab664d0c9e3bddb86a735e9
- Tests: python3 -m pytest tests/ -v --tb=short (156 passed), python3 -m ruff check (all passed), python3 -c 'from cal_ai.calendar import get_calendar_credentials' (import OK)
- PRs: