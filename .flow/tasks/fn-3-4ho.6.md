# fn-3-4ho.6 Write unit tests for extraction models (12 tests)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Added 12 unit tests for the LLM extraction Pydantic models (ExtractedEvent, ExtractionResult, ValidatedEvent) covering valid instantiation, required field validation, invalid enum values, default end_time logic, ISO datetime parsing, and invalid datetime rejection.
## Evidence
- Commits: cac877e05d2af1162a7c8edfdc6becae23c851e9
- Tests: python3 -m pytest tests/unit/test_models_extraction.py -v, python3 -m pytest --tb=short
- PRs: