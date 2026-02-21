# Cal-AI: Conversation-to-Calendar

An AI pipeline that reads conversation transcripts, extracts calendar events using Google Gemini, and syncs them to Google Calendar with full CRUD intelligence.

```
Transcript  →  Parser  →  Calendar Context  →  Gemini 2.5 Pro  →  Sync  →  Google Calendar
```

The AI sees your existing calendar and decides whether to **create**, **update**, or **delete** events based on what's discussed in the conversation. It doesn't just blindly create — if someone says "move standup to 10am" it updates the existing event, and "cancel the code review" deletes it.

## Quick Start

### Prerequisites

- Python 3.12+
- A [Google Cloud project](https://console.cloud.google.com/) with the Calendar API enabled
- OAuth 2.0 Desktop credentials (`credentials.json`)
- A [Gemini API key](https://aistudio.google.com/apikey)

### Setup

```bash
# Install
pip install -e ".[dev]"

# Configure environment
cp .env.example .env  # then fill in your keys
```

`.env` requires:
```
GEMINI_API_KEY=<your-gemini-api-key>
GOOGLE_ACCOUNT_EMAIL=<your-google-email>
OWNER_NAME=<your-name>
TIMEZONE=America/Vancouver
```

Place your Google OAuth `credentials.json` in the project root. On first run, a browser window opens for consent — the resulting `token.json` is cached automatically.

### Run

```bash
# Run on a transcript
python -m cal_ai samples/crud/simple_lunch.txt

# Dry run (extract events without syncing to calendar)
python -m cal_ai samples/crud/mixed_crud.txt --dry-run

# Verbose logging (shows AI reasoning, API calls)
python -m cal_ai samples/crud/clear_schedule.txt -v

# Override the calendar owner name
python -m cal_ai samples/multi_speaker/multiple_events.txt --owner "Alice"
```

### Docker

```bash
docker compose build
docker compose up
```

The default entrypoint runs `samples/crud/simple_lunch.txt`. Mount a different transcript:

```bash
docker compose run cal-ai samples/crud/mixed_crud.txt
```

## How It Works

1. **Parse** — Reads `[Speaker]: text` formatted transcripts, extracts speakers and utterances.
2. **Calendar Context** — Fetches your next 14 days of events from Google Calendar. Remaps UUIDs to short integer IDs (reduces LLM error rates from ~50% to ~5%).
3. **LLM Extraction** — Gemini 2.5 Pro receives the transcript + your calendar context. It outputs structured JSON with `create`, `update`, or `delete` actions, referencing existing events by ID.
4. **Sync** — Dispatches each action to the Google Calendar API. Direct ID-based calls for updates/deletes, with fallback on 404 (update→create, delete→skip).

### CRUD Intelligence

The prompt includes:
- Decision rules for when to create vs. update vs. delete
- Asymmetric confidence (create=medium OK, update/delete=high only)
- Few-shot examples including bulk operations ("clear my schedule" → multiple deletes)
- Negative examples to prevent common mistakes
- Last-statement-wins for conflicting instructions

### Sample Transcripts

40 sample transcripts organized by category under `samples/`, each paired with a `.expected.json` sidecar for regression testing:

| Category | Count | Examples |
|---|---|---|
| `crud/` | 14 | `simple_lunch` (basic create), `update_meeting` (reschedule), `cancel_event` (single delete), `mixed_crud` (create+update+delete), `clear_schedule` (bulk delete), `conflicting_instructions` (last-statement-wins), `partial_update`, `bulk_delete` |
| `multi_speaker/` | 7 | `complex` (4 speakers), `five_speakers_crosstalk` (5 speakers, cross-talk), `multiple_pairs_events` (4 pairs plan separately), `speakers_disagree` (conflict resolution), `side_conversation` |
| `adversarial/` | 7 | `no_events` (no calendar content), `sarcasm` (absurd suggestions), `negation` (all events declined), `hypothetical` (no concrete plans), `past_tense` (already happened), `vague_reference` |
| `realistic/` | 7 | `ambiguous_time` (vague times), `typos_informal` (heavy typos), `slang_abbreviations` (internet slang), `interruptions` (incomplete sentences), `filler_tangents` (off-topic noise), `callback_rescheduling` |
| `long/` | 5 | `long_meeting_notes` (80+ lines, 3 events), `long_many_events` (100+ lines, 11 events), `long_circular_planning` (plans change mid-conversation), `long_noise_few_events` (mostly small talk) |

## Development

```bash
# Run all tests including regression suite (mock mode)
make test

# Lint
make lint

# Auto-format
make format

# Coverage report
make test-cov
```

### Regression Testing

The regression test suite validates the AI extraction pipeline against all 40 sample transcripts. Each sample has a `.expected.json` sidecar that defines expected events, tolerance level, and a mock LLM response.

**Mock mode** (default) patches the Gemini API with pre-recorded responses for fast, deterministic testing:

```bash
make test-regression              # Run regression suite (mock mode)
pytest tests/regression/ -k crud  # Run only CRUD category
```

**Live mode** calls the real Gemini API (requires `GEMINI_API_KEY`):

```bash
make test-regression-live         # Run regression suite (live mode)
```

Tolerance levels per sample: **strict** (exact match), **moderate** (fuzzy titles, +/-2hr times), **relaxed** (broad matching, +/-1day times).

### Benchmarking

The benchmark suite runs live Gemini extraction across all sample transcripts and scores results using Precision/Recall/F1 metrics. It also generates an AI self-evaluation where Gemini analyzes its own performance.

```bash
# Run benchmark (requires GEMINI_API_KEY)
make benchmark

# Or directly
python -m cal_ai benchmark

# Custom sample directory and output
python -m cal_ai benchmark /path/to/samples/ --output /tmp/reports/
```

**Output:**
- Console summary (stdout) with overall and per-category P/R/F1
- Detailed markdown report in `reports/benchmark_YYYY-MM-DDTHH-MM-SS.md`
- JSONL run history in `reports/benchmark_history.jsonl`
- AI-generated summary: Gemini self-evaluates its extraction performance, identifies failure patterns, and suggests improvements

**Metrics:** Per-sample and aggregate Precision/Recall/F1, confidence calibration (high/medium/low accuracy correlation), token usage, and cost estimation (Gemini 2.5 pricing).

### Project Structure

```
src/cal_ai/
├── __main__.py          # CLI entrypoint (run + benchmark subcommands)
├── pipeline.py          # 4-stage orchestrator
├── llm.py               # Gemini client + response parsing
├── prompts.py           # System/user prompt builders
├── parser.py            # Transcript parser
├── config.py            # Settings from .env
├── demo_output.py       # Console output renderer
├── models/
│   ├── extraction.py    # Pydantic models (ExtractedEvent, ValidatedEvent)
│   ├── transcript.py    # Utterance, TranscriptParseResult
│   └── calendar.py      # SyncResult
├── benchmark/
│   ├── scoring.py       # P/R/F1 metrics, event matching, confidence calibration
│   ├── runner.py        # Sample discovery, live extraction, cost tracking
│   ├── report.py        # Console + markdown report formatters
│   └── summary.py       # AI self-evaluation via Gemini
└── calendar/
    ├── client.py         # Google Calendar CRUD client
    ├── context.py        # Calendar context fetcher + ID remapping
    ├── auth.py           # OAuth 2.0 credential management
    ├── event_mapper.py   # ValidatedEvent → Google API body
    ├── sync.py           # Batch sync orchestrator
    └── exceptions.py     # Custom exceptions + @with_retry decorator

tests/
├── unit/                # Unit tests (config, logging, models, benchmark, etc.)
├── integration/         # Integration tests (CRUD flows, end-to-end)
└── regression/          # Regression suite (mock + live modes)
    ├── conftest.py      # --live flag, auto-parametrize from samples
    ├── schema.py        # SidecarSpec Pydantic model
    ├── loader.py        # Sample discovery and sidecar loading
    ├── tolerance.py     # Tolerance assertion engine (strict/moderate/relaxed)
    └── test_regression.py

samples/                 # 40 transcripts organized by category
├── crud/                # 14 basic CRUD operations
├── multi_speaker/       # 7 multi-speaker conversations
├── adversarial/         # 7 edge cases (sarcasm, negation, hypotheticals)
├── realistic/           # 7 real-world patterns (typos, slang, interruptions)
└── long/                # 5 long transcripts (80+ lines)
```

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.12 |
| LLM | Google Gemini 2.5 Pro |
| Calendar | Google Calendar API (`google-api-python-client`) |
| Auth | OAuth 2.0 (Desktop app flow) |
| Models | Pydantic v2 |
| Container | Docker |
| Testing | pytest (400+ tests, 92% coverage) |
| Linting | ruff |

## License

MIT
