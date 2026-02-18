# fn-3-4ho.4 Build GeminiClient with extract_events, parse, validate, retry (llm.py)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Implemented GeminiClient in llm.py with extract_events(), _parse_response(), validate_events(), and single-retry logic. The client wraps google-genai SDK, handles "none" sentinel conversion, comma-separated string splitting, structured logging at all levels, and graceful fallback on malformed responses.
## Evidence
- Commits: 4c8a0e12387dce33ff965691cd99b2a193467008
- Tests: python3 -m pytest tests/ -x --no-header, python3 -m ruff check src/cal_ai/llm.py src/cal_ai/__init__.py
- PRs: