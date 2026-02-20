# Conversation-to-Calendar AI

## Project Overview
AI pipeline: conversation transcripts → Gemini Flash 3 extracts events → Google Calendar CRUD.
Single-user demo product. See `docs/SPEC.md` for full specification.

## Tech Stack
- **Language:** Python 3.12+
- **LLM:** Google Gemini Flash 3 (via `google-genai` SDK)
- **Calendar:** `google-api-python-client` (direct, not MCP)
- **Auth:** OAuth 2.0 Desktop app flow
- **Container:** Docker
- **Config:** `.env` file + owner config

## Project Structure
```
src/cal_ai/           # Main package (src layout)
  __init__.py          # Package init, __version__
  __main__.py          # python -m cal_ai entrypoint
  config.py            # Settings dataclass, load_settings(), ConfigError
  log.py               # setup_logging(), get_logger()
tests/                # Test suite (pytest)
  unit/                # Unit tests (test_config, test_log, test_package)
  integration/         # Integration tests
  regression/          # Regression test suite (mock + live modes)
    conftest.py        # --live flag, auto-parametrize from samples
    schema.py          # SidecarSpec Pydantic model
    loader.py          # Sample discovery and sidecar loading
    tolerance.py       # Tolerance assertion engine (strict/moderate/relaxed)
    test_regression.py # Parametrized regression tests
samples/              # Test transcripts organized by category
  crud/                # Basic CRUD operations (create, update, delete)
  multi_speaker/       # Multi-speaker conversations
  adversarial/         # Edge cases (sarcasm, negation, hypotheticals)
  realistic/           # Real-world patterns (typos, slang, interruptions)
  long/                # Long transcripts (80+ lines)
docs/SPEC.md          # System specification
pyproject.toml        # Metadata, deps, ruff/pytest config
Makefile              # Dev workflow targets
Dockerfile            # Python 3.12-slim container
docker-compose.yml    # Service definition with mounts
.env.example          # Environment variable template
credentials.json      # OAuth 2.0 client credentials (gitignored)
token.json            # Cached OAuth tokens (gitignored, auto-generated)
.env                  # Environment variables (gitignored)
```

## Commands
All dev workflow commands are available via `make`:
```bash
make install             # Install package in editable mode with dev deps
make lint                # Run ruff check and format check
make format              # Auto-format with ruff (format + fix)
make test                # Run pytest (all tests including regression mock mode)
make test-cov            # Run pytest with coverage report
make test-regression     # Run regression suite only (mock mode)
make test-regression-live # Run regression suite with live Gemini API
make build               # Build Docker image (docker compose build)
make run                 # Run container (docker compose up)
make clean               # Remove caches, coverage, build artifacts
```

Direct commands (without make):
```bash
python -m cal_ai              # Run the application
pip install -e ".[dev]"       # Install editable with dev deps
pytest                        # Run tests (all including regression mock mode)
pytest tests/regression/ -v   # Run regression suite only (mock mode)
pytest tests/regression/ --live -v  # Run regression suite (live Gemini API)
pytest tests/regression/ -k crud -v # Run only CRUD category tests
ruff check .                  # Lint
ruff format --check .         # Check formatting
docker compose up             # Run in Docker
```

## Environment Variables
Required in `.env`:
- `GEMINI_API_KEY` — Google Gemini API key
- `GOOGLE_ACCOUNT_EMAIL` — Calendar owner's email
- `OWNER_NAME` — Name used for event perspective (e.g., "Alice")

## Architecture: Calendar-Aware CRUD Intelligence

The pipeline uses a multi-stage flow with calendar context injection:

```
Transcript -> Parser -> Calendar Context Fetch (14-day window)
  -> LLM Extraction (transcript + calendar context) -> Sync Dispatch -> Google Calendar
```

**CRUD intelligence:** Before calling the LLM, the pipeline fetches the owner's
upcoming 14 days of calendar events and injects them into the prompt as compact
context with integer ID remapping (reduces LLM error rates from ~50% with UUIDs
to ~5% with integers). The LLM then makes intelligent create/update/delete
decisions by matching conversation references to existing events and outputting
the appropriate action with the matched event's integer ID.

**Sync dispatch:** When `existing_event_id` is present and found in the ID map,
direct API calls (`update_event`/`delete_event`) are used. On HTTP 404: updates
fall back to create, deletes are treated as idempotent success. Without an event
ID, search-based methods are used as fallback.

**Graceful degradation:** If calendar credentials are unavailable or context
fetch fails, the pipeline continues without context (current create-only behavior).

## Key Conventions
- Pipeline architecture: LLM outputs structured JSON, Python handles calendar ops
- All AI reasoning must be logged (demo requirement)
- All calendar operations must be logged
- Ambiguous events get created anyway with notes on assumptions
- Input format: `[Speaker Name]: dialogue text`
- Integer ID remapping for calendar context (never expose UUIDs to LLM)
- Each sample transcript (`samples/<category>/<name>.txt`) has a sidecar `<name>.expected.json` containing: tolerance level (strict/moderate/relaxed), calendar context, expected events, and a `mock_llm_response` for deterministic mock-mode testing
- Regression tests auto-discover samples via `pytest_generate_tests`; mock mode is the default, `--live` flag enables real Gemini API calls

## Security
- Never commit `.env`, `credentials.json`, or `token.json`
- Never log actual API keys or OAuth tokens
