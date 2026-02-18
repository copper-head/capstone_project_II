# fn-3-4ho.7 Write unit tests for prompts (8 tests)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Added 9 unit tests for the prompt builders module (build_system_prompt, build_user_prompt, format_transcript_for_llm), achieving 100% coverage of prompts.py. Tests verify owner name injection, datetime injection, perspective/ambiguity/relative-time/JSON-format instructions, transcript embedding, and utterance formatting.
## Evidence
- Commits: 62ccf410fd79645be2ebe2027f565bb62acb1876
- Tests: python3 -m pytest tests/unit/test_prompts.py -v
- PRs: