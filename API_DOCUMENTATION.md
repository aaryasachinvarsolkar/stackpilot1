# STACKPILOT — API Documentation

This document describes the REST and real-time streaming endpoints provided by the STACKPILOT backend API.

Base URL: `http://localhost:8000`  
Interactive OpenAPI Swagger Docs: `http://localhost:8000/docs`

**Host header.** There is no authentication yet, so the API only answers requests whose `Host` header names a loopback
host: `127.0.0.1` or `localhost`, with or without a port (`ALLOWED_HOSTS`, default `127.0.0.1,localhost`; a wildcard is
refused at startup). Any other host, including a missing one, gets `400 Invalid host header` before routing, CORS or any
endpoint runs. This stops DNS-rebinding attacks from other web pages. The match is exact and case-sensitive, and bracketed
IPv6 forms such as `[::1]` are not accepted. Open the app through `http://localhost:...` or `http://127.0.0.1:...`.

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
- `source_type`: only `blank` is implemented here. `upload` and `git` return `501` on this endpoint; import projects
  with `POST /api/projects/upload` and `POST /api/projects/git` below.
- `409` if the name is registered (compared ignoring case) **or** a folder with that name already exists on disk (existing
  files are never adopted or overwritten).
- If the database write fails, the folder created by that request is removed and `500` is returned.

### `POST /api/projects/upload` (multipart form)
Create a project from a ZIP archive. Form fields: `file` (the ZIP), `name` (same rules as above), optional `description`.
`201` on success. A single shared top-level folder (`repo-main/...`) is dropped; `.git`, `node_modules`, `__pycache__`
and the other ignored folders are skipped.

**Every entry is checked before anything is written, and one unsafe entry rejects the whole archive** (`400`, nothing is
created, no project record). Rejected: `..` segments, absolute paths, drive letters or any `:` (including NTFS streams),
empty or `.` segments, backslash tricks, characters Windows forbids, trailing dots or spaces, reserved device names
(`con`, `nul`, ...), over-long names, symbolic links and other non-regular entries, encrypted entries, duplicate
destinations (case-insensitively) and a name used as both a file and a folder.

Limits, all enforced on the bytes actually read or written (never on a header or an archive's own size claims):

| Setting | Default | Exceeding it |
|---|---|---|
| `MAX_UPLOAD_BYTES` | 50 MiB | `413` (upload or download of the ZIP itself; the body is cut off while it arrives) |
| `MAX_ZIP_UNCOMPRESSED_BYTES` | 200 MiB | `413` (total size of the extracted files) |
| `MAX_ZIP_ENTRIES` | 5000 | `413` (files and folders in the archive) |

Other errors: `400` empty upload, a file that is not a valid ZIP (also corrupt, truncated or unsupported compression),
or an unsafe entry; `409` the name is already used; `422` invalid name. A failed import removes whatever it created. Error
messages are generic: they never contain internal exception text or the offending entry's name. `500` means an unexpected
server error (`The project could not be imported.`); details are only in the server log.

### `POST /api/projects/git`
Create a project from a public GitHub repository. Body `{"name", "git_url", "branch"?, "description"?}`; the archive of the
branch (then `master`, then `main`) is downloaded from `github.com` and imported exactly like an upload, with the same
archive checks and limits (the download is cut off at `MAX_UPLOAD_BYTES` and answers `413`).

`git_url` must be a plain repository URL: `https://github.com/owner/repo`, optionally with `http://`, `www.`, no scheme,
a trailing `/` or a literal `.git` suffix, or `git@github.com:owner/repo.git`. Anything else is `400` before any network
request is made: other hosts, extra path parts such as `/tree/main`, queries or fragments, ports, credentials, and
`.` or `..` as owner or repository. A repository whose archive cannot be downloaded is `400`.

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
Returns `path`, `file_name`, `content`, `line_count`, `language`, `sha256`. Content is returned
exactly as stored (no newline translation). `sha256` is the lowercase hex SHA-256 of the exact bytes
on disk; a save must send it back as `base_sha256`. `404` missing file or directory, `413` larger
than `MAX_FILE_SIZE_BYTES` (default 2 MiB), `415` binary or non-UTF-8 files.

### `PUT .../files/content`
Body `{"path": "...", "content": "...", "base_sha256": "<64 hex characters>"}`.

**Updates an existing file only, and only if it is unchanged since it was loaded.** It never creates
a file or a folder, and `base_sha256` is required: send the `sha256` returned by
`GET .../files/content` for the content the edit is based on. Writes the exact UTF-8 bytes
atomically (temporary file + replace) and returns
`{"status": "saved", "path", "bytes_written", "sha256"}`, where `sha256` is the hash of the content
just written (use it as the next `base_sha256`).

Checks run in this order; every rejection leaves the disk untouched (no bytes changed, nothing
created, no temporary file left behind):

| # | Status | Condition |
|---|---|---|
| 1 | `404` | unknown project |
| 2 | `404` | project folder missing on disk (never created implicitly) |
| 3 | `400` | unsafe path |
| 4 | `413` | content larger than `MAX_FILE_SIZE_BYTES` |
| 5 | `428` | `base_sha256` missing (or `null`) |
| 6 | `400` | `base_sha256` is a string but not exactly 64 hexadecimal characters (empty string, wrong length, non-hex characters, surrounding whitespace, a `sha256:` or `0x` prefix) |
| 7 | `400` | path is a directory |
| 8 | `404` | file does not exist (never existed, or deleted since it was loaded) |
| 9 | `409` | file on disk differs from `base_sha256`: it changed since it was loaded |

**Wrong JSON type is a different error.** If `base_sha256` is not a JSON string at all (a number, a
boolean, a list or an object), the request is rejected by request validation with `422` and the usual
FastAPI validation body (`{"detail": [...]}`), before the handler's own checks above run. So: a
*string* that is not a valid hash gives `400` (check 6), while a *non-string* value gives `422`.
Either way nothing is written.

A `409` or `404` response never contains file content; reload the file with `GET` to see its current
content and hash.

**Client note (the built-in editor).** If a save is accepted but the file read back afterwards differs
from what was submitted, the editor keeps the *submitted* `base_sha256` instead of adopting the hash of
the unexpected disk content, and marks the file unsaved. The next ordinary save is then answered with
`409`, and only an explicit "reload" or "overwrite" action moves on. Other clients should do the same:
never use a hash the user has not seen as the base of a routine save.

**Compatibility:** this is a breaking change for clients that wrote without a hash or created files
through `PUT`; they now receive `428` / `404`. The only built-in client is the editor
(`saveFileContent`). Limit: saves are serialised inside one server process and the hash is checked
before the temporary file is written and again just before the swap, but a different process
modifying the same file in exactly that instant can still win; the operating system offers no
portable "replace only if unchanged".

---

## 4. AI Chat (`/api/projects/{project_id}/chat`)

The chat answers a question **from the project's own files**, read-only, and checks the citations it returns. It changes no
file and runs no code. These are backend behaviors; this document makes no claim about what any client displays.

**Privacy switch: `ALLOW_SENDING_CODE_TO_PROVIDER` (default `false`).** It can only be set in the backend's environment (no
endpoint, request field or UI can change it). While it is `false`, **no request is ever made to an AI provider and no project
file is read**, even if `LLM_PROVIDER` and `LLM_API_KEY` are configured. Order of work for every question, stopping at the
first step that fails: (1) the provider is configured with a real key, (2) consent is on, (3) local retrieval, (4) one provider
request, (5) strict parsing of the reply, (6) citation validation. Steps 1 and 2 happen before any file is opened and are
repeated inside the only function that makes the provider request.

### `GET .../chat/status`
What the chat can do right now. `404` for an unknown project. It sends nothing and never contains a key.
```json
{ "provider": "openai", "model": "gpt-4o", "configured": true, "consent": false, "can_send": false,
  "reason": "Sending your question to the 'openai' AI provider is turned off ..." }
```
`provider` is `mock` when none is chosen; `model` is `null` unless a supported provider is fully configured; `can_send` is
`configured && consent`; `reason` is `null` when `can_send` is true.

### `POST .../chat`
Body `{"message": "...", "mode": "agent|chat|review", "conversation_id": null}`. `mode` is accepted for compatibility and does
not change behavior. Always `200` with an assistant message unless the request is invalid: `422` for a bad body, `404` for an
unknown project, and `404` (`Conversation not found in this project.`) for a `conversation_id` that is not this project's;
nothing is read, sent or written in that case, and there is no fallback to another conversation.

```json
{ "conversation_id": "...", "message_id": "...", "sender": "assistant", "content": "It is defined on line 6.",
  "status": "answered_verified",
  "citations": [ { "file_path": "lib/service.py", "line_start": 6, "line_end": 6, "symbol": null, "status": "verified",
                   "excerpt_id": "E1", "file_sha256": "...", "range_sha256": "..." } ],
  "plan_steps": [],
  "grounding": { "version": 1, "reason": "all_citations_verified", "answerable": true, "provider": "openai",
                 "retrieval": { "excerpts": 3, "chars": 2410, "files": 2, "redactions": 0, "scan_truncated": false },
                 "citations": [ { "excerpt_id": "E1", "path": "lib/service.py", "start_line": 6, "end_line": 6,
                                  "status": "verified", "reason": "current", "file_sha256": "...", "range_sha256": "..." } ] },
  "timestamp": "..." }
```

**`status`** is derived from what was actually checked, never from what the model claims:

| `status` | Meaning |
|---|---|
| `answered_verified` | The model answered, gave at least one citation, and **every** citation is `verified`. |
| `answered_unverified` | The model answered, but there is no citation, or at least one is `stale` or `invalid`. |
| `not_in_context` | No excerpt of the project's files matched the question (the provider was **not** called), or the model said the excerpts do not contain the answer. `content` is a fixed message; the model's text is discarded. |
| `unavailable` | No answer was produced: not configured, consent off, the project's files could not be read, the provider failed or timed out, or its reply was unusable. `content` says why, without raw provider text, keys, prompts or file contents. |

**A verified citation does not mean the answer is correct.** It means the cited lines exist, were among the lines shown to the
model, and are unchanged right now. A model can cite real lines and still misread them.

**Citation validation.** The model must cite by excerpt id and line range. For every citation:
- The id must be one issued for this very request (`E1`, `E2`, ...). The path is always taken from that excerpt; a `file_path`,
  `path`, `file_sha256` or `sha256` the model adds must equal the excerpt's or the citation is `invalid`
  (`path_mismatch` / `hash_mismatch`). Traversal, absolute, UNC and drive-letter strings, NUL characters and wrong types are
  therefore rejected, and nothing a model supplied is echoed back.
- The lines must be whole positive integers, at most 200 lines, and lie inside the excerpt that was shown.
- The file is then re-read with the retrieval engine's own rules (containment inside the project, symlinks and junctions,
  prohibited, binary, generated and oversized files) and compared using the editor's line numbering (`\r\n`, `\r` and `\n`
  only; not `files.py`'s `line_count`) and the same redaction:
  - the file is gone, replaced by something else (a folder, a link, a file outside the project) or no longer permitted: `invalid`;
  - the file's hash is unchanged, or the cited lines are identical to those shown: `verified` (`current` / `file_changed_elsewhere`);
  - the cited lines differ, or the file became shorter: `stale` (`cited_lines_changed` / `file_shorter`).
- At most 12 citations are examined; extra ones add one `invalid` entry (`too_many_citations`).

`citations` in the response lists the `verified` and `stale` ones. `invalid` citations are not listed; they are counted (reason
only, never the model's text) in `grounding.citations`.

**Structured model output.** The provider is asked for JSON `{"answerable": bool, "answer": "plain text", "citations":
[{"excerpt_id": "E1", "line_start": 12, "line_end": 18}]}`. Any other shape, an empty answer, or non-JSON is `unavailable`.

**What is sent to the provider** (and nothing else): the rules, at most 8 retrieved excerpts (24,000 characters in total, line
numbers included, secrets redacted in place) wrapped in delimiters that carry a random per-request code, and the current
question. `.env`, key files, `secrets*`, binaries, generated files and ignored folders are never read. File text is treated as
untrusted data: the rules forbid following instructions found in it, and since only this request's excerpt ids can be cited,
text in a file cannot make an answer cite anything else. **Earlier questions and answers are never sent**: every question
stands alone, although messages are stored. Supported providers: `openai`, `groq`, `gemini` (the Gemini key travels in the
`x-goog-api-key` header). Questions, answers, excerpts and keys are not written to the server log.

**What is stored.** The assistant message keeps `status` and `grounding`: retrieval counts, and per citation the excerpt id, path,
line range, status, reason and two hashes (the file's at retrieval, and the cited lines as the model saw them). **No source code
or excerpt text is stored in `grounding` or `citations`.** `plan_steps` is no longer written for new messages and is always `[]`.

### `GET .../chat/history`
Stored messages of the most recent conversation, oldest first; `[]` if there are none. Each item has `id`, `sender`, `content`,
`citations`, `plan_steps`, `timestamp`, `status` and `grounding`. A message written before answers were grounded has no stored
status: an assistant message is returned with `status: "legacy"` and `grounding: null`, a user message with `status: null`. Its
stored `citations` and `plan_steps` are returned exactly as they were, with no verification added; **a legacy message is never
reported as verified.** (Citations stored in new messages are not re-checked when the history is read; their `status` is the
result at the time of the answer.)

### Database migration required
Messages gained two nullable columns (`status` VARCHAR(24), `grounding` JSON) in migration `0003`. The backend refuses to start
on a database that is not at the current revision and never migrates one by itself. An existing database must be migrated on
purpose, after a backup: `alembic upgrade head`. The migration only adds the two columns (existing rows get NULL, which is what
makes them "legacy"); `alembic downgrade 0002` removes exactly those two columns and nothing else. A fresh database is created
at the current revision automatically.

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
