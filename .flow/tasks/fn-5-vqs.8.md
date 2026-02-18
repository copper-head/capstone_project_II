# fn-5-vqs.8 Write unit tests for demo output (10 tests)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Added 10 unit tests for the demo output formatter (demo_output.py), covering all specified test cases: transcript info display, extracted events, AI reasoning, calendar operations, summary counts, zero-events message, dry-run markers, failed event errors, assumptions rendering, and pipeline duration.
## Evidence
- Commits: 3e7529330188e07b89c91e3c9dc173d729f0e077
- Tests: python3 -m pytest tests/unit/test_demo_output.py -v, python3 -m pytest tests/ -v
- PRs: