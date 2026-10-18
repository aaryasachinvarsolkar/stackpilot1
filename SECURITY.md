# STACKPILOT — Security & Safety Specification

Security is non-negotiable when dealing with autonomous code generation and automated command execution. STACKPILOT implements defense-in-depth across execution, secrets, and authorization.

---

## 1. Sandboxed Command Execution
- **Container Isolation**: AI agents CANNOT run arbitrary bash or shell commands directly on the host system. All execution (`npm test`, `pytest`, `npm run build`, `mvn test`) occurs within isolated Docker containers.
- **Resource Constraints**:
  - Memory limit (default: 512 MB max).
  - CPU quotas (default: 1 CPU core max).
  - Strict wall-clock execution timeouts (default: 60s max per execution).
- **Network Isolation**: By default, sandbox test containers run with internal networking only (no external internet egress allowed during test execution to prevent data exfiltration).

---

## 2. Zero-Secret Exposure
- **Never In LLM Prompts**: API keys, database credentials, JWT secrets, and Git access tokens are strictly stripped from all context windows and prompts sent to external LLMs.
- **Environment Scrubbing**: Environment variables are scanned before prompt generation; any variables matching sensitive patterns (`*KEY*`, `*SECRET*`, `*TOKEN*`, `*PASSWORD*`) are redacted.
- **Log Masking**: Tool call logs and API request traces mask any matching authorization headers or secret values.

---

## 3. Human Approval Gates
Autonomous execution is bounded by explicit human checkpoints:
1. **Plan Approval**: The agent must display a numbered plan before executing multi-file edits.
2. **Diff Approval**: The user must review and accept unified diffs before any changes are written permanently or committed to VCS.
3. **Sensitive Git Operations**: `git push origin ...` or branch deletions require unambiguous Allow/Reject interactive confirmation.

---

## 4. Input Validation & Project Isolation
- **Path Traversal Protection** *(implemented in Phase 2)*: All file read and write operations resolve the requested path (symlinks included) and require it to stay inside the project's folder. Absolute paths, drive letters / `:`, `..` segments, NUL bytes and empty paths are rejected with `400 Bad Request`. Project names are validated (letters, digits, `.`, `_`, `-`; no slashes or reserved names) before being used as folder names. The checks live in `backend/app/services/workspace.py` and are covered by `tests/test_workspace_paths.py`, `tests/test_files.py` and `tests/test_security_regressions.py`. Known limitation: a path is checked and then used, so a local attacker who can swap a folder for a symlink between those two steps is not handled.
- **File limits**: reads and writes are capped at `MAX_FILE_SIZE_BYTES` (default 2 MiB); binary and non-UTF-8 files are refused rather than corrupted. Writes are atomic.
- **No silent success**: unknown projects, missing files and missing project folders return `404`; unavailable features return `501`/`503`. The API no longer returns demo data.
- **User Authorization** *(NOT implemented yet, planned for Phase 4)*: Projects and files are intended to be isolated per user UUID with JWT authentication. Today **every endpoint is unauthenticated**, so run the backend only on a trusted local machine. `JWT_SECRET` still has a placeholder default that must not be used outside development.
