# fn-2: Transcript Parser

## Summary
Parse conversation transcripts with speaker labels into structured data suitable for LLM consumption. This is the input layer of the pipeline.

## Dependencies
- fn-1 (project structure, logging, test harness)

---

## Task Breakdown

### Task 1: Define data models (`src/cal_ai/models/transcript.py`)

Dataclasses (not Pydantic — minimal deps per SPEC §3.2):

- **`Utterance`** — a single speaker turn
  - `speaker: str` — name (stripped of brackets, trimmed)
  - `text: str` — dialogue text (may be multi-line joined with `\n`)
  - `line_number: int` — 1-based line number where utterance begins

- **`ParseWarning`** — a structured parse warning
  - `line_number: int`
  - `message: str`
  - `raw_line: str`

- **`TranscriptParseResult`** — top-level return type
  - `utterances: list[Utterance]`
  - `speakers: list[str]` — unique, ordered by first appearance
  - `warnings: list[ParseWarning]`
  - `source: str` — file path or `"<string>"`

### Task 2: Implement core parser (`src/cal_ai/parser.py`)

**Public API:**
- `parse_transcript(text: str, source: str = "<string>") -> TranscriptParseResult`
- `parse_transcript_file(file_path: str | Path) -> TranscriptParseResult`

**Parsing logic:**
1. Empty/whitespace-only → empty result, no warnings
2. Split by `\n`, iterate with 1-based line numbers
3. Regex: `^\[(.+?)\]:\s*(.*)$`
4. Match → new Utterance with speaker (trimmed), text, line_number
5. No match + current utterance exists → continuation line (append to current text)
6. No match + no current utterance → orphan line → ParseWarning
7. Blank lines → skip (not malformed)
8. Build speakers list via `dict.fromkeys` for ordered uniqueness

**`parse_transcript_file`:**
- Accept `str | Path`, validate exists, read UTF-8, delegate to `parse_transcript`

### Task 3: Add logging
- INFO on successful parse: utterance count, speaker count, speaker list
- WARNING per ParseWarning: line number, raw line, message
- INFO on empty input: "Empty transcript received"
- DEBUG on file read: "Reading transcript from {path}"
- Logger: `logging.getLogger(__name__)` → `cal_ai.parser`

### Task 4: Create test fixtures
- `tests/fixtures/sample_transcript.txt` — SPEC.md example (Alice/Bob lunch)
- `tests/fixtures/multiline_transcript.txt` — multi-line utterances
- `tests/fixtures/malformed_transcript.txt` — various malformed lines
- `tests/fixtures/empty_transcript.txt` — empty file
- `tests/fixtures/unicode_transcript.txt` — Unicode speakers and text

### Task 5: Write unit tests (`tests/unit/test_parser.py`, `tests/unit/test_models.py`)

### Task 6: Write integration tests (`tests/integration/test_parser_files.py`)

### Task 7: Wire up `__init__.py` exports

---

## File Inventory

| File | Action | Description |
|---|---|---|
| `src/cal_ai/models/__init__.py` | CREATE | Export transcript models |
| `src/cal_ai/models/transcript.py` | CREATE | Utterance, ParseWarning, TranscriptParseResult |
| `src/cal_ai/parser.py` | CREATE | parse_transcript(), parse_transcript_file() |
| `tests/unit/test_models.py` | CREATE | Model unit tests |
| `tests/unit/test_parser.py` | CREATE | Parser unit tests |
| `tests/integration/test_parser_files.py` | CREATE | File I/O tests |
| `tests/fixtures/sample_transcript.txt` | CREATE | SPEC example |
| `tests/fixtures/multiline_transcript.txt` | CREATE | Multi-line fixture |
| `tests/fixtures/malformed_transcript.txt` | CREATE | Malformed fixture |
| `tests/fixtures/empty_transcript.txt` | CREATE | Empty fixture |
| `tests/fixtures/unicode_transcript.txt` | CREATE | Unicode fixture |

---

## Required Tests

### `tests/unit/test_models.py` (6 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_utterance_creation` | Basic instantiation | All fields accessible |
| `test_utterance_equality` | Identical objects | Equal |
| `test_utterance_inequality` | Different objects | Not equal |
| `test_parse_warning_creation` | Basic instantiation | Fields set correctly |
| `test_transcript_parse_result_creation` | All fields | Accessible |
| `test_transcript_parse_result_empty` | Empty lists | Valid empty result |

### `tests/unit/test_parser.py` (40 tests)

#### Happy Path (6 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_parse_spec_example` | SPEC.md example transcript | 3 utterances (Alice/Bob/Alice), speakers=["Alice","Bob"], 0 warnings |
| `test_parse_single_utterance` | `"[Alice]: Hello"` | 1 utterance, speaker="Alice", text="Hello", line=1 |
| `test_parse_two_speakers` | Two different speakers | 2 utterances, correct fields |
| `test_speakers_list_ordered_by_first_appearance` | Alice, Bob, Alice again | speakers=["Alice","Bob"] |
| `test_source_default` | No explicit source | `result.source == "<string>"` |
| `test_source_custom` | source="my_file.txt" | `result.source == "my_file.txt"` |

#### Multi-line Utterances (4 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_multiline_continuation` | Speaker line + continuation lines | 1 utterance, text joined with `\n` |
| `test_multiline_then_new_speaker` | Alice multi-line, then Bob | 2 utterances, Alice has continuation text |
| `test_multiline_with_blank_lines_between` | Blank line mid-utterance | Blank skipped, continuation still attached |
| `test_multiline_indented_continuation` | Continuation with leading whitespace | Whitespace stripped |

#### Empty and Whitespace Input (3 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_parse_empty_string` | `""` | Empty result, no warnings |
| `test_parse_whitespace_only` | `"   \n  \n\t"` | Empty result, no warnings |
| `test_parse_only_blank_lines` | `"\n\n\n"` | Empty result, no warnings |

#### Malformed Input (7 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_malformed_missing_closing_bracket` | `"[Alice: Hello"` | 0 utterances, 1 warning |
| `test_malformed_missing_opening_bracket` | `"Alice]: Hello"` | 0 utterances, 1 warning |
| `test_malformed_no_colon` | `"[Alice] Hello"` | 0 utterances, 1 warning |
| `test_malformed_no_brackets_at_all` | `"Alice said hello"` | 0 utterances, 1 warning |
| `test_malformed_line_before_first_speaker` | Orphan text then `[Alice]: Hi` | 1 utterance, 1 warning |
| `test_malformed_line_between_speakers` | `[Alice]: Hi` then garbled then `[Bob]: Hey` | 2 utterances (garbled = continuation of Alice), 0 warnings |
| `test_entirely_malformed_input` | Multiple non-matching lines | 0 utterances, multiple warnings |

#### Speaker Label Edge Cases (8 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_speaker_with_no_text` | `"[Alice]:"` | speaker="Alice", text="" |
| `test_speaker_with_only_whitespace_text` | `"[Alice]:   "` | speaker="Alice", text="" |
| `test_speaker_name_with_spaces` | `"[Dr. Jane Smith]: Hello"` | speaker="Dr. Jane Smith" |
| `test_speaker_name_with_special_characters` | `"[O'Brien (host)]: Welcome"` | speaker="O'Brien (host)" |
| `test_speaker_name_with_numbers` | Speaker 1, Speaker 2 | Correct speakers list |
| `test_speaker_name_trimmed` | `"[ Alice ]: Hello"` | speaker="Alice" |
| `test_consecutive_same_speaker` | Alice twice in a row | 2 separate utterances, NOT merged |
| `test_many_speakers` | 5+ speakers | All in speakers list, first-appearance order |

#### Unicode (3 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_unicode_speaker_name` | `"[René]: Bonjour"` | speaker="René" |
| `test_unicode_dialogue_text` | Unicode in text | Preserved correctly |
| `test_cjk_characters` | Japanese speaker/text | Parsed correctly |

#### Colon/Bracket Edge Cases (4 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_colon_in_dialogue_text` | `"[Alice]: Time is 3:00 PM"` | text="Time is 3:00 PM" |
| `test_brackets_in_dialogue_text` | `"[Alice]: He said [wow]"` | text="He said [wow]" |
| `test_nested_brackets_in_speaker` | `"[[Editor]]: Note"` | Handled gracefully |
| `test_empty_brackets` | `"[]: Hello"` | 0 utterances, 1 warning |

#### Large Input (2 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_very_long_line` | 10,000+ char text | Parses, text preserved |
| `test_many_utterances` | 1,000 generated utterances | 1,000 returned, correct line numbers, < 1 second |

#### Logging (3 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_logging_on_successful_parse` | Parse SPEC example, check caplog | INFO with utterance/speaker counts |
| `test_logging_on_warning` | Parse malformed line | WARNING with line number and raw line |
| `test_logging_on_empty_input` | Parse empty string | INFO "Empty transcript" message |

### `tests/integration/test_parser_files.py` (7 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_parse_spec_example_file` | sample_transcript.txt | Same as test_parse_spec_example, source=file path |
| `test_parse_multiline_file` | multiline_transcript.txt | Multi-line utterances correct |
| `test_parse_malformed_file` | malformed_transcript.txt | Warnings for bad lines, valid lines parsed |
| `test_parse_empty_file` | empty_transcript.txt | Empty result |
| `test_parse_unicode_file` | unicode_transcript.txt | Unicode preserved |
| `test_parse_nonexistent_file` | "does/not/exist.txt" | Raises FileNotFoundError |
| `test_parse_file_source_field` | Any fixture file | result.source == file path string |

**Total: 53 tests** (6 model + 40 parser unit + 7 file integration)

---

## Implementation Order
1. Task 1 — data models
2. Model tests (M1-M6) — verify models
3. Task 2 — core parser logic
4. Task 4 — fixture files
5. Task 5 — parser unit tests (P1-P40)
6. Task 3 — add logging
7. Task 6 — integration tests (F1-F7)
8. Task 7 — exports
9. Final: `ruff check .` and `ruff format --check .` clean

## Design Decisions
- **Dataclasses over Pydantic** — stdlib, zero-dep, sufficient for simple containers. Migrate later if fn-3 needs Pydantic.
- **No merging of consecutive same-speaker utterances** — parser is structural, merging is semantic (fn-3's job).
- **Non-matching lines = continuation when current utterance exists** — most natural for real transcripts with soft-wrapped text. Only orphan lines (before any speaker) generate warnings.
- **Regex `^\[(.+?)\]:\s*(.*)$`** — non-greedy speaker capture, permissive about speaker name contents, colon required.
