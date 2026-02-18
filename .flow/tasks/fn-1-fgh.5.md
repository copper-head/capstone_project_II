# fn-1-fgh.5 Create Dockerfile (python:3.12-slim)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Created Dockerfile using python:3.12-slim base image with optimized layer caching. Copies only pyproject.toml and src/ (excludes .env, credentials.json, token.json), installs with pip --no-cache-dir, and runs python -m cal_ai.
## Evidence
- Commits: e63844559c51d825678c5672a1a207e95aca3f60
- Tests: docker build validation deferred to fn-1-fgh.10
- PRs: