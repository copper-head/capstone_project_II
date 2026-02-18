# fn-5: Pipeline Orchestration & Demo

## Summary
Wire all components together into the end-to-end pipeline. Accept a transcript file, parse it, extract events via LLM, sync to Google Calendar, and produce the demo output (structured logs showing the full reasoning chain).

## Dependencies
- fn-1 (project structure, config, logging)
- fn-2 (transcript parser)
- fn-3 (LLM event extraction)
- fn-4 (Google Calendar client)

---

## Task Breakdown

### Task 1: Create CLI Entrypoint (`src/cal_ai/__main__.py`)
- `argparse` (stdlib, no extra deps)
- Positional argument: `transcript_file` (path to .txt file)
- Optional `--dry-run` flag (parse and extract but skip calendar sync)
- Optional `--verbose` / `-v` flag for debug-level logging
- Optional `--owner` override (defaults to `OWNER_NAME` from config)
- Validate file exists before entering pipeline
- On error: clear message to stderr, exit code 1
- On success: call pipeline orchestrator, exit code 0

### Task 2: Create Pipeline Orchestrator (`src/cal_ai/pipeline.py`)

**`run_pipeline(transcript_path: Path, owner: str, dry_run: bool = False) -> PipelineResult`**

**`PipelineResult` dataclass:**
- `transcript_path: Path`, `speakers_found: list[str]`, `utterance_count: int`
- `events_extracted: list[ExtractedEvent]`
- `events_synced: list[SyncResult]`, `events_failed: list[FailedEvent]`
- `warnings: list[str]`, `duration_seconds: float`

**`SyncResult` dataclass:**
- `event: ExtractedEvent`, `action_taken: str` (created/updated/deleted/skipped_duplicate)
- `calendar_event_id: str | None`, `success: bool`, `error: str | None`

**Pipeline stages:**
1. **Stage 1 — Load & Parse**: Read transcript, call parser, log speakers and utterance count. File unreadable → raise and exit.
2. **Stage 2 — Extract Events**: Call LLM extractor. If LLM fails → log error, return empty result (zero events).
3. **Stage 3 — Sync to Calendar**: For each event, dispatch by action (create/update/delete). Each event wrapped in try/except. One failure does not kill the rest.
4. **Stage 4 — Summary**: Compute and return `PipelineResult`.

**Error handling:**
- File not found / unreadable: hard failure, clear error, exit
- Parse warnings (malformed lines): logged, pipeline continues
- LLM extraction failure: logged, pipeline exits cleanly with zero events
- Individual event sync failure: logged, pipeline continues with remaining events

### Task 3: Create Demo Output Formatter (`src/cal_ai/demo_output.py`)
Renders `PipelineResult` as structured console output:

```
============================================================
  CONVERSATION-TO-CALENDAR AI
============================================================

--- STAGE 1: Transcript Loaded ---
  File: samples/simple_lunch.txt
  Speakers: Alice, Bob
  Utterances: 3 lines

--- STAGE 2: Events Extracted ---
  Found 1 event(s)

  Event 1: Lunch with Bob
    When: Thursday 2026-02-19, 12:00 PM - 1:00 PM
    Where: New place on 5th
    Who: Alice, Bob
    Confidence: high
    AI Reasoning: Alice explicitly proposes lunch on Thursday
      at noon and Bob confirms. Location is mentioned.
    Assumptions: Duration assumed to be 1 hour (not specified)

--- STAGE 3: Calendar Operations ---
  [CREATE] "Lunch with Bob" -> Created (ID: abc123)

--- SUMMARY ---
  Events extracted: 1
  Successfully synced: 1
  Failed: 0
  Warnings: 0
  Pipeline duration: 2.3s
============================================================
```

- Dry-run: `[DRY RUN] Would create "Lunch with Bob"`
- Zero events: "No calendar events detected in this conversation."
- Failures: error message inline under failed event

### Task 4: Create Sample Transcript Files (`samples/`)
1. **`samples/simple_lunch.txt`** — Single event, clear details (Alice + Bob, lunch Thursday at noon)
2. **`samples/multiple_events.txt`** — 3 events (standup, code review, lunch)
3. **`samples/cancellation.txt`** — Meeting cancellation (action: delete)
4. **`samples/ambiguous_time.txt`** — Vague time references ("sometime next week")
5. **`samples/no_events.txt`** — Casual conversation, no calendar items
6. **`samples/complex.txt`** — 4 speakers, mixed content, some relevant to owner, some not

### Task 5: Wire Docker Entrypoint
- `Dockerfile`: `ENTRYPOINT ["python", "-m", "cal_ai"]`, `CMD ["samples/simple_lunch.txt"]`
- `docker-compose.yml`: Mount `samples/`, `.env`, `credentials.json`, `token.json`

### Tasks 6-10: Write All Tests

---

## File Inventory

| File | Action | Description |
|---|---|---|
| `src/cal_ai/__main__.py` | MODIFY | CLI entrypoint (replace stub from fn-1) |
| `src/cal_ai/pipeline.py` | CREATE | Pipeline orchestrator |
| `src/cal_ai/demo_output.py` | CREATE | Demo console output formatter |
| `samples/simple_lunch.txt` | CREATE | Single event sample |
| `samples/multiple_events.txt` | CREATE | Multiple events sample |
| `samples/cancellation.txt` | CREATE | Cancellation sample |
| `samples/ambiguous_time.txt` | CREATE | Ambiguous time sample |
| `samples/no_events.txt` | CREATE | No events sample |
| `samples/complex.txt` | CREATE | Complex multi-speaker sample |
| `tests/unit/test_cli.py` | CREATE | CLI entrypoint tests |
| `tests/unit/test_pipeline.py` | CREATE | Pipeline orchestrator tests |
| `tests/unit/test_demo_output.py` | CREATE | Demo output formatter tests |
| `tests/unit/test_sample_transcripts.py` | CREATE | Sample file validation tests |
| `tests/integration/test_end_to_end.py` | CREATE | E2E tests with mocked services |
| `tests/integration/test_docker.py` | CREATE | Docker config validation tests |
| `Dockerfile` | MODIFY | Add ENTRYPOINT/CMD, copy samples/ |
| `docker-compose.yml` | MODIFY | Add volume mounts |

---

## Required Tests

### `tests/unit/test_cli.py` (7 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_cli_valid_file_runs_pipeline` | Valid file → pipeline invoked | Exit 0, run_pipeline called with correct path |
| `test_cli_missing_file_argument_shows_usage` | No args | Exit 2, stderr contains "usage:" |
| `test_cli_nonexistent_file_shows_error` | Bad path | Exit 1, stderr contains "File not found" |
| `test_cli_dry_run_flag_passes_to_pipeline` | --dry-run | run_pipeline called with dry_run=True |
| `test_cli_verbose_flag_sets_debug_logging` | -v | Logger level set to DEBUG |
| `test_cli_owner_override` | --owner "Bob" | run_pipeline called with owner="Bob" |
| `test_cli_unreadable_file_shows_error` | No read permissions | Exit 1, stderr contains permission error |

### `tests/unit/test_pipeline.py` (14 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_pipeline_full_flow_success` | Happy path: parse→extract→sync all succeed | Correct counts in PipelineResult |
| `test_pipeline_parse_returns_empty` | Parser returns 0 utterances | utterance_count=0, events_extracted empty |
| `test_pipeline_extraction_returns_no_events` | Parser succeeds, LLM finds nothing | events_extracted empty, no calendar calls |
| `test_pipeline_extraction_failure_does_not_crash` | LLM raises RuntimeError | Pipeline returns 0 events, warning logged |
| `test_pipeline_single_event_sync_failure_continues` | 1 of 3 events fails sync | 2 synced, 1 failed |
| `test_pipeline_all_events_sync_failure` | All events fail sync | events_synced empty, all in events_failed |
| `test_pipeline_dry_run_skips_calendar` | dry_run=True | Calendar methods never called |
| `test_pipeline_records_duration` | Duration tracking | duration_seconds > 0 |
| `test_pipeline_handles_create_action` | action="create" | create_event called |
| `test_pipeline_handles_delete_action` | action="delete" | delete_event called |
| `test_pipeline_handles_update_action` | action="update" | update_event called |
| `test_pipeline_speakers_found_populated` | Speaker list from parse | speakers_found == ["Alice", "Bob"] |
| `test_pipeline_passes_owner_to_extractor` | Owner forwarded | Extractor called with owner="TestOwner" |
| `test_pipeline_passes_current_datetime_to_extractor` | Datetime forwarded | Extractor called with frozen datetime |

### `tests/unit/test_demo_output.py` (10 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_output_contains_transcript_info` | Stage 1 section | Contains file path, speakers, utterance count |
| `test_output_contains_extracted_events` | Stage 2 section | Contains event titles, times, locations |
| `test_output_contains_ai_reasoning` | Reasoning in output | Contains exact reasoning string |
| `test_output_contains_calendar_operations` | Stage 3 section | Contains [CREATE], [UPDATE] markers |
| `test_output_contains_summary_counts` | Summary tallies | "Events extracted: 3", "Synced: 2", "Failed: 1" |
| `test_output_zero_events_message` | Zero events | "No calendar events detected" |
| `test_output_dry_run_shows_would_create` | Dry-run mode | Contains [DRY RUN] markers |
| `test_output_failed_event_shows_error` | Failed sync error | Contains error string inline |
| `test_output_contains_assumptions` | Assumptions rendered | Both assumption strings appear |
| `test_output_contains_duration` | Duration in summary | Contains "2.3s" or similar |

### `tests/unit/test_sample_transcripts.py` (6 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_all_sample_files_exist` | All 6 files present in samples/ | All exist |
| `test_sample_files_are_parseable` | Each file parseable by transcript parser | No exceptions, returns utterances |
| `test_simple_lunch_has_expected_speakers` | simple_lunch.txt speakers | At least 2 distinct speakers |
| `test_multiple_events_has_enough_content` | multiple_events.txt content | At least 6 utterances |
| `test_complex_has_multiple_speakers` | complex.txt speakers | At least 3 distinct speakers |
| `test_no_events_is_casual_conversation` | no_events.txt content | Parses successfully, no scheduling keywords |

### `tests/integration/test_end_to_end.py` (9 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_e2e_simple_lunch` | Full pipeline on simple_lunch.txt | 1 event extracted and synced |
| `test_e2e_multiple_events` | Full pipeline on multiple_events.txt | 3 events extracted and synced |
| `test_e2e_cancellation` | Full pipeline on cancellation.txt | delete_event called, [DELETE] in output |
| `test_e2e_ambiguous_time` | Full pipeline on ambiguous_time.txt | Low confidence event with assumptions |
| `test_e2e_no_events` | Full pipeline on no_events.txt | 0 events, "No calendar events detected" |
| `test_e2e_complex_multi_speaker` | Full pipeline on complex.txt | Multiple events, mixed actions |
| `test_e2e_partial_sync_failure` | One calendar sync fails | Others succeed, failed event has error |
| `test_e2e_llm_failure_graceful_exit` | LLM service down | 0 events, error message, exit 0 |
| `test_e2e_output_structure_has_all_stages` | Demo output structure | Contains "STAGE 1", "STAGE 2", "STAGE 3", "SUMMARY" |

### `tests/integration/test_docker.py` (4 tests)

| Test | What It Tests | Expected |
|---|---|---|
| `test_dockerfile_has_correct_entrypoint` | Dockerfile ENTRYPOINT | Contains `python -m cal_ai` |
| `test_dockerfile_copies_samples` | Dockerfile copies samples/ | Contains COPY for samples/ |
| `test_docker_compose_mounts_env` | docker-compose.yml env | Includes .env in env_file or volumes |
| `test_docker_compose_has_default_command` | Default command present | Default transcript path specified |

**Total: 50 tests** (7 CLI + 14 pipeline + 10 demo output + 6 sample validation + 9 E2E integration + 4 Docker)

---

## Implementation Order
1. Task 4 (sample transcripts) — no code deps, start immediately
2. Task 2 (pipeline orchestrator) — core logic
3. Task 3 (demo output formatter) — depends on PipelineResult from task 2
4. Task 1 (CLI entrypoint) — depends on tasks 2 and 3
5. Task 5 (Docker entrypoint) — depends on task 1
6. Tasks 6-10 (all tests) — depend on all above

## Design Decisions
- **argparse over click**: Zero extra deps. CLI is trivial (1 positional arg + 2-3 flags).
- **PipelineResult as return value**: Structured result for both demo output and tests. Logging is a side effect during execution.
- **Per-event try/except in sync stage**: Key partial-failure requirement. One failure does not kill the rest.
- **Dry-run mode**: Development/testing without Google Calendar credentials.
- **Demo output as separate module**: Keeps formatting out of orchestrator. Easier to test and change.
- **Docker ENTRYPOINT + CMD**: `ENTRYPOINT` for `python -m cal_ai`, `CMD` for default transcript. Users override just the file with `docker compose run app samples/other.txt`.
- **OAuth in Docker**: token.json must be generated on host first, volume-mounted into container. Documented in README.

## Out of Scope
- Web UI or API server
- Batch processing of multiple transcript files
- Watch mode or file monitoring
