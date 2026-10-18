# STACKPILOT — Database Schema

STACKPILOT leverages a relational database (PostgreSQL in production, SQLite for local zero-dependency development) equipped with vector extension (`pgvector`) for storing dense semantic embeddings of code chunks.

---

## 0. What is actually implemented (Phase 3a)

Sections 1-2 below are the **target design**. The database that exists today has four tables:
`projects`, `project_files`, `conversations`, `messages`. There is no `users` table, no
`code_chunks`/`embeddings`/`tasks`/`agent_runs`/`tool_calls`/`test_runs`/`git_commits`, and the
columns differ from the design (for example `projects.languages` is JSON, not `language_summary`).

Differences from the design that are intentional for now:
- `projects` additionally has `origin` (`unclassified`, `user`, `import`, `upload`, `git`, `seed`),
  `archived_at`, `last_scanned_at`; `project_files` has `file_hash`.
- Project names are unique ignoring case (`ux_projects_name_lower`); a file path is unique per
  project (`ux_project_files_project_path`).
- Timestamps are timezone-aware UTC in the API on every backend. SQLite stores them as text without
  an offset (always UTC); the `UTCDateTime` type restores the offset when reading.
- SQLite connections enforce foreign keys, so `ON DELETE CASCADE` really cascades.

### Migrations (Alembic)
Schema changes are made only through Alembic (`backend/alembic/`). `create_all` is no longer used.

| Revision | Content |
|---|---|
| `0001` | Baseline: exactly the schema the application created before migrations existed |
| `0002` | Adds `origin`, `archived_at`, `last_scanned_at`, `file_hash` and the integrity indexes. Additive only: no existing value changes; existing projects become `origin='unclassified'` |

Run from `backend/` (the URL comes from `DATABASE_URL`):
```bash
alembic current                 # show the database's revision
alembic upgrade head            # apply pending migrations
alembic downgrade 0001          # undo 0002 (original columns and data are untouched)
alembic stamp 0001              # ONLY for a database created before Alembic: marks it as the baseline
```
**Startup behaviour:** the app never migrates an existing database by itself. On a completely empty
database it creates the schema; if the database already has tables but is unstamped or behind
`head`, it refuses to start and prints the command to run. **Always take a verified backup first**
(`python scripts/backup.py create ...`, see TESTING.md). SQLite migrations run in a single
transaction (a failure rolls everything back); `0002` also checks for conflicting data before it
changes anything.

---

## 1. Entity Relationship Overview

```
Users
  └── Projects
        ├── ProjectFiles
        │     └── CodeChunks
        │           └── Embeddings (pgvector: vector(1536) / vector(384))
        ├── Conversations
        │     └── Messages
        ├── Tasks
        │     └── AgentRuns
        │           └── ToolCalls
        ├── TestRuns
        └── GitCommits
```

---

## 2. Table Definitions

### 2.1 `users`
- `id` (UUID, Primary Key)
- `email` (VARCHAR(255), Unique, Not Null)
- `hashed_password` (VARCHAR(255), Not Null)
- `full_name` (VARCHAR(255))
- `created_at` (TIMESTAMP WITH TIME ZONE, Default NOW())
- `updated_at` (TIMESTAMP WITH TIME ZONE, Default NOW())

### 2.2 `projects`
- `id` (UUID, Primary Key)
- `user_id` (UUID, Foreign Key -> `users.id`)
- `name` (VARCHAR(255), Not Null)
- `description` (TEXT)
- `root_path` (VARCHAR(1024), Not Null)
- `is_indexed` (BOOLEAN, Default False)
- `language_summary` (JSONB)
- `created_at` (TIMESTAMP WITH TIME ZONE)
- `updated_at` (TIMESTAMP WITH TIME ZONE)

### 2.3 `project_files`
- `id` (UUID, Primary Key)
- `project_id` (UUID, Foreign Key -> `projects.id`)
- `file_path` (VARCHAR(1024), Not Null)
- `file_name` (VARCHAR(255), Not Null)
- `file_size_bytes` (INTEGER)
- `language` (VARCHAR(64))
- `file_hash` (VARCHAR(64))
- `last_scanned_at` (TIMESTAMP WITH TIME ZONE)

### 2.4 `code_chunks`
- `id` (UUID, Primary Key)
- `project_id` (UUID, Foreign Key -> `projects.id`)
- `file_id` (UUID, Foreign Key -> `project_files.id`)
- `chunk_index` (INTEGER, Not Null)
- `chunk_type` (VARCHAR(64)) -- e.g., 'function', 'class', 'method', 'module'
- `symbol_name` (VARCHAR(255))
- `start_line` (INTEGER, Not Null)
- `end_line` (INTEGER, Not Null)
- `content` (TEXT, Not Null)
- `metadata_json` (JSONB) -- imports, decorators, dependencies

### 2.5 `embeddings`
- `id` (UUID, Primary Key)
- `chunk_id` (UUID, Foreign Key -> `code_chunks.id`, Unique)
- `model_name` (VARCHAR(128), Not Null)
- `dimensions` (INTEGER, Not Null)
- `vector` (VECTOR(1536)) -- pgvector type; or TEXT in SQLite fallback
- `created_at` (TIMESTAMP WITH TIME ZONE)

### 2.6 `conversations`
- `id` (UUID, Primary Key)
- `project_id` (UUID, Foreign Key -> `projects.id`)
- `title` (VARCHAR(255))
- `created_at` (TIMESTAMP WITH TIME ZONE)

### 2.7 `messages`
- `id` (UUID, Primary Key)
- `conversation_id` (UUID, Foreign Key -> `conversations.id`)
- `sender` (VARCHAR(32)) -- 'user', 'assistant', 'system'
- `content` (TEXT, Not Null)
- `citations` (JSONB) -- references to files & line numbers
- `token_count` (INTEGER)
- `created_at` (TIMESTAMP WITH TIME ZONE)

### 2.8 `tasks`
- `id` (UUID, Primary Key)
- `project_id` (UUID, Foreign Key -> `projects.id`)
- `title` (VARCHAR(255))
- `prompt` (TEXT, Not Null)
- `status` (VARCHAR(64)) -- 'pending_approval', 'running', 'completed', 'failed'
- `plan_json` (JSONB)
- `created_at` (TIMESTAMP WITH TIME ZONE)

### 2.9 `agent_runs`
- `id` (UUID, Primary Key)
- `task_id` (UUID, Foreign Key -> `tasks.id`)
- `status` (VARCHAR(64))
- `iterations` (INTEGER, Default 0)
- `diff_content` (TEXT)
- `started_at` (TIMESTAMP WITH TIME ZONE)
- `completed_at` (TIMESTAMP WITH TIME ZONE)

### 2.10 `tool_calls`
- `id` (UUID, Primary Key)
- `agent_run_id` (UUID, Foreign Key -> `agent_runs.id`)
- `tool_name` (VARCHAR(128), Not Null)
- `arguments` (JSONB, Not Null)
- `result` (TEXT)
- `is_error` (BOOLEAN, Default False)
- `duration_ms` (INTEGER)
- `executed_at` (TIMESTAMP WITH TIME ZONE)

### 2.11 `test_runs`
- `id` (UUID, Primary Key)
- `project_id` (UUID, Foreign Key -> `projects.id`)
- `command` (VARCHAR(255), Not Null)
- `passed` (BOOLEAN, Not Null)
- `output` (TEXT)
- `duration_seconds` (FLOAT)
- `created_at` (TIMESTAMP WITH TIME ZONE)

### 2.12 `git_commits`
- `id` (UUID, Primary Key)
- `project_id` (UUID, Foreign Key -> `projects.id`)
- `commit_hash` (VARCHAR(64), Not Null)
- `message` (TEXT, Not Null)
- `author` (VARCHAR(255))
- `committed_at` (TIMESTAMP WITH TIME ZONE)
