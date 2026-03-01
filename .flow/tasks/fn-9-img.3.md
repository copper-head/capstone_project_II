# fn-9-img.3 Memory Write Path (Fact Extraction + Action Decision)

## Description

Implement the memory write path: after calendar sync, run two LLM calls — (1) extract candidate facts from the transcript and extracted events, (2) compare candidates against existing memories and decide ADD/UPDATE/DELETE/NOOP actions — then dispatch actions via `MemoryStore.upsert()`/`delete()` and log them. Print a concise console summary after completion.

**Size:** M
**Files:**
- `src/cal_ai/memory/extraction.py` (new) — fact extraction + action decision LLM orchestration
- `src/cal_ai/memory/prompts.py` (new) — prompt builders for both LLM calls
- `src/cal_ai/pipeline.py` (modify) — add memory write stage after sync, add memory stats to PipelineResult
- `tests/unit/test_memory_extraction.py` (new) — unit tests with mocked LLM responses
- `tests/unit/test_pipeline.py` (modify) — update mocks for write-path stage

## Approach

- **Fact extraction call**: Send transcript + extracted events + owner name to Gemini. Prompt instructs LLM to identify facts across 5 categories (preferences, people, vocabulary, patterns, corrections) using **third-person framing with owner name** (e.g., "Bob is Alice's manager", not "Bob is my manager"). Output: `{"facts": [...]}`. Include 2-3 negative few-shot examples (trivial conversations → empty facts array) to prevent hallucinated memories. Conservative sarcasm/hypothetical guard: only extract facts stated clearly and directly.
- **Owner-centric people extraction**: The extraction prompt must instruct the LLM to remember how other people relate to the **owner** — roles, meeting patterns, scheduling preferences. Inter-person relationships (e.g., "Bob and Carol are on the same team") are NOT extracted unless they directly affect the owner's scheduling.
- **Name collision disambiguation**: The extraction prompt must instruct the LLM to append disambiguating context to keys when the owner knows multiple people with the same name (e.g., "Bob (manager)" vs "Bob (dentist)").
- **Vocabulary includes title preferences**: The vocabulary category captures the owner's preferred event titles (e.g., "wellness hour" = therapy appointment), not just temporal concepts.
- **Action decision call**: Send candidate facts + existing memories (with integer-remapped IDs) + owner name to Gemini. The action decision prompt also receives owner name to maintain third-person framing consistency when generating updated values (e.g., "Bob was Alice's former manager"). Prompt instructs LLM to choose ADD/UPDATE/DELETE/NOOP for each fact. Include few-shot examples for all 4 action types, especially UPDATE (merge vs replace) and NOOP (already known).
- **Action reasoning required**: The action decision output schema includes a required `reasoning` field explaining why each action was chosen (supports demo requirement for observable AI reasoning).
- **Confidence adjustable**: The extraction LLM proposes initial confidence, but the action decision LLM sets the final confidence stored in the DB. It has more context (existing memories) and can upgrade/downgrade confidence based on corroboration or contradiction.
- **Category immutable on UPDATE**: The action decision LLM cannot reclassify a memory's category. To change category, it must DELETE the old entry and ADD a new one. The action decision prompt must enforce this constraint.
- **Temporal UPDATE for past-tense references**: When the owner says "Bob used to be my manager", the system should UPDATE the memory to "Bob was Alice's former manager" rather than DELETE. The prompt must instruct this behavior to preserve relationship history.
- **Integer ID remapping**: Same pattern as calendar context in `src/cal_ai/calendar/context.py`. Map DB autoincrement IDs to sequential integers starting at 1, pass to LLM, map back when dispatching actions.
- **Action dispatch**: Loop through actions. ADD and UPDATE both dispatch to `MemoryStore.upsert(category, key, value, confidence)`. DELETE dispatches to `MemoryStore.delete(memory_id)`. Log each action via `MemoryStore.log_action()` with category/key snapshots. Handle edge cases: UPDATE/DELETE referencing nonexistent ID → log warning, skip.
- **Console summary**: After write path completes, print a concise one-line summary (e.g., "Memory: +2 added, 1 updated, 0 deleted"). Matches the style of sync result logging.
- **Pipeline integration**: Add Stage 5 after the sync loop (or after extraction when no events are synced). The write path runs **even when zero events are extracted** — conversations with no scheduling content can still contain memory-worthy facts (preferences, people, vocabulary). Pass `extracted_events=[]` in this case. When `dry_run=True`, skip the write path entirely (no LLM calls, no SQLite writes) to match existing dry-run semantics of no external side effects. Remove or bypass the early-return path in pipeline so memory write is reached. Wrap in try/except for graceful degradation. Add to `PipelineResult`: `memories_added: int`, `memories_updated: int`, `memories_deleted: int`, and `memory_usage_metadata: list` (token usage from both memory LLM calls, same type as `ExtractionResult.usage_metadata`).
- **Reuse `GeminiClient._call_api()`** for both LLM calls — same pattern as `benchmark/summary.py:179`. Create `GenerateContentConfig` with `system_instruction`, `response_mime_type="application/json"`, and `response_schema` (Pydantic model).
- **Token tracking**: Both LLM calls return `LLMCallResult` with usage metadata. Store in `PipelineResult.memory_usage_metadata` list so benchmark/reporting can consume them separately from extraction tokens.
- **Update pipeline unit tests**: Add mocks for the write-path stage in `tests/unit/test_pipeline.py`.

## Key context

- Mem0's prompt structure is the reference: `FACT_RETRIEVAL_PROMPT` for extraction, `DEFAULT_UPDATE_MEMORY_PROMPT` for action decision — see `github.com/mem0ai/mem0/blob/main/mem0/configs/prompts.py`
- Extraction prompt must emphasize: extract from speaker content only, not system framing. Include DO NOT extract criteria (greetings, generic questions).
- Action decision prompt must show examples of supplementary vs contradictory vs redundant facts
- Both ADD and UPDATE actions use the same `upsert()` method — the ON CONFLICT handles deduplication
- Gemini alphabetically sorts response_schema keys — ensure field names produce logical alphabetical ordering
- `_call_api()` is currently a private method on `GeminiClient`. The benchmark summary module already calls it directly (line ~179). Consider adding a public `call_api()` method or passing the client to memory extraction functions.
- `PipelineResult` is currently a mutable class at `pipeline.py:74` — adding fields is straightforward

## Acceptance
- [ ] Fact extraction LLM call: takes transcript text + extracted events + owner name, returns candidate facts with category/key/value/confidence via Pydantic structured output
- [ ] Fact extraction uses third-person framing with owner name (e.g., "Bob is Alice's manager")
- [ ] Fact extraction prompt includes 2-3 negative few-shot examples (trivial input → empty facts; sarcasm → skip)
- [ ] Fact extraction enforces owner-centric people relationships (only how others relate to owner)
- [ ] Fact extraction instructs name collision disambiguation (e.g., "Bob (manager)" vs "Bob (dentist)")
- [ ] Fact extraction includes vocabulary title preferences (e.g., "wellness hour" = therapy appointment)
- [ ] Action decision LLM call: takes candidate facts + existing memories (integer-remapped IDs) + owner name, returns ADD/UPDATE/DELETE/NOOP actions via Pydantic structured output
- [ ] Action decision prompt uses owner name for third-person framing consistency in generated values
- [ ] Action decision output includes required `reasoning` field for each action
- [ ] Action decision sets final `confidence` (may differ from extraction's proposal)
- [ ] Action decision enforces category immutability on UPDATE (reclassify via DELETE + ADD)
- [ ] Action decision prompt instructs temporal UPDATE for past-tense references (e.g., "used to be" → UPDATE with "was former", not DELETE)
- [ ] Action decision prompt includes few-shot examples for all 4 action types
- [ ] Integer ID remapping: DB IDs mapped to sequential integers for LLM, mapped back for dispatch
- [ ] ADD and UPDATE actions both dispatch to `MemoryStore.upsert(category, key, value, confidence)`
- [ ] DELETE actions dispatch to `MemoryStore.delete(memory_id)`
- [ ] All actions logged to `memory_log` via `log_action()` with category/key snapshots, old/new values, and transcript filename
- [ ] Invalid action targets (UPDATE/DELETE nonexistent ID) logged as warnings, skipped gracefully
- [ ] Console prints concise one-line memory summary after write path (e.g., "Memory: +2 added, 1 updated, 0 deleted")
- [ ] Pipeline Stage 5: memory write runs after sync (or after extraction when no events), wrapped in try/except for graceful degradation
- [ ] Write path runs even when zero events are extracted (receives `extracted_events=[]`)
- [ ] Write path is skipped entirely when `dry_run=True` (no LLM calls, no SQLite writes)
- [ ] `PipelineResult` includes `memories_added`, `memories_updated`, `memories_deleted` counts
- [ ] `PipelineResult` includes `memory_usage_metadata: list` for token tracking from both memory LLM calls
- [ ] Existing pipeline unit tests updated to mock write-path memory stage
- [ ] Unit tests with mocked LLM responses cover: facts extraction, action decision, action dispatch (upsert/delete), error handling
- [ ] `make test` and `make lint` pass

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
