# fn-5-vqs.4 Update CLI entrypoint (__main__.py with argparse)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Replaced the stub __main__.py with a full argparse-based CLI entrypoint supporting positional transcript_file argument, --dry-run, --verbose/-v, and --owner flags. Includes file validation, config-based owner resolution, clear error messages to stderr, and correct exit codes. Updated existing test_package.py to match new CLI behavior.
## Evidence
- Commits: ca3dd2fbf7d011f0579e6117759458c3d74bfc8d
- Tests: python3 -m pytest tests/ -x -q (208 passed), python3 -m cal_ai --help (exit 0), python3 -m cal_ai (exit 2), python3 -m cal_ai /nonexistent/file.txt (exit 1)
- PRs: