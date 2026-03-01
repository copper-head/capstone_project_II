# Architecture

Cal-AI is a 5-stage pipeline that converts conversation transcripts into Google Calendar operations, backed by a persistent memory system that accumulates scheduling-relevant facts across runs.

## Pipeline Overview

```
                         ┌─────────────────┐
                         │  Transcript File │
                         └────────┬────────┘
                                  │
                    Stage 1: Parse transcript
                                  │
                                  v
                     ┌────────────────────────┐
                     │  Speakers + Utterances  │
                     └────────────┬───────────┘
                                  │
                  Stage 1b: Load memories from SQLite
                                  │
                                  v
                     ┌────────────────────────┐
                     │    Memory Context       │
                     │  (preferences, people,  │
                     │   patterns, etc.)       │
                     └────────────┬───────────┘
                                  │
                  Stage 1c: Fetch calendar context (14-day window)
                                  │
                                  v
                     ┌────────────────────────┐
                     │   Calendar Context      │
                     │  (events with integer   │
                     │   ID remapping)         │
                     └────────────┬───────────┘
                                  │
                    Stage 2: LLM extraction via Gemini
                        (transcript + memory + calendar)
                                  │
                                  v
                     ┌────────────────────────┐
                     │   Extracted Events      │
                     │  (create/update/delete  │
                     │   with event IDs)       │
                     └────────────┬───────────┘
                                  │
                    Stage 3: Sync dispatch to Google Calendar
                                  │
                                  v
                     ┌────────────────────────┐
                     │   Sync Results          │
                     │  (created/updated/      │
                     │   deleted events)       │
                     └────────────┬───────────┘
                                  │
                    Stage 4: Memory write path
                        (fact extraction + action decision)
                                  │
                                  v
                     ┌────────────────────────┐
                     │   Updated Memory DB     │
                     │  (new/modified facts)   │
                     └────────────┬───────────┘
                                  │
                    Stage 5: Summary output
                                  │
                                  v
                     ┌────────────────────────┐
                     │   Console Output        │
                     └────────────────────────┘
```

## Stage Details

### Stage 1: Transcript Parsing

**Module:** `src/cal_ai/parser.py`

Reads a plain-text file with `[Speaker]: text` formatted lines. Produces a list of `Utterance` objects (speaker name + text) and a set of unique speakers. Lines that don't match the speaker pattern are treated as continuations.

### Stage 1b: Memory Read Path

**Module:** `src/cal_ai/memory/store.py`, `src/cal_ai/memory/formatter.py`

Loads all stored memories from the owner's SQLite database. Memories are grouped by category and formatted as a `## Your Memory (about {owner_name})` section that gets injected into the system prompt before the calendar context section.

Categories:
- **preferences** — scheduling preferences ("Alice prefers morning meetings")
- **people** — facts about contacts ("Bob handles budget proposals")
- **vocabulary** — owner-specific terminology
- **patterns** — recurring scheduling patterns ("Sprint retros are 1 hour")
- **corrections** — past extraction mistakes to avoid

When no memories exist, the section is omitted entirely, making the system byte-for-byte backward compatible with pre-memory behavior.

**Graceful degradation:** If the memory store fails to load, a warning is logged and the pipeline continues without memory context.

### Stage 1c: Calendar Context Fetch

**Module:** `src/cal_ai/calendar/context.py`

Fetches the owner's upcoming 14 days of Google Calendar events via the Calendar API. Events are formatted as compact text with **integer ID remapping** — Google Calendar UUIDs are replaced with sequential integers (1, 2, 3...) to reduce LLM hallucination rates. The reverse mapping is preserved for use during sync dispatch.

Example context injected into the prompt:
```
[1] Team Standup | 2026-03-05T09:00:00 - 2026-03-05T09:30:00
[2] Lunch with Bob | 2026-03-05T12:00:00 - 2026-03-05T13:00:00
```

**Graceful degradation:** If credentials are unavailable or the API call fails, the pipeline continues without calendar context (create-only behavior).

### Stage 2: LLM Extraction

**Module:** `src/cal_ai/llm.py`, `src/cal_ai/prompts.py`

Sends the transcript to Gemini along with the memory context and calendar context. The system prompt includes:

- Owner perspective rules (whose calendar is this for?)
- 14 "Do NOT Extract" filtering rules (past events, sarcasm, complaints, hypotheticals, etc.)
- CRUD decision rules with asymmetric confidence thresholds
- Few-shot examples (positive and negative)
- Bulk operation handling ("clear my schedule" → multiple deletes)
- Conflicting instruction resolution (last statement wins)

The LLM returns structured JSON: an array of events, each with `action` (create/update/delete), `title`, `start_time`, `end_time`, `confidence`, `reasoning`, and optionally `existing_event_id` for updates/deletes.

Response parsing uses Pydantic validation. If the response is malformed, one retry is attempted.

### Stage 3: Sync Dispatch

**Module:** `src/cal_ai/calendar/sync.py`, `src/cal_ai/calendar/client.py`

Each extracted event is dispatched to the Google Calendar API:

- **create** — `events.insert()` (with duplicate detection via time-window search)
- **update** — Resolves `existing_event_id` through the integer→UUID reverse map, then calls `events.update()`. Falls back to create on HTTP 404.
- **delete** — Resolves ID and calls `events.delete()`. 404 is treated as idempotent success.

When no `existing_event_id` is provided for update/delete, a search-based fallback matches by title and time window.

### Stage 4: Memory Write Path

**Module:** `src/cal_ai/memory/extraction.py`, `src/cal_ai/memory/prompts.py`

After calendar sync, two separate Gemini calls update the memory store:

**Call 1 — Fact Extraction:**
- Input: transcript text + extracted events + owner name
- Output: candidate facts, each with `category`, `key`, `value`, `confidence`
- The prompt includes negative few-shot examples (sarcasm, hypotheticals, trivial conversations) to enforce conservative extraction

**Call 2 — Action Decision:**
- Input: candidate facts + existing memories (integer-remapped, same pattern as calendar context)
- Output: actions (ADD/UPDATE/DELETE/NOOP) with reasoning and confidence
- ADD and UPDATE dispatch to `MemoryStore.upsert()`
- DELETE dispatches to `MemoryStore.delete()`
- All operations are logged to the `memory_log` audit table

The write path runs even when zero events are extracted (conversations can contain memory-worthy facts without scheduling content). It is skipped entirely in dry-run mode.

**Graceful degradation:** Write path failure logs a warning but the pipeline returns success (events were already synced).

### Stage 5: Summary Output

**Module:** `src/cal_ai/demo_output.py`

Renders a formatted console report showing all stages: transcript info, extracted events with AI reasoning, calendar operations performed, and memory changes.

## Memory System Architecture

### Storage

Each owner gets a separate SQLite database file, auto-generated from a slugified `OWNER_NAME`:

```
data/memory_alice.db        # OWNER_NAME=Alice
data/memory_alice_smith.db  # OWNER_NAME=Alice Smith
```

The `MEMORY_DB_PATH` environment variable overrides the auto-generated path.

### Schema

**`memories` table:**

| Column | Type | Description |
|---|---|---|
| id | INTEGER | Primary key (auto-increment) |
| category | TEXT | One of: preferences, people, vocabulary, patterns, corrections |
| key | TEXT | Unique identifier within category |
| value | TEXT | The fact content |
| confidence | TEXT | high / medium / low |
| source_count | INTEGER | Number of conversations that contributed to this fact |
| created_at | TEXT | ISO 8601 timestamp |
| updated_at | TEXT | ISO 8601 timestamp |

Unique constraint on `(category, key)`. Upsert increments `source_count` and updates `value`/`confidence`/`updated_at`.

**`memory_log` table:**

Audit trail of all memory operations (action, category, key, old_value, new_value, reasoning, timestamp).

### Integer ID Remapping

Same pattern used for calendar context — existing memories are presented to the LLM with sequential integer IDs instead of database row IDs. This reduces error rates and prevents the LLM from hallucinating or misreferencing IDs.

### Duck Typing

The memory formatter accepts any object with `category`, `key`, and `value` attributes. This allows it to work with both `MemoryRecord` (production) and test fixtures without coupling.

## CRUD Intelligence

### ID Remapping Strategy

Both calendar context and memory context use integer ID remapping — a pattern where internal identifiers (Google Calendar UUIDs, SQLite row IDs) are replaced with sequential integers before being shown to the LLM. This was one of the most impactful design decisions:

- UUID-based references had ~50% LLM error rates (hallucinated IDs, truncated strings)
- Integer-based references reduced error rates to ~5%
- The reverse mapping is maintained in memory for resolving back to real IDs during dispatch

### Prompt Engineering

The extraction prompt went through 12 iterations of prompt engineering, tracked in `reports/iteration_log.md`. Key progression:

| Run | Train F1 | Val F1 | Key Change |
|---|---|---|---|
| 0 | 0.72 | — | Baseline |
| 1 | 0.72 | 0.86 | Added anti-extraction rules |
| 4 | 0.90 | 0.88 | Professional title rules |
| 7 | 0.93 | 0.90 | Availability signaling filter |
| 9 | 0.98 | 0.88 | Topic-specific titles |
| 12 | 0.97 | 0.93 | Final (diminishing returns) |

The biggest drivers of improvement were anti-extraction rules (precision) and the grounding check (anti-hallucination).

## Benchmark Suite

**Module:** `src/cal_ai/benchmark/`

The benchmark suite measures extraction accuracy across sample transcripts:

1. Discover samples (`.txt` files with optional `.expected.json` sidecars)
2. For each sample: build calendar context from sidecar → extract via Gemini → score against expected events
3. Aggregate P/R/F1 using the tolerance engine (Hungarian algorithm best-match pairing)
4. Generate console summary + markdown report + JSONL history
5. AI summary: Gemini self-evaluates its own benchmark performance

### Scoring

True positives must match on:
- Action type (create/update/delete)
- Title (within tolerance)
- Time (within tolerance)

Tolerance levels: **strict** (exact match), **moderate** (fuzzy titles, +/-2hr times), **relaxed** (broad matching, +/-1day).

Edge case: both actual and expected empty = vacuous truth (P=R=F1=1.0).

### Training Data

140 total transcripts across three directories:

| Directory | Count | Purpose |
|---|---|---|
| `samples/` | 40 | Regression tests (mock + live) |
| `training/train/` | 70 | Training set for prompt iteration |
| `training/test/` + `training/val/` | 30 | Test and validation splits |

Each transcript has a `.expected.json` sidecar containing:
- `tolerance`: strict / moderate / relaxed
- `calendar_context`: existing events for the scenario
- `expected_events`: ground-truth events
- `mock_llm_response`: deterministic response for mock-mode testing

## Design Decisions

### Pipeline over Agent

The LLM extracts structured JSON data; deterministic Python code handles validation, calendar operations, and memory management. This keeps the system predictable, debuggable, and easy to log — all key demo requirements.

### Direct API over MCP

For a single-user demo, the Google Calendar Python client is simpler and avoids a Node.js sidecar dependency. MCP is a natural upgrade path for future agentic iterations.

### Dual-Call Memory Write

Two separate LLM calls (fact extraction + action decision) rather than a single call because:
- Separation of concerns: extraction focuses on what's factual, action decision focuses on what's changed
- The action decision call can see existing memories, enabling intelligent UPDATE vs ADD decisions
- Easier to debug and audit each step independently

### Per-Owner DB Isolation

Separate SQLite files per owner (rather than a shared DB with owner column) for simplicity and data isolation. Makes it trivial to reset a single owner's memories without affecting others.

### Graceful Degradation

Every optional subsystem (calendar context, memory read, memory write) is wrapped in try/except with warning-level logging. The pipeline never fails due to a subsystem error — it degrades to the next-simplest behavior:
- No calendar credentials → create-only mode
- Memory read failure → no memory context
- Memory write failure → events already synced, just skip memory update
