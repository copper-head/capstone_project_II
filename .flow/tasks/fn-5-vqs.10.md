# fn-5-vqs.10 Write sample transcript validation and Docker tests (10 tests)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Added 6 sample transcript validation tests (file existence, parseability, speaker counts, utterance counts, casual conversation check) and 4 Docker configuration tests (entrypoint, samples copy, env mounting, default command). All 10 tests pass.
## Evidence
- Commits: 2602efa4677016c579f60ce7552e42473be4cefb
- Tests: python3 -m pytest tests/unit/test_sample_transcripts.py tests/integration/test_docker.py -v --tb=short --no-header
- PRs: