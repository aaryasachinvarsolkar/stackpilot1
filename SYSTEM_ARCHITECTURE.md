# STACKPILOT — System Architecture

## 1. High-Level Architecture

STACKPILOT is organized around a clean client-server architecture with specialized micro-layers handling AI orchestration, codebase indexing, vector retrieval, and sandboxed execution:

```
┌─────────────────────────────────────────────────────────────┐
│                      USER WEB BROWSER                       │
│      Next.js 14+ / React Frontend (3-Pane Workspace)        │
│  [File Explorer]  │  [Monaco Code Editor]  │  [AI Chat/Plan]│
└──────────────────────────────┬──────────────────────────────┘
                               │ REST / WebSocket (SSE)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   BACKEND API (FastAPI)                     │
│  ├── API Routes (/projects, /chat, /agent, /files, /git)    │
│  ├── Auth & Session Middleware                              │
│  └── Background Task Queue (Indexing, Testing)              │
└──────┬───────────────────────┬───────────────────────┬──────┘
       │                       │                       │
       ▼                       ▼                       ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│ CODEBASE      │      │ AI AGENT      │      │ EXECUTION     │
│ ENGINE        │      │ ORCHESTRATOR  │      │ SANDBOX       │
│ - AST Parser  │      │ - Planner     │      │ - Docker      │
│ - Chunking    │      │ - RAG Engine  │      │ - Resource    │
│ - Embedder    │      │ - Tool Calling│      │   Limits      │
│ - pgvector DB │      │ - LLM Provider│      │ - Test Runner │
└───────────────┘      └───────────────┘      └───────────────┘
```

## 2. Core Subsystems

### 2.1 Web Application (Frontend)
- **Framework**: Next.js App Router with TypeScript and Tailwind CSS.
- **Design System**: Slate/Dark-mode theme, glassmorphic panels, glowing semantic badges, responsive 3-pane layout (`Files | Monaco Editor | AI Chat`).
- **State Management**: React hooks for active project, open file tabs, streaming chat messages, diff reviews, and execution logs.
- **Editor**: Monaco Editor with language servers, syntax highlighting, diff viewing (`monaco-editor` diff mode), and breakpoint hooks.

### 2.2 Backend Service (FastAPI)
- **Framework**: Python 3.13 with FastAPI and AsyncIO.
- **Database Layer**: SQLAlchemy 2.0 async engine supporting:
  - PostgreSQL 16 with `pgvector` for production environments.
  - SQLite with `aiosqlite` for lightweight, zero-dependency local development and CI testing.
- **Communication Protocols**:
  - REST endpoints for CRUD operations (projects, files, configurations, git status).
  - WebSocket / SSE for real-time agent thought streaming, token generation, and command output feeds.

### 2.3 Codebase Engine & RAG Pipeline
```
Raw Project Files
       │
       ▼
 [File Scanner & Exclusions (.git, node_modules)]
       │
       ▼
 [Tree-sitter / AST Language Parsers]
  Extract: classes, functions, methods, imports, signatures
       │
       ▼
 [Semantic Boundary Chunker]
  Chunks structured strictly per symbol/scope
       │
       ▼
 [Dense Embedding Provider]
  Generate 1536-dim or 384-dim chunk vectors
       │
       ▼
 [PostgreSQL + pgvector / Vector DB]
  HNSW / IVFFlat Index on embedding column
```

### 2.4 Agent Workflow & Tool Execution
```
User Prompt
     │
     ▼
[Task Analyzer] ──> Analyzes intent (question, refactor, bugfix, feature)
     │
     ▼
[Task Planner] ────> Generates numbered step-by-step implementation plan
     │
     ▼
[User Approval Gate] ─── (User reviews & approves / edits plan)
     │
     ▼
[Context Retrieval] ───> RAG semantic search over code chunks
     │
     ▼
[LLM Tool Loop] ───────> Calls tools:
                         • read_file
                         • search_code
                         • modify_file
                         • run_tests (in Docker Sandbox)
     │
     ▼
[Result Evaluation]
     ├── Tests Pass ──> Generate Unified Diff ──> User Review & Commit
     └── Tests Fail ──> Invoke Automated Debugger (capped max 3 retries)
```

### 2.5 Sandboxed Execution Environment
All arbitrary command runs (`npm test`, `pytest`, `npm run build`) are dispatched through the sandbox runner:
- Strict containment inside non-privileged Docker containers.
- Enforced RAM limits (e.g. 512MB default) and CPU limits (e.g. 1.0 CPU cores).
- Configurable execution timeout (default 60 seconds).
- Host root filesystem and sensitive environment credentials completely excluded from container mounting.
