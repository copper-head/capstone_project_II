# fn-1-fgh.8 Create .dockerignore

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Created .dockerignore to exclude sensitive files (.env, credentials), version control (.git), project management (.flow/), tests, docs, caches, and IDE files from the Docker build context. Only pyproject.toml and src/ (needed by the Dockerfile) remain in the build context.
## Evidence
- Commits: 34a4c1677703bb41dd6526211f822b1fa50879c3
- Tests: visual inspection of .dockerignore entries against Dockerfile COPY commands
- PRs: