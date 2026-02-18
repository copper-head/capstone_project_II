# fn-3-4ho.2 Define Pydantic models (ExtractedEvent, ExtractionResult, ValidatedEvent, LLMResponseSchema)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Added four Pydantic models for the LLM extraction pipeline: ExtractedEvent (raw LLM output with string datetimes), ExtractionResult (response wrapper), ValidatedEvent (parsed datetimes with 1-hour default duration), and LLMResponseSchema/LLMResponseEvent (all-required-strings schema for Gemini SDK). Added pydantic>=2.0 as explicit dependency and wired exports through both __init__.py files.
## Evidence
- Commits: a84d737c054ddd858d545246834b5dd3aacd44dc
- Tests: python3 -m pytest tests/ -x --tb=short, python3 -m ruff check src/cal_ai/
- PRs: