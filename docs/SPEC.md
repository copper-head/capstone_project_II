# Conversation-to-Calendar AI — System Specification

## 1. Project Overview

An AI-powered pipeline that ingests conversation transcripts, extracts calendar-relevant events using a large language model, and automatically creates/manages events on the user's Google Calendar.

This is a **demo product** — a proof-of-concept to demonstrate that modern LLMs can reliably extract scheduling information from natural conversation and act on it. Previous attempts by the research group using earlier LLM generations were unsuccessful ("flopped"), though no specific failure modes were documented.

## 2. Functional Requirements

### 2.1 Input
- **Format:** Plain-text conversation transcripts with speaker labels
- **Structure:** Each line follows the pattern `[Speaker Name]: dialogue text`
- **Delivery:** Complete conversations provided as input (not streamed)
- **Assumption:** Transcripts are accurate and speaker labels are correct (transcription is out of scope)

Example input:
```
[Alice]: Hey, want to grab lunch Thursday at noon?
[Bob]: Sure, how about that new place on 5th?
[Alice]: Perfect, see you there.
```

### 2.2 Processing
- The system must identify calendar-relevant events from conversation context
- For each detected event, extract:
  - **Who** — participants involved
  - **Where** — location (if mentioned)
  - **When** — date, time, duration (if determinable)
  - **What** — event description/title derived from context
- The system must know who its **owner** is (configurable) and determine event relevance from the owner's perspective
- When context is ambiguous or incomplete, the system should **still create the event** with whatever information is available and note what is missing or assumed

### 2.3 Output
- Calendar events are created/updated/deleted on the owner's Google Calendar
- All AI reasoning is logged (why an event was or wasn't created, what assumptions were made)
- All calendar operations are logged (what was created/modified/deleted and why)
- Console output showing the system's decisions and actions

### 2.4 Calendar Operations
The AI has full CRUD control over the owner's Google Calendar:
- **Create** new events
- **Read** existing events (to check for conflicts, duplicates)
- **Update** existing events (e.g., time changes, location updates)
- **Delete** events (e.g., cancellations mentioned in conversation)

## 3. Non-Functional Requirements

### 3.1 Portability
- Must run on any system with Docker installed
- Containerized backend for easy setup and reproducibility

### 3.2 Simplicity
- Minimal dependencies
- Single-language stack (Python)
- No frontend UI required — console/log output is sufficient

### 3.3 Observability
- Clear, readable logs of:
  - Extracted event data (structured)
  - AI reasoning/confidence for each decision
  - Google Calendar API operations and responses
  - Errors and edge cases encountered

## 4. Architecture

### 4.1 Pipeline Design

```
Transcript (text file)
        |
        v
  [Stage 1: Transcript Parser]
        |
        v
  [Stage 1.5: Calendar Context Fetch]  <-- 14-day window via Google Calendar API
        |                                    Integer ID remapping applied
        v
  [Stage 2: LLM Event Extractor]  <-- Gemini Flash 3
        |                              Receives transcript + calendar context
        |                              Outputs action (create/update/delete)
        |                              References existing events by integer ID
        v
  [Event Validator/Formatter]
        |
        v
  [Stage 3: Sync Dispatch]  <-- google-api-python-client
        |                        Direct ID calls for update/delete
        |                        Search-based fallback when no ID
        |                        404 fallback: update->create, delete->skip
        v
  Google Calendar API
```

The system follows a **structured extraction pipeline** — the LLM produces structured event data (JSON), and deterministic Python code handles validation and calendar operations. The LLM does not interact with Google Calendar directly.

**Stage 1.5 (Calendar Context Fetch)** injects the owner's upcoming calendar events into the LLM prompt so it can make intelligent CRUD decisions. Events are formatted with remapped integer IDs (1, 2, 3...) instead of Google Calendar UUIDs to reduce LLM hallucination rates. The reverse mapping is used during sync dispatch to resolve real event IDs for direct API calls. If context fetch fails (e.g., no credentials), the pipeline degrades gracefully to create-only behavior.

This design was chosen over an agentic/MCP approach because:
- Easier to debug (inspect extracted JSON before calendar operations)
- Better logging of AI reasoning (which is a key demo requirement)
- Simpler to swap LLM providers (only the extraction call changes)
- Fewer dependencies (no Node.js sidecar for MCP server)
- MCP remains an easy upgrade path for future agentic iterations

### 4.2 Tech Stack

| Component | Technology |
|---|---|
| Language | Python |
| LLM | Google Gemini Flash 3 |
| Calendar API | `google-api-python-client` (direct) |
| Auth | OAuth 2.0 (Desktop app flow) |
| Containerization | Docker |
| Configuration | `.env` file + owner config |

### 4.3 Key Design Decisions

1. **Pipeline over Agent:** The LLM extracts structured data; Python code handles execution. This keeps the system predictable, debuggable, and easy to log.
2. **Direct API over MCP:** For a demo, the Google Calendar Python client is simpler and avoids a Node.js dependency. MCP is a natural upgrade path if the system moves to agentic control.
3. **Complete conversations only:** No streaming or chunked transcript handling in this version.
4. **Single user:** No multi-tenancy, no user management. One owner, one calendar.

## 5. Configuration

### 5.1 Environment Variables (`.env`)
```
GEMINI_API_KEY=<api_key>
GOOGLE_ACCOUNT_EMAIL=<user_email>
```

### 5.2 Owner Configuration
- Owner name set via config (e.g., config file or env var)
- Used by the LLM to determine whose perspective events are extracted from
- Example: If owner is "Alice", and Alice says "I'll meet Bob Thursday" — that's an event. If Bob says "I'll meet Carol Thursday" and Alice is just overhearing — that may not be.

### 5.3 OAuth Credentials
- `credentials.json` — OAuth 2.0 Desktop client credentials (from Google Cloud Console)
- `token.json` — Cached OAuth tokens (auto-generated after first auth flow)
- Both are gitignored

## 6. Scope

### 6.1 In Scope (Current Demo)
- Parse complete conversation transcripts with speaker labels
- Extract calendar events using Gemini Flash 3
- Create/read/update/delete events on Google Calendar
- Log all AI reasoning and calendar operations
- Dockerized for portability
- Owner identity via config

### 6.2 Out of Scope (Future)
- Audio capture and recording
- Speech-to-text transcription
- Streaming/real-time transcript processing
- Multi-user support
- Web UI or mobile app
- Event approval workflow (human-in-the-loop)
- Notification system
- MCP-based agentic calendar control

## 7. Assumptions

1. Transcripts are accurate and speaker labels are correct
2. The user has a Google account with Calendar access
3. The user has set up a Google Cloud project with Calendar API enabled
4. OAuth consent screen is configured with the user as a test user
5. Gemini API access is available with a valid API key
6. All conversations provided are relevant to the owner (no filtering of unrelated transcripts)

## 8. Known Risks

| Risk | Mitigation |
|---|---|
| LLM hallucinates events not discussed | Log reasoning, validate extracted data structure |
| LLM misses events that were discussed | Test with diverse transcript samples, iterate on prompts |
| Relative time references ("next Thursday") | Provide current date/time context to the LLM |
| Duplicate event creation | Check existing calendar events before creating |
| OAuth token expiry (7-day limit in test mode) | Re-auth when token expires; document the process |
| Previous LLM failures (professor's note) | Unknown failure modes — design for observability so we can diagnose |

## 9. Success Criteria

A successful demo shows:
1. A transcript goes in
2. The system correctly identifies scheduling-relevant conversation
3. Events appear on Google Calendar with accurate who/where/when
4. Logs clearly show the AI's reasoning process
5. Edge cases (vague times, missing locations) are handled gracefully with assumptions noted
