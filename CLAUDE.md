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
  integration/         # Integration tests (future)
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
make install    # Install package in editable mode with dev deps
make lint       # Run ruff check and format check
make format     # Auto-format with ruff (format + fix)
make test       # Run pytest
make test-cov   # Run pytest with coverage report
make build      # Build Docker image (docker compose build)
make run        # Run container (docker compose up)
make clean      # Remove caches, coverage, build artifacts
```

Direct commands (without make):
```bash
python -m cal_ai              # Run the application
pip install -e ".[dev]"       # Install editable with dev deps
pytest                        # Run tests
ruff check .                  # Lint
ruff format --check .         # Check formatting
docker compose up             # Run in Docker
```

## Environment Variables
Required in `.env`:
- `GEMINI_API_KEY` — Google Gemini API key
- `GOOGLE_ACCOUNT_EMAIL` — Calendar owner's email
- `OWNER_NAME` — Name used for event perspective (e.g., "Alice")

## Key Conventions
- Pipeline architecture: LLM outputs structured JSON, Python handles calendar ops
- All AI reasoning must be logged (demo requirement)
- All calendar operations must be logged
- Ambiguous events get created anyway with notes on assumptions
- Input format: `[Speaker Name]: dialogue text`

## Security
- Never commit `.env`, `credentials.json`, or `token.json`
- Never log actual API keys or OAuth tokens
