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
- **Path Traversal Protection**: All file read and write operations enforce strict boundary checks ensuring file paths reside inside the project's authorized root directory. Attempts to reference `../../etc/passwd` or parent directories are rejected with `403 Forbidden`.
- **User Authorization**: Projects and files are isolated per user UUID with JWT authentication.
