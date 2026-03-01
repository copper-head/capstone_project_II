# fn-9-img.5 Documentation & Deployment Config

## Description

Update project documentation and deployment configuration to reflect the memory system addition, including per-owner DB isolation and memory CLI command.

**Size:** S
**Files:**
- `CLAUDE.md` (modify) — project structure, architecture section, env vars, security
- `.env.example` (modify) — add `MEMORY_DB_PATH`
- `docker-compose.yml` (modify) — add directory volume mount for memory DB + WAL files
- `Makefile` (modify) — add memory-related convenience target
- `.gitignore` (modify if needed) — ensure `data/memory*.db*` is ignored

## Approach

- **CLAUDE.md Project Structure**: Add `memory/` subpackage under `src/cal_ai/` with files: `__init__.py`, `store.py`, `models.py`, `formatter.py`, `extraction.py`, `prompts.py`
- **CLAUDE.md Architecture**: Add a "Memory System" section after the existing "Calendar-Aware CRUD Intelligence" section. Describe the dual-call pipeline: read path (load → format → inject) and write path (extract facts → decide actions → write). Mention per-owner DB isolation (slugified OWNER_NAME → separate DB file). Reference `docs/memory_system_design.tex` for detailed design.
- **CLAUDE.md Commands**: Document `python -m cal_ai memory` CLI subcommand
- **CLAUDE.md Environment Variables**: Add `MEMORY_DB_PATH` (optional, overrides auto-generated default from `OWNER_NAME`)
- **CLAUDE.md Security**: Add `memory*.db` to the "never commit" list
- **.env.example**: Add `# MEMORY_DB_PATH=data/memory.db` (commented out) with comment explaining it's optional and defaults to auto-generated path from OWNER_NAME
- **docker-compose.yml**: Mount a **directory volume** (not a single file) for the memory DB. Use `- ./data:/app/data` or a named volume so that SQLite WAL sibling files (`-wal`, `-shm`) persist alongside the main DB file. Point `MEMORY_DB_PATH` inside the mounted directory.
- **Makefile**: Add `make clean-memory` target to remove memory DB files (useful during development)
- **.gitignore**: Ensure `data/memory*.db*` pattern covers per-owner DB files and WAL siblings

## Key context

- CLAUDE.md is the primary developer reference — existing architecture docs at lines 92-114 follow a specific pattern (pipeline diagram + prose explanation)
- `.env.example` currently has 3 required vars (`GEMINI_API_KEY`, `GOOGLE_ACCOUNT_EMAIL`, `OWNER_NAME`) — `MEMORY_DB_PATH` is optional and should be commented out to show the auto-generated default is preferred
- `docker-compose.yml` already mounts `.env` and `credentials.json` — memory needs a directory mount, not a file mount, due to WAL sibling files
- Use generic model references ("Gemini via google-genai") rather than specific model names/pricing, since the model is configurable
- Per-owner isolation means multiple DB files can exist in `data/` (e.g., `memory_alice.db`, `memory_bob.db`) — gitignore pattern must cover all

## Acceptance
- [ ] CLAUDE.md project structure includes `memory/` subpackage with all module files listed
- [ ] CLAUDE.md has "Architecture: Memory System" section describing dual-call pipeline and per-owner DB isolation
- [ ] CLAUDE.md commands section documents `python -m cal_ai memory` CLI subcommand
- [ ] CLAUDE.md environment variables section documents `MEMORY_DB_PATH` as optional override (defaults to auto-generated from `OWNER_NAME`)
- [ ] CLAUDE.md security section includes `memory*.db` in "never commit" list
- [ ] `.env.example` includes commented-out `MEMORY_DB_PATH` with explanation of auto-generated default
- [ ] `docker-compose.yml` mounts a directory volume (not single file) for memory DB + WAL persistence
- [ ] `Makefile` has `clean-memory` target
- [ ] `.gitignore` covers `data/memory*.db*` (per-owner DB files + WAL siblings)
- [ ] No hardcoded model names or specific pricing in documentation (use generic references)
- [ ] `make lint` passes

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
