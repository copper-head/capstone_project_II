# fn-9-img.1 Memory Store Foundation (SQLite + Models + Config + CLI)

## Description
Create the `src/cal_ai/memory/` subpackage with SQLite store, Pydantic models, config integration with per-owner DB isolation, and `python -m cal_ai memory` CLI subcommand.

**Size:** M
**Files:**
- `src/cal_ai/memory/__init__.py` (new) — public API exports
- `src/cal_ai/memory/store.py` (new) — MemoryStore class with SQLite CRUD
- `src/cal_ai/memory/models.py` (new) — Pydantic models for memory data
- `src/cal_ai/config.py` (modify) — add `memory_db_path` field to Settings with per-owner default
- `src/cal_ai/__main__.py` (modify) — add `memory` subcommand
- `tests/unit/test_memory_store.py` (new) — unit tests

## Approach

- Follow the `src/cal_ai/calendar/` subpackage structure as a template
- `MemoryStore.__init__(db_path)`: Create parent directories (`Path(db_path).parent.mkdir(parents=True, exist_ok=True)`), then connect to SQLite and run `CREATE TABLE IF NOT EXISTS` for both tables. Provides `load_all()`, `upsert()`, `delete()`, `log_action()` methods.
- **`upsert(category, key, value, confidence)`** is the single write primitive for both ADD and UPDATE actions. Uses `INSERT INTO memories (...) VALUES (...) ON CONFLICT(category, key) DO UPDATE SET value=excluded.value, confidence=excluded.confidence, source_count=source_count+1, updated_at=excluded.updated_at`. Returns the row `id` (via `cursor.lastrowid` or a follow-up SELECT).
- **`delete(memory_id)`** removes a memory row by id
- **`log_action(action, memory_id, category, key, old_value, new_value, transcript)`** writes to `memory_log` with category/key snapshots for durable traceability after deletion
- `memory_log.memory_id` is a historical reference, NOT an enforced FK — no `PRAGMA foreign_keys` needed for this table
- Use `sqlite3.Row` row factory for named column access
- Set `PRAGMA journal_mode=WAL` on connection creation
- Pydantic models: `MemoryRecord` (DB row representation), `MemoryFact` (extracted fact from LLM), `MemoryAction` (LLM action decision with required `reasoning` field), response wrappers for structured output
- Gemini alphabetically sorts response_schema keys — name fields so alpha order matches logical order
- **Per-owner DB isolation**: `Settings.memory_db_path` defaults to `data/memory_{slugified_owner}.db`, auto-generated from `OWNER_NAME` via slugification (lowercase, replace spaces/special chars with underscores, e.g., `"Alice Smith"` → `data/memory_alice_smith.db`). If `MEMORY_DB_PATH` is explicitly set in `.env`, it overrides the auto-generated path. This ensures changing `OWNER_NAME` gives each owner their own memory store.
- Store ISO 8601 timestamps as TEXT using `datetime.now(UTC).isoformat()`
- Unit tests must use `tmp_path / "memory.db"` (file-based), NOT `:memory:`, because WAL mode is not meaningful for in-memory databases
- **Memory CLI**: Add `memory` subcommand to `__main__.py` (same pattern as existing `benchmark` subcommand). Instantiate `MemoryStore`, call `load_all()`, display as formatted table grouped by category showing key/value/confidence/source_count. Current memories only (no audit log display).

## Key context

- SQLite UPSERT syntax: `INSERT INTO t (...) VALUES (...) ON CONFLICT(col) DO UPDATE SET col = excluded.col` — `excluded` references the attempted INSERT values
- The `UNIQUE(category, key)` constraint enables natural deduplication
- `source_count` increments on every upsert (whether ADD or UPDATE) to track confirmation frequency
- `memory_log` stores `category` and `key` snapshots so audit trail survives memory deletion
- Gemini structured output pitfall: `Field(default=...)` works in SDK v1.63.0+ (issue #699 fixed). But prefer `Optional[type] = None` for nullable fields in response schemas
- `data/` directory does not exist in the repo — `MemoryStore.__init__` must create parent directories before connecting
- `__main__.py` already has a `benchmark` subcommand pattern to follow for the `memory` subcommand

## Acceptance
- [ ] `src/cal_ai/memory/` subpackage exists with `__init__.py`, `store.py`, `models.py`
- [ ] `MemoryStore.__init__(db_path)` creates parent directories, creates DB file, and runs `CREATE TABLE IF NOT EXISTS` for both `memories` and `memory_log` tables
- [ ] `MemoryStore.load_all()` returns all memories ordered by category, key
- [ ] `MemoryStore.upsert(category, key, value, confidence)` inserts new or updates existing via `ON CONFLICT(category, key) DO UPDATE`, increments `source_count`, updates `updated_at`
- [ ] `MemoryStore.delete(memory_id)` removes a memory row by id
- [ ] `MemoryStore.log_action(action, memory_id, category, key, old_value, new_value, transcript)` writes to `memory_log` with category/key snapshots
- [ ] `memory_log` schema includes `category` and `key` columns — no FK constraint on `memory_id`
- [ ] Pydantic models: `MemoryFact(category, key, value, confidence)`, `MemoryAction(action, category, key, new_value, target_memory_id, reasoning)` with required `reasoning` field, response wrappers
- [ ] `MemoryAction` model has `confidence` field allowing action decision LLM to set final confidence (may differ from extraction's proposal)
- [ ] `Settings.memory_db_path` auto-generated from slugified `OWNER_NAME` (e.g., `data/memory_alice_smith.db`); `MEMORY_DB_PATH` env var overrides when explicitly set
- [ ] Slugification: lowercase, replace spaces/special chars with underscores
- [ ] `python -m cal_ai memory` CLI subcommand displays current memories in formatted table grouped by category (key/value/confidence/source_count)
- [ ] Unit tests use `tmp_path / "memory.db"` (file-based, not `:memory:`)
- [ ] Unit tests cover: upsert (new + existing/increment), delete, load_all (empty and populated), schema auto-creation with parent dir creation, log_action with category/key snapshots
- [ ] `make test` passes with new tests included

## Done summary
Created the memory store foundation: src/cal_ai/memory/ subpackage with SQLite-backed MemoryStore (upsert/delete/load_all/log_action with WAL mode), Pydantic models (MemoryRecord, MemoryFact, MemoryAction with response wrappers), per-owner DB isolation in Settings via slugified OWNER_NAME, and python -m cal_ai memory CLI subcommand. Includes 30 unit tests covering all CRUD operations, schema creation, audit log traceability, and correct ID return on upsert update path.
## Evidence
- Commits: a3a25a4, 038a6df
- Tests: python3 -m pytest tests/unit/test_memory_store.py -v (30 passed), python3 -m pytest (476 passed, 40 skipped), make lint (all checks passed)
- PRs: