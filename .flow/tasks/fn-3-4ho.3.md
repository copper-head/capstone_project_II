# fn-3-4ho.3 Build system prompt and user prompt (prompts.py)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Implemented prompts.py with three functions: build_system_prompt() for the Gemini system instruction (owner perspective, relative time resolution, ambiguity handling, JSON format), build_user_prompt() to wrap transcript text, and format_transcript_for_llm() to convert parsed Utterance objects into clean "Speaker: text" format. Exported all three from the top-level package.
## Evidence
- Commits: 36704c5e22395af501668847f1f2286240f61de2
- Tests: PYTHONPATH=src python3 -m pytest tests/ -v (93 passed), python3 -m ruff check src/cal_ai/prompts.py (all checks passed)
- PRs: