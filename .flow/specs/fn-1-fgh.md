# fn-1: Project Scaffolding

## Summary
Bootstrap the Python project structure, dependency management, Docker setup, configuration loading, and logging framework. Everything else builds on top of this.

## Architecture Decision: `src` Layout
Use `src/cal_ai/` (not flat). Prevents accidental imports of uninstalled package, forces `pip install -e .` to work before tests run, aligns with PyPA recommendations.

---

## Task Breakdown

### Task 1: Create `pyproject.toml`
Project metadata, runtime deps, dev deps, and all tool config in one file.

**Project metadata:** name `cal-ai`, version `0.1.0`, requires-python `>=3.12`

**Runtime dependencies:**
- `python-dotenv>=1.0`
- `google-genai>=1.0`
- `google-api-python-client>=2.0`
- `google-auth-oauthlib>=1.0`
- `google-auth-httplib2>=0.2`

**Dev dependencies** (`[project.optional-dependencies] dev`):
- `pytest>=8.0`
- `pytest-cov>=5.0`
- `ruff>=0.9`

**Tool config:**
- `[tool.ruff]` — target Python 3.12, line-length 99, select E/F/W/I/UP/B/SIM/N
- `[tool.ruff.format]` — double quotes, spaces
- `[tool.pytest.ini_options]` — testpaths, pythonpath, verbose + coverage

### Task 2: Create package structure
```
src/cal_ai/
    __init__.py       # __version__ = "0.1.0", docstring
    __main__.py       # Stub: prints "cal-ai: not yet implemented", exits 0
    config.py         # Configuration loading
    log.py            # Structured logging (named log.py to avoid stdlib collision)
```

### Task 3: Implement `config.py`
- `Settings` frozen dataclass with fields: `gemini_api_key`, `google_account_email`, `owner_name`, `log_level` (default "INFO"), `timezone` (default "America/Vancouver")
- `load_settings()` → calls `dotenv.load_dotenv()`, reads env vars, validates, returns `Settings`
- `ConfigError(Exception)` — raised when required vars missing/empty/whitespace-only
- Error message names ALL missing variables
- `__repr__` masks `gemini_api_key` with `***`

### Task 4: Implement `log.py`
- `setup_logging(level: str = "INFO")` — configures root logger with structured formatter
- Format: `%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`
- ISO 8601 timestamps, StreamHandler to stderr
- Idempotent (no duplicate handlers on repeated calls)
- `get_logger(name: str)` — convenience wrapper around `logging.getLogger`
- Invalid level string raises `ValueError`

### Task 5: Create `Dockerfile`
- `FROM python:3.12-slim`, `WORKDIR /app`
- Copy `pyproject.toml` first (layer caching), `pip install --no-cache-dir .`
- Copy `src/`, `CMD ["python", "-m", "cal_ai"]`
- Do NOT copy `.env`, `credentials.json`, `token.json`

### Task 6: Create `docker-compose.yml`
- Service `cal-ai`, build from `.`, `env_file: .env`
- Volume mounts for `credentials.json`, `token.json`, `samples/`

### Task 7: Create `.env.example`
```
# Required
GEMINI_API_KEY=your_gemini_api_key_here
GOOGLE_ACCOUNT_EMAIL=you@gmail.com
OWNER_NAME=YourName

# Optional
LOG_LEVEL=INFO
TIMEZONE=America/Vancouver
```

### Task 8: Create `.dockerignore`
Exclude `.env`, credentials, `.git`, tests, docs, `.flow/`, caches.

### Task 9: Create `Makefile`
Targets: `install`, `lint`, `format`, `test`, `test-cov`, `build`, `run`, `clean` with `.PHONY` declarations.

### Task 10: Create test structure
```
tests/
    __init__.py
    conftest.py          # Shared fixtures (monkeypatch_env, clean_env)
    unit/
        __init__.py
        test_config.py
        test_log.py
        test_package.py
    integration/
        __init__.py
```

### Task 11: Update `.gitignore`
Add: `.ruff_cache/`, `.pytest_cache/`, `*.egg-info/`, `dist/`, `build/`, `.coverage`, `htmlcov/`

### Task 12: Update `CLAUDE.md`
Update commands section with actual Makefile targets.

---

## File Inventory

| File | Action | Description |
|---|---|---|
| `pyproject.toml` | CREATE | Metadata, deps, ruff/pytest config |
| `src/cal_ai/__init__.py` | CREATE | Package init, `__version__` |
| `src/cal_ai/__main__.py` | CREATE | `python -m cal_ai` stub |
| `src/cal_ai/config.py` | CREATE | Settings dataclass, load_settings(), ConfigError |
| `src/cal_ai/log.py` | CREATE | setup_logging(), get_logger() |
| `Dockerfile` | CREATE | Python 3.12-slim container |
| `docker-compose.yml` | CREATE | Service definition with mounts |
| `.env.example` | CREATE | Template with placeholders |
| `.dockerignore` | CREATE | Build context exclusions |
| `Makefile` | CREATE | Dev workflow targets |
| `tests/__init__.py` | CREATE | Empty |
| `tests/conftest.py` | CREATE | Shared env fixtures |
| `tests/unit/__init__.py` | CREATE | Empty |
| `tests/unit/test_config.py` | CREATE | Config tests |
| `tests/unit/test_log.py` | CREATE | Logging tests |
| `tests/unit/test_package.py` | CREATE | Package structure tests |
| `tests/integration/__init__.py` | CREATE | Empty |
| `.gitignore` | MODIFY | Add cache/build entries |
| `CLAUDE.md` | MODIFY | Update commands |

---

## Required Tests

### `tests/unit/test_package.py` (6 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_package_is_importable` | `import cal_ai` works | No ImportError |
| `test_package_has_version` | `cal_ai.__version__` defined | Returns `"0.1.0"` |
| `test_package_version_is_semver` | Version format | Matches `r"^\d+\.\d+\.\d+$"` |
| `test_main_module_exists` | `python -m cal_ai` runs | Exit code 0, no traceback |
| `test_config_module_importable` | `from cal_ai.config import load_settings, ConfigError` | No ImportError |
| `test_logging_module_importable` | `from cal_ai.log import setup_logging, get_logger` | No ImportError |

### `tests/unit/test_config.py` (19 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_load_settings_with_all_vars_set` | Happy path — all vars present | Returns Settings with correct values |
| `test_load_settings_missing_gemini_api_key` | GEMINI_API_KEY not set | Raises ConfigError mentioning "GEMINI_API_KEY" |
| `test_load_settings_missing_google_account_email` | GOOGLE_ACCOUNT_EMAIL not set | Raises ConfigError mentioning "GOOGLE_ACCOUNT_EMAIL" |
| `test_load_settings_missing_owner_name` | OWNER_NAME not set | Raises ConfigError mentioning "OWNER_NAME" |
| `test_load_settings_missing_multiple_vars` | Two+ vars missing | Raises ConfigError naming ALL missing vars |
| `test_load_settings_empty_string_gemini_key` | GEMINI_API_KEY="" | Raises ConfigError |
| `test_load_settings_empty_string_email` | GOOGLE_ACCOUNT_EMAIL="" | Raises ConfigError |
| `test_load_settings_empty_string_owner` | OWNER_NAME="" | Raises ConfigError |
| `test_load_settings_whitespace_only_value` | OWNER_NAME="   " | Raises ConfigError |
| `test_settings_repr_masks_api_key` | repr(settings) | Does NOT contain actual key, shows *** |
| `test_settings_repr_shows_email` | repr(settings) | Contains email value |
| `test_settings_repr_shows_owner` | repr(settings) | Contains owner name |
| `test_settings_is_frozen` | Mutate a field | Raises FrozenInstanceError/AttributeError |
| `test_config_error_is_exception` | ConfigError class | Subclass of Exception |
| `test_config_error_message` | ConfigError("msg") | str(e) returns "msg" |
| `test_load_settings_default_log_level` | LOG_LEVEL not set | Defaults to "INFO" |
| `test_load_settings_custom_log_level` | LOG_LEVEL=DEBUG | Returns "DEBUG" |
| `test_load_settings_default_timezone` | TIMEZONE not set | Defaults to "America/Vancouver" |
| `test_load_settings_custom_timezone` | TIMEZONE=US/Eastern | Returns "US/Eastern" |

### `tests/unit/test_log.py` (15 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_setup_logging_does_not_raise` | setup_logging() call | No exception |
| `test_setup_logging_sets_level` | setup_logging("DEBUG") | Root logger level is DEBUG |
| `test_setup_logging_default_level_is_info` | setup_logging() no arg | Root logger level is INFO |
| `test_setup_logging_invalid_level_raises` | setup_logging("INVALID") | Raises ValueError |
| `test_setup_logging_adds_handler` | After setup_logging() | Root logger has StreamHandler |
| `test_setup_logging_idempotent` | Call twice | No duplicate handlers |
| `test_get_logger_returns_logger` | get_logger("test") | Returns logging.Logger |
| `test_get_logger_name` | get_logger("cal_ai.test") | Logger name equals "cal_ai.test" |
| `test_log_output_contains_level` | Log INFO, capture stderr | Contains "INFO" |
| `test_log_output_contains_logger_name` | Log with named logger | Contains logger name |
| `test_log_output_contains_message` | Log "hello world" | Contains "hello world" |
| `test_log_output_contains_timestamp` | Log message | Contains ISO 8601 pattern |
| `test_log_output_has_pipe_separators` | Log message | Contains " | " separators |
| `test_debug_not_shown_at_info_level` | Level=INFO, log DEBUG | DEBUG not in output |
| `test_debug_shown_at_debug_level` | Level=DEBUG, log DEBUG | DEBUG in output |

### Non-pytest Validation Checks

| Check | Command | Expected |
|---|---|---|
| Editable install | `pip install -e ".[dev]"` | Exit code 0 |
| Ruff lint | `ruff check .` | Exit code 0 |
| Ruff format | `ruff format --check .` | Exit code 0 |
| Pytest | `pytest` | All 40 tests pass |
| Docker build | `docker build .` | Exit code 0 |
| Package run | `python -m cal_ai` | Exit code 0, stub output |

**Total: 40 unit tests + 6 validation checks**

---

## Implementation Order
1. Tasks 1-4 (pyproject.toml + package + config + log) — one work unit
2. Tasks 5-9 (Docker + env.example + dockerignore + Makefile) — second unit
3. Tasks 10-12 (tests + gitignore + CLAUDE.md update) — third unit

## Notes
- `log.py` not `logging.py` — avoids stdlib name collision
- Frozen dataclass for Settings, not Pydantic — simpler for 3 string fields
- `.env` currently has `GOOGLE_ACCOUNT_PASSWORD` — not needed (OAuth), user responsibility to clean up
