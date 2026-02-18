# fn-3: LLM Event Extraction

## Summary
Integrate Gemini Flash 3 to extract calendar events from parsed transcripts. The LLM receives structured conversation data and returns structured JSON event data. This is the core AI component.

## Dependencies
- fn-1 (config, logging)
- fn-2 (parsed transcript data structure)

---

## Task Breakdown

### Task 1: Add `google-genai` Dependency
Update `pyproject.toml` to add `google-genai>=1.0.0`. Run `pip install -e .` to verify.

### Task 2: Define Pydantic Models (`src/cal_ai/models.py`)

**`ExtractedEvent`** — a single event extracted by the LLM:
- `title: str`, `start_time: str` (ISO 8601), `end_time: str | None`
- `location: str | None`, `attendees: list[str]`
- `confidence: Literal["high", "medium", "low"]`
- `reasoning: str`, `assumptions: list[str]`
- `action: Literal["create", "update", "delete"]`

**`ExtractionResult`** — full LLM response wrapper:
- `events: list[ExtractedEvent]`
- `summary: str`

**`ValidatedEvent`** — post-validation with parsed datetimes:
- Same fields but `start_time: datetime`, `end_time: datetime` (1-hour default applied)

**`LLMResponseSchema`** — simplified schema for Gemini's `response_schema` parameter. All fields required strings (`"none"` sentinel for optional fields) to avoid SDK `Optional` type limitations.

### Task 3: Build the System Prompt (`src/cal_ai/prompts.py`)

- `build_system_prompt(owner_name: str, current_datetime: str) -> str`
  - Owner perspective: "You are extracting calendar events for {owner_name}"
  - Current date/time injection for relative time resolution
  - Owner perspective filtering rules (high confidence for direct participation, low for overheard)
  - Ambiguity handling: "still extract with assumptions noted"
  - Relative time resolution: "Resolve 'next Thursday', 'tomorrow' to absolute dates"
  - JSON output format instructions
  - Field-level instructions (confidence levels, `"none"` for missing optional fields)
  - Empty results: "return empty events array with summary explaining why"

- `build_user_prompt(transcript_text: str) -> str`
  - Wraps transcript: "Extract calendar events from the following conversation:\n\n{text}"

- `format_transcript_for_llm(utterances: list[Utterance]) -> str`
  - Converts parsed utterances back to clean text for the LLM prompt

### Task 4: Build the Gemini Client (`src/cal_ai/llm.py`)

**`GeminiClient` class:**
- `__init__(self, api_key: str, model: str = "gemini-3-flash-preview")`
  - Creates `genai.Client(api_key=api_key)`, stores model name

- `extract_events(self, transcript_text: str, owner_name: str, current_datetime: datetime) -> ExtractionResult`
  - Builds system + user prompts
  - Calls `self.client.models.generate_content()` with `response_mime_type="application/json"` and `response_schema=LLMResponseSchema`
  - Parses response via `_parse_response()`
  - On parse failure: retry ONCE with same call
  - On second failure: return graceful failure (empty events, error summary)
  - Logs all reasoning at every step

- `_parse_response(self, raw_text: str) -> ExtractionResult`
  - `json.loads()` → Pydantic validation → convert `"none"` to `None`
  - Raises `MalformedResponseError` on failure

- `_validate_events(self, result: ExtractionResult, current_datetime: datetime) -> list[ValidatedEvent]`
  - Parse ISO 8601 strings → `datetime` objects
  - Apply 1-hour default for missing `end_time`
  - Validate confidence values

### Task 5: Custom Exceptions (`src/cal_ai/exceptions.py`)
- `MalformedResponseError(Exception)` — JSON parse or schema validation failure
- `ExtractionError(Exception)` — unrecoverable extraction failures

### Task 6: Wire Up Logging
In `llm.py`:
- System prompt sent → DEBUG
- User prompt / transcript → DEBUG
- Raw LLM response → DEBUG
- Each extracted event with reasoning → INFO (demo-visible)
- Retry attempts and why → WARNING
- Parse failures with raw response → ERROR
- Final extraction summary → INFO

### Task 7: Write All Unit Tests

### Task 8: Manual Smoke Test Documentation

---

## File Inventory

| File | Action | Description |
|---|---|---|
| `src/cal_ai/models.py` | CREATE/MODIFY | ExtractedEvent, ExtractionResult, ValidatedEvent, LLMResponseSchema |
| `src/cal_ai/prompts.py` | CREATE | System prompt builder, user prompt builder, transcript formatter |
| `src/cal_ai/llm.py` | CREATE | GeminiClient with extract_events(), parse/validate, retry |
| `src/cal_ai/exceptions.py` | CREATE/MODIFY | MalformedResponseError, ExtractionError |
| `tests/unit/test_models_extraction.py` | CREATE | Pydantic model validation tests |
| `tests/unit/test_prompts.py` | CREATE | Prompt construction tests |
| `tests/unit/test_llm.py` | CREATE | GeminiClient tests with mocked Gemini SDK |
| `pyproject.toml` | MODIFY | Add google-genai dependency |

---

## Required Tests

All tests use mocks — no real Gemini API calls.

### `tests/unit/test_models_extraction.py` (12 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_extracted_event_valid_complete` | All fields with valid values | Model instantiates, all fields accessible |
| `test_extracted_event_valid_minimal` | end_time=None, location=None, empty assumptions | Optional fields are None |
| `test_extracted_event_invalid_confidence` | confidence="maybe" | Pydantic ValidationError |
| `test_extracted_event_missing_required_title` | No title field | ValidationError |
| `test_extracted_event_missing_required_start_time` | No start_time field | ValidationError |
| `test_extracted_event_missing_required_reasoning` | No reasoning field | ValidationError |
| `test_extraction_result_with_events` | List of valid ExtractedEvents | events list has correct length |
| `test_extraction_result_empty_events` | events=[], summary present | Empty list, valid model |
| `test_validated_event_default_end_time` | end_time=None | end_time = start_time + 1 hour |
| `test_validated_event_explicit_end_time` | end_time provided | Matches provided value |
| `test_validated_event_iso_datetime_parsing` | "2026-02-19T12:00:00" | Correct datetime object |
| `test_validated_event_invalid_datetime_string` | "next Thursday" | Raises ValueError |

### `tests/unit/test_prompts.py` (8 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_build_system_prompt_contains_owner_name` | Owner name in prompt | "Alice" appears in prompt |
| `test_build_system_prompt_contains_current_datetime` | Date/time in prompt | "2026-02-18" appears in prompt |
| `test_build_system_prompt_contains_perspective_instructions` | Owner perspective rules | Contains "perspective" and "owner" |
| `test_build_system_prompt_contains_ambiguity_instructions` | Ambiguity handling | Contains assumptions/incomplete info instructions |
| `test_build_system_prompt_contains_relative_time_instructions` | Relative time resolution | References resolving relative dates |
| `test_build_system_prompt_contains_json_format_instructions` | JSON output structure | Mentions field names: title, start_time, etc. |
| `test_build_user_prompt_contains_transcript` | Transcript in user prompt | Full transcript text in returned string |
| `test_format_transcript_for_llm` | Parsed utterances → clean text | Clean "Speaker: text" format |

### `tests/unit/test_llm.py` (23 tests)

#### Happy Path (3 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_extract_single_event_happy_path` | SPEC.md example → 1 lunch event | 1 event, correct title/time/location/attendees |
| `test_extract_multiple_events` | Conversation with 2 events | 2 events, distinct titles and times |
| `test_extract_no_events` | Small talk, no events | 0 events, non-empty summary |

#### Ambiguous Events (2 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_extract_ambiguous_event_no_time` | "meet up sometime this week" | 1 event, confidence="low", non-empty assumptions |
| `test_extract_ambiguous_event_no_location` | Time but no location | location=None, assumptions note missing location |

#### Owner Perspective (2 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_owner_perspective_owner_involved` | Owner directly participates | confidence="high", owner in attendees |
| `test_owner_perspective_overheard_conversation` | Owner overhears others' meeting | confidence="low", reasoning explains overheard |

#### Relative Time Resolution (3 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_relative_time_next_thursday` | "next Thursday" from 2026-02-18 | start_time contains "2026-02-26" |
| `test_relative_time_tomorrow` | "tomorrow" from 2026-02-18 | start_time contains "2026-02-19" |
| `test_relative_time_this_weekend` | "this weekend" | start_time is a weekend day |

#### Malformed Response Handling (4 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_malformed_json_retry_success` | 1st call invalid JSON, 2nd valid | Succeeds on retry, WARNING logged, generate_content called 2x |
| `test_malformed_json_retry_still_bad_graceful_failure` | Both calls invalid JSON | 0 events, error summary, ERROR logged, called 2x |
| `test_llm_returns_empty_response` | Empty string response | Treated as malformed, retry triggered |
| `test_llm_returns_events_missing_required_fields` | Valid JSON, missing title | Schema validation fails, retry triggered |

#### Confidence Levels (3 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_confidence_levels_explicit_plan_is_high` | Clear plan with details | confidence="high" |
| `test_confidence_levels_vague_mention_is_low` | "maybe we could meet" | confidence="low" |
| `test_confidence_levels_medium_partial_info` | Day but no time | confidence="medium" |

#### Logging (3 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_reasoning_is_logged` | Event reasoning → console | INFO log contains reasoning string |
| `test_extraction_summary_is_logged` | Summary → console | Log contains summary string |
| `test_raw_llm_response_is_logged_at_debug` | Raw response logged | DEBUG log contains raw JSON |

#### API Integration (3 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_system_prompt_sent_to_gemini` | System prompt in API call | config includes system_instruction with owner + datetime |
| `test_response_schema_sent_to_gemini` | Schema in API call | config includes response_mime_type and response_schema |
| `test_extract_events_called_with_correct_model` | Model name used | generate_content called with "gemini-3-flash-preview" |

#### Edge Cases (3 tests — part of test_llm.py)

| Test | What It Tests | Expected |
|---|---|---|
| `test_api_error_handling` | Gemini API raises APIError | ExtractionError raised or graceful failure, error logged |
| `test_none_string_conversion` | "none" → None for end_time/location | Parsed event has None values |
| `test_end_time_default_one_hour` | end_time=None → start + 1hr | ValidatedEvent.end_time correct |

**Total: 43 unit tests**

---

## Implementation Order
1. Task 1 (dependency) — immediate
2. Task 5 (exceptions) — no deps, small
3. Task 2 (models) → run test_models_extraction.py
4. Task 3 (prompts) → run test_prompts.py
5. Task 7 (transcript formatter) — small, in prompts.py
6. Task 4 (GeminiClient) + Task 6 (logging) → run test_llm.py
7. Task 8 (smoke test docs) — last

## Design Decisions
- **Two-tier schema**: `LLMResponseSchema` (all-required, `"none"` sentinels) for Gemini API, `ExtractedEvent`/`ValidatedEvent` for internal use. Works around SDK `Optional` type limitations.
- **Retry exactly once**: On malformed JSON or schema failure, retry same call once. Second failure → graceful result (empty events, error summary). Never crash the pipeline.
- **String datetimes from LLM, parsed internally**: LLM outputs ISO 8601 strings. `_validate_events()` parses to `datetime` in `ValidatedEvent`.
- **Owner perspective is prompt-engineered**: System prompt instructs LLM to set confidence based on owner involvement. No post-filtering in Python.
- **Logging is first-class**: Reasoning at INFO (demo-visible), raw responses at DEBUG, errors at WARNING/ERROR.
- **Model string**: `gemini-3-flash-preview` (configurable default).
