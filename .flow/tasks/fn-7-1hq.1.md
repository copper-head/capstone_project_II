# fn-7-1hq.1 Migrate samples to subdirectory structure and update all references

## Description
Migrate the existing 11 sample transcripts from the flat `samples/` directory into the new category-based subdirectory structure, and update all hardcoded path references across the codebase.

**Size:** M
**Files:** `samples/` (11 files + 5 new dirs), `Dockerfile`, `docker-compose.yml`, `tests/unit/test_sample_transcripts.py`, `tests/integration/test_end_to_end.py`, `tests/integration/test_crud_flows.py`, `tests/integration/test_docker.py`, `tests/unit/test_demo_output.py`

## Approach

- Create subdirectories: `samples/{crud,adversarial,multi_speaker,realistic,long}/`
- Move existing samples per categorization:
  - `crud/`: simple_lunch, update_meeting, cancel_event, cancellation, mixed_crud, clear_schedule
  - `multi_speaker/`: complex, multiple_events
  - `adversarial/`: no_events
  - `realistic/`: ambiguous_time
  - `long/`: (empty, populated by later tasks)
- Delete `multiple_events_copy.txt` (orphan duplicate not in EXPECTED_FILES)
- Update `Dockerfile:L13,16` — `COPY samples/ samples/` stays, `CMD` becomes `["samples/crud/simple_lunch.txt"]`
- Update `docker-compose.yml` — volume mount `./samples:/app/samples:ro` stays (mounts whole tree)
- Update `test_sample_transcripts.py:L14,16-26` — `EXPECTED_FILES` list with new subdir paths
- Update `test_end_to_end.py:L31` and all `_run_e2e()` calls — prefix paths with category
- Update `test_crud_flows.py:L32` and all `_run_crud_e2e()` calls
- Update `test_docker.py` assertions about Dockerfile/compose content
- Update `test_demo_output.py:L78,136` hardcoded paths
- Follow existing `Path("samples")` pattern — just change to `Path("samples/crud")` etc.

## Key context

- `test_sample_transcripts.py` EXPECTED_FILES list at line 16 has 9 entries but there are 11 files in `samples/` — `clear_schedule.txt` and `multiple_events_copy.txt` are NOT in the list
- `docker-compose.yml` volume mount `./samples:/app/samples:ro` recursively mounts all subdirs — no change needed
- The `test_docker.py` tests check for string `"COPY samples/"` and `"samples/"` in Dockerfile/compose content — assertions may need loosening
## Acceptance
- [ ] `samples/{crud,adversarial,multi_speaker,realistic,long}/` subdirectories exist
- [ ] All 10 existing samples (excluding multiple_events_copy.txt) moved to correct category subdir
- [ ] `multiple_events_copy.txt` deleted
- [ ] Dockerfile CMD updated to `["samples/crud/simple_lunch.txt"]`
- [ ] All 5 test files updated with new paths — `pytest` passes with 0 failures
- [ ] `ruff check .` passes
- [ ] No orphan references to flat `samples/*.txt` paths remain
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
