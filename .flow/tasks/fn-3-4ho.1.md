# fn-3-4ho.1 Add google-genai dependency to pyproject.toml

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Normalized google-genai version specifier in pyproject.toml to >=1.0.0 per epic spec. Verified dependency installs correctly (resolves to 1.63.0), can be imported, and all 93 existing tests pass.
## Evidence
- Commits: d39bea3f23f0339f5fc2ad186455ea0c609a0cd1
- Tests: python3 -m pytest tests/ --tb=short -q (93 passed), pip install -e . (google-genai 1.63.0 resolved), python3 -c 'import google.genai' (import verified)
- PRs: