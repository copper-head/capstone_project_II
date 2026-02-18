# fn-1-fgh.6 Create docker-compose.yml

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Created docker-compose.yml with cal-ai service, env_file for .env, and volume mounts for credentials.json (ro), token.json (rw), and samples/ (ro).
## Evidence
- Commits: 9b926e5e143c0512e6086446aabc5daf9b943610
- Tests: docker compose config --quiet
- PRs: