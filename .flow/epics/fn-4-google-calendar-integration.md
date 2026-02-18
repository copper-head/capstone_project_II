# fn-4: Google Calendar Integration

## Summary
Build the Google Calendar client with full CRUD operations, OAuth 2.0 authentication, duplicate detection, conflict checking, and error handling with retry logic. This is the output layer of the pipeline.

## Dependencies
- fn-1 (config, logging, project structure)
- Shared `ExtractedEvent` model (defined here or by fn-3, whichever runs first)

---

## Task Breakdown

### Task 1: Define shared event models (`src/cal_ai/models.py`)
If not already created by fn-3, define:

- **`ExtractedEvent`** — input from LLM extraction
  - `title: str`, `start_time: datetime`, `end_time: datetime | None` (default +1hr)
  - `location: str | None`, `attendees: list[str]`
  - `confidence: Literal["high", "medium", "low"]`
  - `reasoning: str`, `assumptions: list[str]`
  - `action: Literal["create", "update", "delete"]`

- **`SyncResult`** — output from sync orchestration
  - `created: int`, `updated: int`, `deleted: int`, `skipped: int`
  - `conflicts: list[dict]`, `failures: list[dict]`

### Task 2: Implement OAuth 2.0 auth (`src/cal_ai/calendar/auth.py`)
- `get_calendar_credentials(credentials_path, token_path) -> Credentials`
- Load cached token from `token.json` → if valid, return
- If expired, refresh via refresh token → save updated token
- If refresh fails or no token, launch `InstalledAppFlow.run_local_server()` → save token
- Missing `credentials.json` → raise `CalendarAuthError`
- Scopes: `["https://www.googleapis.com/auth/calendar"]`
- Log every auth step

### Task 3: Implement event mapper (`src/cal_ai/calendar/event_mapper.py`)
- `map_to_google_event(event: ExtractedEvent, timezone: str, owner_email: str) -> dict`
- Maps: summary, location, start/end (ISO 8601 + timezone), description (reasoning + assumptions), attendees
- `end_time` None → default `start_time + 1 hour`
- Owner name → `GOOGLE_ACCOUNT_EMAIL`; other attendees → display name in description
- Description includes LLM reasoning for demo observability

### Task 4: Implement Calendar CRUD client (`src/cal_ai/calendar/client.py`)
`GoogleCalendarClient` class (accepts `Credentials`, optional mock `service` for testing):

- **`create_event(event)`** — map → duplicate check → conflict check → insert → log
- **`list_events(time_min, time_max)`** — list with pagination → log count
- **`update_event(event_id, event)`** — map → update → log
- **`find_and_update_event(event)`** — search by title+time → update if found, warn if not
- **`delete_event(event_id)`** — delete → log
- **`find_and_delete_event(event)`** — search by title+time → delete if found, warn if not

### Task 5: Implement duplicate detection
- `_is_duplicate(event, existing_events) -> dict | None`
- Match: same title (case-insensitive) AND overlapping time
- Overlap: `event_a.start < event_b.end AND event_b.start < event_a.end`
- Same title + different time = NOT duplicate
- Different title + same time = NOT duplicate (that's a conflict)

### Task 6: Implement conflict detection
- `_find_conflicts(event, existing_events) -> list[dict]`
- Return all existing events with overlapping time (regardless of title)
- Caller logs warning but proceeds with creation

### Task 7: Implement error handling (`src/cal_ai/calendar/exceptions.py`)
Custom exceptions:
- `CalendarAuthError` — auth failures
- `CalendarAPIError` — base API error
- `CalendarRateLimitError` — 429 responses
- `CalendarNotFoundError` — 404 on update/delete

Retry logic via `@with_retry` decorator:
- HTTP 429 → exponential backoff, max 3 retries
- HTTP 401 → refresh token, retry once
- Network errors → backoff, max 3 retries
- HTTP 404 → raise CalendarNotFoundError (no retry)

### Task 8: Implement sync orchestrator
`sync_events(events: list[ExtractedEvent]) -> SyncResult`
- Dispatch by `event.action`: create/update/delete
- Continue on partial failures (one bad event doesn't kill the run)
- Return SyncResult with counts and details
- Log summary

### Task 9: Write unit tests
### Task 10: Write integration test documentation

---

## File Inventory

| File | Action | Description |
|---|---|---|
| `src/cal_ai/models.py` | CREATE | ExtractedEvent, SyncResult (shared with fn-3) |
| `src/cal_ai/calendar/__init__.py` | CREATE | Re-exports GoogleCalendarClient, get_calendar_credentials |
| `src/cal_ai/calendar/auth.py` | CREATE | OAuth 2.0 Desktop flow |
| `src/cal_ai/calendar/client.py` | CREATE | CRUD + duplicate/conflict + sync |
| `src/cal_ai/calendar/event_mapper.py` | CREATE | ExtractedEvent → Google Calendar dict |
| `src/cal_ai/calendar/exceptions.py` | CREATE | Custom exceptions + retry decorator |
| `tests/unit/calendar/__init__.py` | CREATE | Empty |
| `tests/unit/calendar/conftest.py` | CREATE | Mock credentials, service, sample events |
| `tests/unit/calendar/test_auth.py` | CREATE | Auth tests |
| `tests/unit/calendar/test_client.py` | CREATE | CRUD + detection + sync tests |
| `tests/unit/calendar/test_event_mapper.py` | CREATE | Event mapping tests |
| `tests/unit/calendar/test_exceptions.py` | CREATE | Error handling + retry tests |
| `tests/integration/test_calendar_integration.py` | CREATE | Manual integration docs |

---

## Required Tests

### `tests/unit/calendar/test_auth.py` (7 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_load_cached_token_valid` | token.json exists, token valid | Returns credentials, no browser flow |
| `test_expired_token_triggers_refresh` | Token expired, refresh token available | creds.refresh() called, token saved |
| `test_refresh_failure_triggers_reauth` | Refresh fails | Falls back to browser OAuth flow |
| `test_no_cached_token_launches_browser_flow` | No token.json | InstalledAppFlow launched |
| `test_missing_credentials_json_raises_error` | No credentials.json | Raises CalendarAuthError |
| `test_token_saved_after_successful_auth` | After any successful auth | token.json written |
| `test_correct_scopes_requested` | OAuth flow scopes | Scope is calendar |

### `tests/unit/calendar/test_event_mapper.py` (7 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_map_full_event` | All fields populated | Correct Google Calendar dict |
| `test_map_minimal_event_no_location_no_attendees` | Required fields only | No location/attendees in output |
| `test_map_event_default_end_time` | end_time=None | end = start + 1 hour |
| `test_map_event_with_attendees` | Attendees list | Owner mapped to email, others to display names |
| `test_map_event_description_includes_reasoning` | Reasoning + assumptions | Both in description field |
| `test_map_event_timezone_applied` | Configured timezone | start/end timeZone matches config |
| `test_map_event_iso_format` | Datetime serialization | ISO 8601 format |

### `tests/unit/calendar/test_client.py` (24 tests)

#### Create Operations (5 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_create_event_success` | Happy path create | insert() called, response returned, logged |
| `test_create_event_minimal_fields` | No location/attendees | insert() called without optional fields |
| `test_create_event_with_attendees` | Attendees in event | Attendees in API body |
| `test_create_event_skipped_when_duplicate` | Duplicate detected | insert() NOT called, logged |
| `test_create_event_with_conflict_warning` | Time conflict exists | insert() called, warning logged |

#### Read Operations (3 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_list_events_returns_results` | Events in range | Correct list returned |
| `test_list_events_empty_range` | No events | Empty list |
| `test_list_events_pagination` | nextPageToken present | Multiple pages fetched |

#### Update Operations (3 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_update_event_success` | Update by ID | update() called, response returned |
| `test_find_and_update_event_found` | Search + update | Matching event found and updated |
| `test_find_and_update_event_not_found` | No match | update() NOT called, warning logged, returns None |

#### Delete Operations (3 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_delete_event_success` | Delete by ID | delete() called |
| `test_find_and_delete_event_found` | Search + delete | Matching event found and deleted, returns True |
| `test_find_and_delete_event_not_found` | No match | delete() NOT called, warning logged, returns False |

#### Duplicate Detection (5 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_duplicate_detected_same_title_overlapping_time` | Same title + overlap | Returns existing event |
| `test_no_duplicate_same_title_different_time` | Same title, no overlap | Returns None |
| `test_no_duplicate_different_title_same_time` | Different title, same time | Returns None |
| `test_duplicate_detection_case_insensitive` | "Lunch" vs "lunch" | Detected as duplicate |
| `test_duplicate_detection_partial_overlap` | Same title, partial time overlap | Detected as duplicate |

#### Conflict Detection (4 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_conflict_detected_overlapping_time` | Different title, time overlap | Returns conflicting event |
| `test_no_conflict_adjacent_events` | Back-to-back (end=start) | No conflict |
| `test_no_conflict_non_overlapping` | Completely separate times | No conflict |
| `test_multiple_conflicts_detected` | Overlaps with 2+ events | All returned |

#### Sync Orchestration (5 tests — part of test_client.py or separate test_sync.py)

| Test | What It Tests | Expected |
|---|---|---|
| `test_sync_events_dispatches_create` | action="create" events | create_event called |
| `test_sync_events_dispatches_update` | action="update" events | find_and_update_event called |
| `test_sync_events_dispatches_delete` | action="delete" events | find_and_delete_event called |
| `test_sync_events_returns_summary` | Mixed actions | Correct SyncResult counts |
| `test_sync_events_continues_on_partial_failure` | One event fails | Others still processed |

### `tests/unit/calendar/test_exceptions.py` (9 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_api_rate_limit_429_retries` | HTTP 429 once, then success | Retries, succeeds on 2nd call |
| `test_api_rate_limit_429_max_retries_exceeded` | HTTP 429 four times | Raises CalendarRateLimitError |
| `test_api_auth_expired_401_triggers_refresh` | HTTP 401 once | Refreshes token, retries, succeeds |
| `test_api_auth_expired_401_refresh_fails` | HTTP 401, refresh fails | Raises CalendarAuthError |
| `test_network_timeout_retries` | Timeout once, then success | Retries, succeeds |
| `test_network_timeout_max_retries_exceeded` | Timeout four times | Raises CalendarAPIError |
| `test_event_not_found_404_on_delete` | HTTP 404 on delete | Raises CalendarNotFoundError |
| `test_event_not_found_404_on_update` | HTTP 404 on update | Raises CalendarNotFoundError |
| `test_invalid_event_data_raises_validation_error` | start_time > end_time | Raises ValueError, no API call |

**Total: 47 unit tests + 2 manual integration tests**

---

## Implementation Order
1. Task 1 (shared models) — can parallel with task 2, 3
2. Task 2 (auth) — independent
3. Task 3 (event mapper) — depends on task 1
4. Task 7 (exceptions + retry) — independent
5. Task 4 (client CRUD) — depends on 1, 2, 3, 7
6. Tasks 5, 6 (duplicate/conflict) — part of task 4
7. Task 8 (sync orchestrator) — depends on 4
8. Task 9 (unit tests) — TDD alongside each module
9. Task 10 (integration docs) — last

## Design Decisions
- **Service injection** in `GoogleCalendarClient.__init__` for testability (mock service in tests, real in prod)
- **`@with_retry` decorator** in exceptions.py keeps retry logic DRY and testable
- **`zoneinfo.ZoneInfo`** (stdlib Python 3.9+) for timezone handling
- **Attendee limitation**: LLM extracts names not emails; owner → email, others → display name in description
- **All times normalized to UTC** before duplicate/conflict comparison
