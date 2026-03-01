# fn-9-img.2 Memory Read Path (Load, Format, Inject)

## Description

Implement the memory read path: load memories from SQLite, format them by category with owner name in header, inject as a `## Your Memory (about {owner_name})` section into the extraction system prompt, and thread `memory_context` through the pipeline.

**Size:** M
**Files:**
- `src/cal_ai/memory/formatter.py` (new) — format memories for prompt injection
- `src/cal_ai/prompts.py` (modify) — add `memory_context` parameter to `build_system_prompt()`
- `src/cal_ai/llm.py` (modify) — add `memory_context` parameter to `extract_events()`
- `src/cal_ai/pipeline.py` (modify) — add memory load stage before calendar context fetch
- `tests/unit/test_memory_formatter.py` (new) — formatter unit tests
- `tests/unit/test_pipeline.py` (modify) — update existing pipeline mocks for memory stage
- `tests/unit/test_prompts.py` (modify) — add byte-for-byte identity test

## Approach

- Follow the `CalendarContext` pattern at `src/cal_ai/calendar/context.py` — create analogous `MemoryContext` dataclass with `memory_text: str` field
- `format_memory_context(memories, owner_name)` accepts any sequence of objects with `category`, `key`, and `value` attributes (duck-typed). This allows both `MemoryRecord` (from store) and `SidecarMemoryEntry` (from tests) to be formatted without conversion. Groups memories by category with bullet points, matching the format in `docs/memory_system_design.tex` Section 2.1
- **Header ownership**: The formatter is the single source of truth for the memory section. `format_memory_context()` returns the **complete section** including the `## Your Memory (about {owner_name})` header and categorized bullet points. `build_system_prompt()` simply appends the raw `memory_context` string — it does NOT add any header or wrapper.
- When `memories` is empty, return `""` — this ensures no `## Your Memory` section is emitted
- Add `memory_context: str = ""` to `build_system_prompt()` at `prompts.py:14` — append raw `memory_context` string **before** `## Your Calendar` section (both near end of prompt, line ~446). The formatter already includes the header, so `build_system_prompt()` only needs `if memory_context:` guard and appends it as-is.
- **Byte-for-byte backward compatibility**: When `memory_context=""`, `build_system_prompt()` output must be identical to current behavior. Add an explicit test for this.
- Add `memory_context: str = ""` to `extract_events()` at `llm.py:74` — pass through to `build_system_prompt()`
- In `pipeline.py`, add memory load **before** calendar context fetch (matching epic diagram order: Load Memories → Fetch Calendar Context → Extract Events):
  - Instantiate `MemoryStore(settings.memory_db_path)`
  - Call `store.load_all()` → `format_memory_context(memories, settings.owner_name)` → pass to `extract_events()`
  - Wrap in try/except: on failure, log warning, continue with empty memory (graceful degradation, same pattern as calendar context at line ~201-204)
- **Update existing pipeline unit tests** (`tests/unit/test_pipeline.py`): Add `memory_db_path` to mocked `Settings`, mock `MemoryStore` instantiation and `load_all()` to prevent SQLite file creation during unit tests

## Key context

- `build_system_prompt()` currently has 3 params: `owner_name`, `current_datetime`, `calendar_context` — all with defaults except first two
- Calendar context is appended at line ~446 with `if calendar_context:` guard — memory follows the same pattern
- `extract_events()` has two callers: `pipeline.py` (line ~217) and `benchmark/runner.py` (line ~286). Both signatures must stay backward-compatible via default `memory_context=""`
- The prompt's "lost in the middle" mitigation places context sections at the end — memory before calendar preserves calendar's recency advantage
- Existing pipeline unit tests use `MagicMock` for settings — these must be updated to include `memory_db_path` attribute
- Epic diagram shows stage order: Load Memories → Fetch Calendar Context → Extract Events

## Acceptance
- [ ] `format_memory_context()` accepts objects with `category`/`key`/`value` attributes (duck-typed — works with `MemoryRecord` and `SidecarMemoryEntry`) and `owner_name` parameter
- [ ] `format_memory_context()` produces categorized text with `## Your Memory (about {owner_name})` header and category subheadings with bullet points
- [ ] `format_memory_context([])` returns `""` (empty string, not "No memories")
- [ ] `build_system_prompt()` accepts `memory_context: str = ""` and appends it raw (no header wrapping) before `## Your Calendar`
- [ ] `build_system_prompt()` with empty `memory_context` produces byte-for-byte identical output to current behavior (explicit test in `test_prompts.py`)
- [ ] `extract_events()` accepts `memory_context: str = ""` and threads it to `build_system_prompt()`
- [ ] Pipeline loads memories from SQLite before calendar context fetch (matching epic diagram)
- [ ] Pipeline passes `settings.owner_name` to `format_memory_context()` for owner-contextualized header
- [ ] Pipeline gracefully degrades on memory load failure (logs warning, continues with empty memory)
- [ ] Existing pipeline unit tests (`tests/unit/test_pipeline.py`) updated to mock MemoryStore and include `memory_db_path` on mocked settings
- [ ] All existing regression tests pass in mock mode with no sidecar changes
- [ ] `make test` and `make lint` pass

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
