# fn-4-gyw.3 Implement event mapper (calendar/event_mapper.py)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Implemented the event mapper module (calendar/event_mapper.py) that converts ValidatedEvent instances into Google Calendar API event body dicts, mapping summary, location, start/end with timezone, LLM reasoning in description, and owner-email attendee handling.
## Evidence
- Commits: 7edac0d19c5fe076464a40421e827debffc84e0a
- Tests: ruff check src/cal_ai/calendar/event_mapper.py, ruff format --check src/cal_ai/calendar/event_mapper.py, python3 -c ast.parse (syntax check)
- PRs: