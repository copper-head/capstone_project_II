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
  __main__.py          # python -m cal_ai entrypoint (run, benchmark, memory subcommands)
  config.py            # Settings dataclass, load_settings(), ConfigError, _slugify_owner()
  log.py               # setup_logging(), get_logger()
  benchmark/           # Benchmark suite (P/R/F1 scoring, reports, AI summary)
    __init__.py        # Public API exports
    scoring.py         # Event matching, P/R/F1, confidence calibration
    runner.py          # Sample discovery, live extraction, aggregation
    report.py          # Console + markdown report formatters
    summary.py         # AI-generated self-evaluation via Gemini
  memory/              # Long-term memory system (SQLite-backed)
    __init__.py        # Public API exports (MemoryStore, MemoryRecord, etc.)
    store.py           # SQLite memory store (upsert, delete, load_all, log_action)
    models.py          # Pydantic models (MemoryRecord, ExtractedFact, MemoryAction)
    formatter.py       # Format memories for LLM prompt injection
    extraction.py      # Memory write path orchestration (run_memory_write)
    prompts.py         # Prompt builders for fact extraction + action decision
tests/                # Test suite (pytest)
  unit/                # Unit tests (test_config, test_log, test_package, test_memory_store)
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
reports/              # Benchmark output (gitignored)
data/                 # Memory DB files, per-owner (gitignored)
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
make benchmark           # Run benchmark suite (live Gemini, writes to reports/)
make build               # Build Docker image (docker compose build)
make run                 # Run container (docker compose up)
make clean               # Remove caches, coverage, build artifacts
make clean-memory        # Remove all memory DB files (data/memory*.db*)
```

Direct commands (without make):
```bash
python -m cal_ai              # Run the application
python -m cal_ai benchmark    # Run benchmark suite (default: samples/)
python -m cal_ai benchmark /path/to/samples/ --output /tmp/reports/
python -m cal_ai memory       # Display current memories (grouped by category)
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

Optional:
- `MEMORY_DB_PATH` — Override auto-generated memory DB path. Defaults to `data/memory_{slugified_owner}.db` (e.g., `data/memory_alice_smith.db` for `OWNER_NAME=Alice Smith`). Only set this if you need a custom location.

## Architecture: Calendar-Aware CRUD Intelligence

The pipeline uses a 5-stage flow with memory and calendar context injection:

```
Stage 1:  Transcript -> Parser
Stage 1b: Load Memories from SQLite (per-owner DB)
Stage 1c: Fetch Calendar Context (14-day window)
Stage 2:  LLM Extraction (transcript + memory context + calendar context)
Stage 3:  Sync Dispatch -> Google Calendar
Stage 4:  Memory Write Path (fact extraction + action decision -> SQLite)
Stage 5:  Summary
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

## Architecture: Memory System

The memory system provides persistent storage of scheduling-relevant facts using
a dual-call architecture. See `docs/memory_system_design.tex` for detailed design.

**Read path (Stage 1b):** Memories are loaded from a per-owner SQLite DB, formatted
by category (preferences, people, vocabulary, patterns, corrections), and injected
as a `## Your Memory (about {owner_name})` section in the system prompt before
the calendar context section. When no memories exist, the section is omitted
entirely (byte-for-byte backward compatible with pre-memory behavior).

**Write path (Stage 4):** After calendar sync, two separate Gemini calls handle
memory updates:
1. **Fact extraction** -- transcript + extracted events -> candidate facts with
   category/key/value/confidence. Owner name is threaded in for third-person framing.
   Conservative extraction with negative few-shot examples (sarcasm, hypotheticals,
   trivial conversations produce empty facts).
2. **Action decision** -- candidate facts + existing memories -> ADD/UPDATE/DELETE/NOOP
   actions with integer-remapped memory IDs, reasoning, and final confidence.
   ADD and UPDATE dispatch to `upsert()`, DELETE dispatches to `delete()`.
   All operations are logged to the `memory_log` audit table.

The write path runs even when zero events are extracted (conversations can contain
memory-worthy facts without scheduling content). Skipped entirely in dry-run mode.

**Per-owner DB isolation:** Each owner gets a separate SQLite file, auto-generated
from a slugified `OWNER_NAME` (e.g., `data/memory_alice_smith.db`). The
`_slugify_owner()` function in `config.py` lowercases and replaces spaces/special
characters with underscores. `MEMORY_DB_PATH` env var overrides the auto-generated
path when set.

**Graceful degradation:** Read path failure logs a warning and continues without
memory. Write path failure logs a warning but the pipeline returns success (events
were already synced). Matches the calendar context degradation pattern.

**Key implementation:** `run_memory_write()` in `src/cal_ai/memory/extraction.py`
orchestrates the write path. Pipeline integration is in `src/cal_ai/pipeline.py`
Stage 4.

## Architecture: Benchmark Suite

The benchmark suite (`python -m cal_ai benchmark`) measures extraction accuracy
across all sample transcripts using live Gemini API calls.

```
Discover samples -> Load sidecars -> For each sample:
  Build calendar context from sidecar -> extract_events() via Gemini
  -> Score actual vs expected (P/R/F1) using tolerance engine
-> Aggregate scores -> Console summary + Markdown report + JSONL history
-> AI summary (Gemini self-evaluation of own performance)
```

**Scoring**: Reuses the regression test tolerance engine (Hungarian algorithm
best-match pairing). True positives must match on action AND pass title/time
tolerance checks. P/R edge cases: both empty = vacuous truth (P=R=F1=1.0).

**Cost tracking**: Token usage surfaced from `GeminiClient._call_api()` via
`LLMCallResult`. Gemini 2.5 pricing: $1.25/1M input, $10.00/1M output.

**AI summary**: After scoring, Gemini self-evaluates the benchmark results --
identifies strengths, failure patterns, and suggests improvements. Graceful
failure: if the summary call fails, the report is still complete.

**Output**: Console summary (stdout), detailed markdown report with per-sample
diffs (`reports/benchmark_YYYY-MM-DDTHH-MM-SS.md`), and JSONL history
(`reports/benchmark_history.jsonl`).

## Key Conventions
- Pipeline architecture: LLM outputs structured JSON, Python handles calendar ops
- All AI reasoning must be logged (demo requirement)
- All calendar operations must be logged
- Ambiguous events get created anyway with notes on assumptions
- Input format: `[Speaker Name]: dialogue text`
- Integer ID remapping for calendar context and memory action decisions (never expose raw DB IDs to LLM)
- Each sample transcript (`samples/<category>/<name>.txt`) has a sidecar `<name>.expected.json` containing: tolerance level (strict/moderate/relaxed), calendar context, expected events, and a `mock_llm_response` for deterministic mock-mode testing
- Regression tests auto-discover samples via `pytest_generate_tests`; mock mode is the default, `--live` flag enables real Gemini API calls
- Memory formatter accepts duck-typed objects with `category`/`key`/`value` attributes (works with both `MemoryRecord` and test `SidecarMemoryEntry`)

## Security
- Never commit `.env`, `credentials.json`, `token.json`, or `memory*.db` files
- Never log actual API keys or OAuth tokens
- Memory DB files (`data/memory*.db*`) are gitignored; they contain personal scheduling facts
