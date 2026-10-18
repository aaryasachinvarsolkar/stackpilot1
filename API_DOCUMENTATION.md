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

## 2. Projects & Workspace (`/api/projects`)

### `GET /api/projects`
List all registered projects for the active user.

### `POST /api/projects`
Create a new project.
- **Request Body**:
```json
{
  "name": "my-saas-app",
  "description": "Production SaaS application",
  "path": "/workspace/projects/my-saas-app"
}
```

### `GET /api/projects/{id}`
Retrieve project details, metadata, and index status.

### `POST /api/projects/{id}/upload`
Upload a project zip/tar archive to initialize workspace files.

### `POST /api/projects/{id}/index`
Trigger background AST parsing, semantic chunking, and vector embedding generation.

---

## 3. Files & Code Navigation (`/api/files`)

### `GET /api/files/tree?project_id={id}`
Retrieve hierarchical directory tree for the project, excluding ignored patterns.

### `POST /api/files/read`
Read file content and line range.
- **Request Body**:
```json
{
  "project_id": "proj_123",
  "file_path": "src/controllers/auth.ts",
  "start_line": 1,
  "end_line": 100
}
```

### `POST /api/files/write`
Save changes directly to a file (or create if non-existent).

---

## 4. AI Chat & RAG Retrieval (`/api/chat`)

### `POST /api/chat`
Ask a question or initiate discussion grounded in the codebase.
- **Request Body**:
```json
{
  "project_id": "proj_123",
  "message": "Where is user JWT token validation implemented?",
  "conversation_id": "conv_456"
}
```
- **Response**: Streamed SSE or JSON containing message explanation and citation array (`file_path`, `function_name`, `line_numbers`).

---

## 5. Agent Orchestrator & Task Execution (`/api/agent`)

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

## 6. Execution & Sandbox (`/api/sandbox`)

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

## 7. Version Control (`/api/git`)

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
