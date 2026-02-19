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
python -m cal_ai samples/simple_lunch.txt

# Dry run (extract events without syncing to calendar)
python -m cal_ai samples/mixed_crud.txt --dry-run

# Verbose logging (shows AI reasoning, API calls)
python -m cal_ai samples/clear_schedule.txt -v

# Override the calendar owner name
python -m cal_ai samples/multiple_events.txt --owner "Alice"
```

### Docker

```bash
docker compose build
docker compose up
```

The default entrypoint runs `samples/simple_lunch.txt`. Mount a different transcript:

```bash
docker compose run cal-ai samples/mixed_crud.txt
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

| File | Scenario |
|---|---|
| `simple_lunch.txt` | Basic lunch event between two people |
| `multiple_events.txt` | Several events in one conversation |
| `ambiguous_time.txt` | Vague time references the AI must resolve |
| `cancellation.txt` | Event cancellation |
| `update_meeting.txt` | Rescheduling an existing meeting |
| `cancel_event.txt` | Cancelling an existing event |
| `mixed_crud.txt` | Create + update + delete in one conversation |
| `clear_schedule.txt` | Bulk delete — clear all events for 3 days |
| `no_events.txt` | Conversation with no calendar-relevant content |

## Development

```bash
# Run tests (313 tests, 92% coverage)
make test

# Lint
make lint

# Auto-format
make format

# Coverage report
make test-cov
```

### Project Structure

```
src/cal_ai/
├── __main__.py          # CLI entrypoint
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
└── calendar/
    ├── client.py         # Google Calendar CRUD client
    ├── context.py        # Calendar context fetcher + ID remapping
    ├── auth.py           # OAuth 2.0 credential management
    ├── event_mapper.py   # ValidatedEvent → Google API body
    ├── sync.py           # Batch sync orchestrator
    └── exceptions.py     # Custom exceptions + @with_retry decorator
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
| Testing | pytest (313 tests, 92% coverage) |
| Linting | ruff |

## License

MIT
