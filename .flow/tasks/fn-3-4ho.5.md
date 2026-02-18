# fn-3-4ho.5 Create custom exceptions (MalformedResponseError, ExtractionError)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Created custom exceptions module with MalformedResponseError (for JSON/schema parse failures, includes raw_response attribute) and ExtractionError (for unrecoverable extraction failures). Both exported from top-level cal_ai package.
## Evidence
- Commits: ba8ea0d130a038fd3c7c50a9a48056beee3f1831
- Tests: python3 -m pytest tests/ -v
- PRs: