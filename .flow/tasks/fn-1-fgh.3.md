# fn-1-fgh.3 Implement config.py (Settings dataclass, load_settings, ConfigError)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Implemented config.py with frozen Settings dataclass (gemini_api_key, google_account_email, owner_name, log_level, timezone), load_settings() that reads env vars via python-dotenv and validates required fields, ConfigError for missing/invalid config, and custom __repr__ that masks the API key.
## Evidence
- Commits: 01a3458611db4bea9f60758e23f464025621f80c
- Tests: python3 -c (10 manual functional tests from /tmp)
- PRs: