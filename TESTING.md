# STACKPILOT — Testing Strategy

STACKPILOT maintains a rigorous multi-tier testing strategy ensuring reliability, deterministic agent execution, and robust vector retrieval.

---

## 1. Test Levels

### 1.1 Unit Tests
- **AST Parser**: Validate symbol extraction, function boundaries, and class hierarchy across languages.
- **Semantic Chunker**: Ensure chunk boundaries respect AST scopes and maintain proper metadata.
- **RAG Engine**: Verify vector similarity math, context ranking, and context compression rules.
- **Agent Planner**: Verify decomposition of user instructions into structured plans.
- **Controlled Tools**: Mocked tool tests (`read_file`, `modify_file`, `search_code`).
- **Database Layer**: Validate async connection lifecycle, model mappings, and query builders.

### 1.2 Integration Tests
- **Backend <-> Database**: Test migrations, relational cascading, and vector index persistence.
- **Backend <-> Frontend API**: Validate REST routes, WebSocket event streaming, and error handling.
- **Agent <-> Sandbox Runner**: Test isolated command execution and timeout enforcement.

### 1.3 End-to-End (E2E) Flow
Simulate full autonomous developer workflows:
1. Create project & import files.
2. Index codebase and verify chunks/vectors stored.
3. Query codebase via RAG and verify grounded response.
4. Issue prompt: "Add new endpoint".
5. Agent proposes plan -> plan approved -> files modified -> tests run in sandbox -> unified diff accepted -> Git commit verified.

---

## 2. Test Execution Commands

> **Status (Phase 1):** the sections above describe the target strategy. What exists today is the
> backend API suite described below. There are no frontend tests yet (`npm test` is not defined);
> only `npx tsc --noEmit` type-checking is available. Sandbox, RAG, AST and agent tests do not
> exist because those features are not implemented.

### Backend Tests
Use Python 3.13 and install the pinned dependencies into a virtual environment:
```bash
cd backend
py -3.13 -m venv .venv            # or reuse your existing 3.13 environment
.venv\Scripts\python -m pip install -r requirements-dev.lock
.venv\Scripts\python -m pytest -v
```
`requirements.txt` / `requirements-dev.txt` list the direct, pinned dependencies (edit these).
`requirements.lock` / `requirements-dev.lock` pin the complete tree including transitive
packages; install from the `.lock` files for reproducible environments (the Dockerfile will move
to `requirements.lock` in the deployment phase).

### Dependency locking
Regenerate the locks after changing a `requirements*.txt` file, in a clean Python 3.13 venv:
```bash
py -3.13 -m venv %TEMP%\lockenv
%TEMP%\lockenv\Scripts\python -m pip install -r requirements.txt
%TEMP%\lockenv\Scripts\python -m pip freeze   # -> requirements.lock (keep the header comments)
# repeat with requirements-dev.txt -> requirements-dev.lock
```
Verify by building another fresh venv from the `.lock` file: `pip check` must be clean, `pip freeze`
must equal the lock, and the test suite must pass. `colorama` in the dev lock is only needed on
Windows and is harmless elsewhere.

### Test isolation (important)
`backend/tests/conftest.py` runs every session against a **throwaway SQLite database and working
directory** in the system temp folder, and deletes them afterwards. It overrides `DATABASE_URL`
and `WORKSPACES_ROOT` before the app is imported, refuses to start if the engine could point at
`backend/stackpilot.db`, and fingerprints the real database and `backend/workspaces/` at the start
and end of the session (failing the run if either changed). `tests/test_isolation.py` asserts these
guarantees.
Never run the app's test suite against a different harness: the old behaviour created and dropped
tables in the development database.

### Backend test files (Phase 2)
| File | Covers |
|---|---|
| `test_workspace_paths.py` | Path/name safety helpers: traversal, absolute and drive paths, symlink/junction escape, name rules |
| `test_files.py` | File API: real tree, read/write round-trip, 404/413/415/400 cases, containment |
| `test_projects.py` | Project API: validation, 409/501 cases, file counts from disk, rollback, delete keeps files |
| `test_chat.py` | Chat history and the honest 503 (no AI provider yet) |
| `test_security_regressions.py` | One test per audited defect (F1, F2, F3, F3b, F4, F6, F7) |
| `test_isolation.py` | The test harness cannot touch real data |

The audited defects were first captured as strict-xfail tests (Phase 1). Phase 2 fixed them, the
strict xfails flipped to failures (XPASS), and the markers were removed. Run the suite from
`backend/`; the expected result is all tests passing (see the phase report for the current count).

### Backup before risky work
```bash
python scripts/backup.py create --dest C:\path\outside\the\repo\backups
python scripts/backup.py verify C:\path\outside\the\repo\backups\<date>
```
Backs up the SQLite database (online backup API), `backend/workspaces/` (zip + SHA-256 manifest)
and the env files, then verifies integrity, row counts and hashes. The destination must be
outside the repository.

### Frontend checks
```bash
cd frontend
npx tsc --noEmit --incremental false
```
