# fn-1-fgh.4 Implement log.py (setup_logging, get_logger)

## Description
TBD

## Acceptance
- [ ] TBD

## Done summary
Implemented log.py with setup_logging() and get_logger() functions. setup_logging configures the root logger with a structured pipe-separated format using ISO 8601 timestamps and StreamHandler to stderr, is idempotent against duplicate handlers, and raises ValueError for invalid level strings. get_logger provides a convenience wrapper around logging.getLogger.
## Evidence
- Commits: 10680352d7b0d26c80af6fda322f5190f5bf12d4
- Tests: PYTHONPATH=src python3 -c 'from cal_ai.log import setup_logging, get_logger; setup_logging(); get_logger("test")'
- PRs: