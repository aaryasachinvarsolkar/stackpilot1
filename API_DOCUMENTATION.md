# STACKPILOT — API Documentation

This document describes the REST and real-time streaming endpoints provided by the STACKPILOT backend API.

Base URL: `http://localhost:8000`  
Interactive OpenAPI Swagger Docs: `http://localhost:8000/docs`

---

## 1. System & Health

### `GET /health`
Quick liveness check.
- **Response `200 OK`**:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2026-09-23T12:00:00Z"
}
```

### `GET /api/health`
Detailed system and dependency readiness check.
- **Response `200 OK`**:
```json
{
  "status": "healthy",
  "database": "connected",
  "database_type": "sqlite",
  "environment": "development",
  "version": "0.1.0",
  "timestamp": "2026-09-23T12:00:00Z"
}
```

---

> **Implementation status (Phase 2).** Sections 2-4 describe the endpoints that **exist today**.
> Sections 5-7 (agent, sandbox, git) and the upload/index endpoints are **planned and not
> implemented**. There is **no authentication yet** (planned for Phase 4): every endpoint is open.
> Anywhere `{project_id}` appears, the project's UUID or its name is accepted. Unknown projects
> always return `404`; the API never substitutes demo data.

## 2. Projects & Workspace (`/api/projects`)

### `GET /api/projects`
List registered projects (newest first). Read-only. Each item contains `id`, `name`,
`description`, `root_path`, `is_indexed`, `languages`, `last_indexed`, `created_at` (timezone-aware UTC),
`origin` (`user` for projects created through the API; `unclassified` for rows that predate origin tracking), plus:
- `file_count`: measured on disk when the request is made (ignored folders such as
  `node_modules` and symlinks are excluded);
- `workspace_exists`: `false` if the project's folder is missing from disk.

> `is_indexed`, `languages` and `last_indexed` are the stored values. Indexing is not implemented,
> so treat `is_indexed` as unreliable for rows created before Phase 2 (see PROGRESS/Phase 3).

### `POST /api/projects`
Create a project and scaffold its starter files. `201` on success.
```json
{ "name": "my-saas-app", "description": "optional", "source_type": "blank", "template": "FastAPI + Python" }
```
- `name`: 1-100 characters; letters, digits, `.`, `_`, `-`; must start with a letter or digit; no
  spaces, slashes or reserved Windows names (`con`, `nul`, ...). Invalid names return `422`.
- `template`: `FastAPI + Python` (default), `Next.js + TypeScript` or `Go Microservice`; anything
  else returns `422`.
- `source_type`: only `blank` is implemented. `upload` and `git` return `501`.
- `409` if the name is registered (compared ignoring case) **or** a folder with that name already exists on disk (existing
  files are never adopted or overwritten).
- If the database write fails, the folder created by that request is removed and `500` is returned.

### `GET /api/projects/{project_id}`
Project details (same shape as the list items). `404` if unknown.

### `DELETE /api/projects/{project_id}`
Unregisters the project. **Only the database record is removed; files on disk are preserved.**
`204`, or `404` if unknown.

---

## 3. Files (`/api/projects/{project_id}/files`)

Paths are relative to the project's folder. Absolute paths, drive letters or `:`, `..` segments,
NUL bytes, empty paths and anything resolving outside the folder (including via symlinks) return
`400` with `Illegal file path. Path traversal is strictly prohibited.`

### `GET .../files/tree`
Real directory tree of the project folder (ignored folders/files and symlinks are skipped). `404`
if the project is unknown or its folder does not exist; `[]` for an empty folder.

### `GET .../files/content?path=app/main.py`
Returns `path`, `file_name`, `content`, `line_count`, `language`. Content is returned exactly as
stored (no newline translation). `404` missing file or directory, `413` larger than
`MAX_FILE_SIZE_BYTES` (default 2 MiB), `415` binary or non-UTF-8 files.

### `PUT .../files/content`
Body `{"path": "...", "content": "..."}`. Writes the exact UTF-8 bytes atomically (temporary file +
replace) and creates missing parent folders inside the project. Returns
`{"status": "saved", "path", "bytes_written"}`. `404` unknown project or missing project folder
(it is never created implicitly), `400` unsafe path or path is a directory, `413` too large.

---

## 4. AI Chat (`/api/projects/{project_id}/chat`)

### `GET .../chat/history`
Stored messages of the most recent conversation, oldest first; `[]` if there are none.

### `POST .../chat`
Body `{"message": "...", "mode": "agent|chat|review", "conversation_id": null}`.
**Currently always returns `503`**: no LLM provider is implemented or configured yet (planned for
Phase 6). Nothing is stored. Invalid bodies return `422`; unknown projects `404`.

### `GET /api/info`
Lists only the capabilities that exist today and `ai_available` (currently `false`).

---

## 5. Agent Orchestrator & Task Execution (`/api/agent`) — *planned, not implemented*

### `POST /api/agent/task`
Initiate an agentic engineering task (feature addition, refactor, bugfix).
- **Request Body**:
```json
{
  "project_id": "proj_123",
  "prompt": "Add rate limiting middleware to all authenticated routes"
}
```
- **Response**:
```json
{
  "task_id": "task_789",
  "status": "plan_generated",
  "plan": [
    "1. Locate existing middleware stack in src/middleware/",
    "2. Create rateLimiter.ts using token bucket algorithm",
    "3. Register middleware in app router src/routes/index.ts",
    "4. Add unit test in tests/middleware.test.ts",
    "5. Run test suite to verify"
  ]
}
```

### `POST /api/agent/task/{id}/approve`
Approve the plan and initiate tool execution.

### `GET /api/agent/{id}/status`
Check real-time agent execution state, tool calls, and unified diff output.

---

## 6. Execution & Sandbox (`/api/sandbox`) — *planned, not implemented*

### `POST /api/tests/run`
Run test suite inside Docker sandbox.
- **Request Body**:
```json
{
  "project_id": "proj_123",
  "test_command": "npm test"
}
```

### `POST /api/build/run`
Run build command inside Docker sandbox.

---

## 7. Version Control (`/api/git`) — *planned, not implemented*

### `GET /api/git/status?project_id={id}`
Return modified, added, and untracked files.

### `GET /api/git/diff?project_id={id}`
Return current working tree diff.

### `POST /api/git/commit`
Create a Git commit after user approval.
- **Request Body**:
```json
{
  "project_id": "proj_123",
  "message": "feat: add rate limiting middleware"
}
```
