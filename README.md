# Cal-AI: Conversation-to-Calendar

An AI pipeline that reads conversation transcripts, extracts calendar events using Google Gemini, and syncs them to Google Calendar with full CRUD intelligence and long-term memory.

```
Transcript  →  Parser  →  Load Memories  →  Calendar Context  →  Gemini  →  Sync  →  Memory Write
```

The AI sees your existing calendar and decides whether to **create**, **update**, or **delete** events based on what's discussed in the conversation. It doesn't just blindly create — if someone says "move standup to 10am" it updates the existing event, and "cancel the code review" deletes it.

Between runs, the system **remembers** scheduling-relevant facts about the owner — people they work with, meeting preferences, recurring patterns — and injects this context into future extractions.

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

# Dry run (extract events without syncing to calendar or writing memories)
python -m cal_ai samples/crud/mixed_crud.txt --dry-run

# Verbose logging (shows AI reasoning, API calls, memory operations)
python -m cal_ai samples/crud/clear_schedule.txt -v

# Override the calendar owner name
python -m cal_ai samples/multi_speaker/multiple_events.txt --owner "Alice"

# View stored memories for the current owner
python -m cal_ai memory
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

The pipeline runs in 5 stages:

1. **Parse** — Reads `[Speaker]: text` formatted transcripts, extracts speakers and utterances.
2. **Memory Load** — Loads stored facts about the owner from a per-owner SQLite database (preferences, people, patterns, vocabulary, corrections). Injected into the LLM prompt as context.
3. **Calendar Context** — Fetches your next 14 days of events from Google Calendar. Remaps UUIDs to short integer IDs (reduces LLM error rates from ~50% to ~5%).
4. **LLM Extraction** — Gemini receives the transcript + memory context + calendar context. It outputs structured JSON with `create`, `update`, or `delete` actions, referencing existing events by ID.
5. **Sync** — Dispatches each action to the Google Calendar API. Direct ID-based calls for updates/deletes, with fallback on 404 (update→create, delete→skip).
6. **Memory Write** — Two additional Gemini calls extract scheduling-relevant facts from the conversation and decide whether to ADD, UPDATE, or DELETE memories in the SQLite store.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for a detailed breakdown of the pipeline, memory system, and benchmark suite.

### CRUD Intelligence

The prompt includes:
- Decision rules for when to create vs. update vs. delete
- Asymmetric confidence (create=medium OK, update/delete=high only)
- Few-shot examples including bulk operations ("clear my schedule" → multiple deletes)
- Negative examples to prevent common mistakes
- Last-statement-wins for conflicting instructions

### Memory System

The memory system gives the AI persistent context across conversations:

- **Read path:** Before extraction, stored memories are loaded and injected into the system prompt grouped by category (preferences, people, vocabulary, patterns, corrections). When no memories exist, the section is omitted entirely.
- **Write path:** After calendar sync, two Gemini calls handle memory updates:
  1. **Fact extraction** — transcript + events → candidate facts with category/key/value/confidence
  2. **Action decision** — candidate facts + existing memories → ADD/UPDATE/DELETE/NOOP actions
- **Per-owner isolation:** Each owner gets a separate SQLite DB file (`data/memory_{owner}.db`)
- **Graceful degradation:** If memory read or write fails, the pipeline continues normally — events still sync

```bash
# View current memories
python -m cal_ai memory

# Clear all memories for the current owner
make clean-memory
```

### Sample Transcripts

40+ sample transcripts organized by category under `samples/`, each paired with a `.expected.json` sidecar for regression testing:

| Category | Count | Examples |
|---|---|---|
| `crud/` | 14 | `simple_lunch` (basic create), `update_meeting` (reschedule), `cancel_event` (single delete), `mixed_crud` (create+update+delete), `clear_schedule` (bulk delete), `conflicting_instructions` (last-statement-wins), `partial_update`, `bulk_delete` |
| `multi_speaker/` | 7 | `complex` (4 speakers), `five_speakers_crosstalk` (5 speakers, cross-talk), `multiple_pairs_events` (4 pairs plan separately), `speakers_disagree` (conflict resolution), `side_conversation` |
| `adversarial/` | 7 | `no_events` (no calendar content), `sarcasm` (absurd suggestions), `negation` (all events declined), `hypothetical` (no concrete plans), `past_tense` (already happened), `vague_reference` |
| `realistic/` | 7 | `ambiguous_time` (vague times), `typos_informal` (heavy typos), `slang_abbreviations` (internet slang), `interruptions` (incomplete sentences), `filler_tangents` (off-topic noise), `callback_rescheduling` |
| `long/` | 5 | `long_meeting_notes` (80+ lines, 3 events), `long_many_events` (100+ lines, 11 events), `long_circular_planning` (plans change mid-conversation), `long_noise_few_events` (mostly small talk) |
| `memory/` | 11 pairs | Paired A/B transcripts testing memory influence. A establishes facts (preferences, people, patterns), B tests recall. Categories: `pref_time`, `pref_location`, `pref_duration`, `pref_override` (negative), `people_relationship`, `people_nickname`, `people_contact`, `people_unknown` (negative), `pattern_recurring`, `pattern_habitual`, `pattern_change` (negative) |

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

### Memory Round-Trip Testing

The memory test suite validates that the memory system influences LLM extraction by running dual-pass tests on paired sample transcripts in `samples/memory/`.

Each pair consists of:
- **A-transcript**: Establishes memory-worthy facts (e.g., "I prefer afternoon meetings")
- **B-transcript**: References those facts ambiguously (e.g., "let's find a time to meet")

The test runner executes two extraction passes per B-sample:
1. **With memory**: Memory context injected, asserts against `expected_events`
2. **Without memory**: Empty memory, asserts against `expected_events_no_memory`

If both passes succeed against their respective expected events, the memory system demonstrably changed the outcome. Negative cases (override, unknown person, pattern change) have identical expected events in both passes, proving memory does not override explicit instructions.

```bash
make test-memory              # Run memory tests (mock mode, deterministic)
make test-memory-live         # Run memory tests (live Gemini API)
```

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
├── __main__.py          # CLI entrypoint (run, benchmark, memory subcommands)
├── pipeline.py          # 5-stage orchestrator
├── llm.py               # Gemini client + response parsing
├── prompts.py           # System/user prompt builders
├── parser.py            # Transcript parser
├── config.py            # Settings from .env, owner slugification
├── demo_output.py       # Console output renderer
├── models/
│   ├── extraction.py    # Pydantic models (ExtractedEvent, ValidatedEvent)
│   ├── transcript.py    # Utterance, TranscriptParseResult
│   └── calendar.py      # SyncResult
├── memory/
│   ├── store.py         # SQLite memory store (upsert, delete, load_all, audit log)
│   ├── models.py        # Pydantic models (MemoryRecord, MemoryFact, MemoryAction)
│   ├── formatter.py     # Format memories for LLM prompt injection
│   ├── extraction.py    # Write path orchestration (run_memory_write)
│   └── prompts.py       # Prompt builders for fact extraction + action decision
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
├── unit/                # Unit tests (config, logging, memory, models, benchmark)
├── integration/         # Integration tests (CRUD flows, end-to-end)
└── regression/          # Regression suite (mock + live modes)
    ├── conftest.py      # --live flag, auto-parametrize from samples
    ├── schema.py        # SidecarSpec Pydantic model
    ├── loader.py        # Sample discovery and sidecar loading
    ├── tolerance.py     # Tolerance assertion engine (strict/moderate/relaxed)
    ├── test_regression.py
    └── test_memory_roundtrip.py  # Memory round-trip dual-pass tests

samples/                 # 40+ transcripts organized by category
├── crud/                # 14 basic CRUD operations
├── multi_speaker/       # 7 multi-speaker conversations
├── adversarial/         # 7 edge cases (sarcasm, negation, hypotheticals)
├── realistic/           # 7 real-world patterns (typos, slang, interruptions)
├── long/                # 5 long transcripts (80+ lines)
└── memory/              # 11 paired A/B transcripts (memory round-trip testing)

training/                # 100 additional transcripts (train/test/val splits)
data/                    # Per-owner memory SQLite DBs (gitignored)
docs/                    # Specification, architecture, memory design docs
reports/                 # Benchmark output (gitignored)
```

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.12 |
| LLM | Google Gemini 2.5 Pro |
| Calendar | Google Calendar API (`google-api-python-client`) |
| Memory | SQLite (per-owner, via `memory/store.py`) |
| Auth | OAuth 2.0 (Desktop app flow) |
| Models | Pydantic v2 |
| Container | Docker |
| Testing | pytest |
| Linting | ruff |

## Benchmark Results

Extraction accuracy measured on 70 training samples (P/R/F1 via Hungarian-algorithm best-match pairing):

| Model | Precision | Recall | F1 | Cost (70 samples) |
|---|---|---|---|---|
| Gemini 2.5 Pro | 0.93 | 0.95 | **0.94** | $0.72 |
| Gemini 3.1 Pro Preview | 0.93 | 0.93 | 0.93 | $0.70 |

Per-category F1 (Gemini 2.5 Pro / 3.1 Pro Preview):
- Adversarial: 0.75 / **1.00**
- CRUD: 0.91 / **0.94**
- Long: **0.96** / 0.86
- Multi-speaker: **0.97** / 0.95
- Realistic: 0.92 / **1.00**

## License

MIT
