# STACKPILOT — Project Requirements Document

## 1. Executive Summary
STACKPILOT is an AI-powered software development assistant platform designed to automate and augment complex engineering workflows. Unlike conventional autocomplete tools, STACKPILOT provides codebase-aware retrieval (RAG), abstract syntax tree (AST) semantic parsing, agentic task planning, multi-file code editing with interactive diff reviews, sandboxed testing, and Git operations.

## 2. Target Users
- **Software Engineers / Full-Stack Developers**: Require multi-file modifications and deep codebase understanding.
- **Students & Junior Developers**: Benefit from architecture explanations, automated debugging, and test generation.
- **DevOps / Platform Engineers**: Automate script refactoring, linting, build pipelines, and safe Git workflows.

## 3. Functional Requirements

### FR-01: Project Workspace Management
- Ability to create or open local projects, upload archives (.zip, .tar.gz), or clone remote Git repositories.
- File explorer displaying directory trees with exclusion filters (`node_modules/`, `.git/`, `dist/`, `build/`, `.cache/`).
- Full code editing interface with syntax highlighting, search, and file tabs.

### FR-02: Codebase Indexing & AST Parsing
- Recursive scanner capable of parsing supported languages (`.js`, `.ts`, `.tsx`, `.jsx`, `.py`, `.java`, `.cpp`, `.go`).
- Structural symbol extraction: functions, classes, methods, imports, exports, interfaces, type definitions.
- Semantic boundary chunking (splitting files by function/class rather than fixed character tokens).
- Dense vector embedding generation for semantic chunks.
- Persistent vector indexing in PostgreSQL + pgvector.

### FR-03: RAG-Based Retrieval Pipeline
- Query embedding generation and cosine similarity search against code chunks.
- Context compression, deduplication, and dependency ordering before prompting the LLM.
- Direct citation of source files, function signatures, and line numbers in retrieved context.

### FR-04: AI Chat & Reasoning Assistant
- Interactive conversational interface with streaming responses.
- Grounded contextual answers strictly derived from retrieved codebase fragments.
- Inline citation badges allowing instant code jump.

### FR-05: AI Task Planner & Agent Orchestrator
- Autonomous task decomposition: decomposes complex prompts into numbered, executable task plans.
- Human-in-the-loop review gate: user must approve or modify the plan before tool execution commences.

### FR-06: Controlled Tool Calling
- Controlled tool interface exposing:
  `read_file`, `search_code`, `list_files`, `create_file`, `modify_file`, `delete_file`, `run_tests`, `run_linter`, `run_build`, `git_diff`, `git_status`, `git_commit`.
- Complete execution audit log for every tool invocation, arguments, and return payload.

### FR-07: Multi-File Code Modification & Diff Review
- Support transactional code edits spanning multiple coupled files.
- Unified Git diff viewer showing side-by-side or unified additions/deletions.
- Explicit Accept / Reject / Rollback UI controls.

### FR-08: Sandboxed Execution & Testing
- Execution of commands (`npm test`, `npm run build`, `npm run lint`, `pytest`, `mvn test`) isolated within Docker containers.
- Strict timeout and resource limits (CPU, memory, disk I/O, network).

### FR-09: Automated Debugging & Self-Healing Loop
- Stack trace parsing (error type, offending file, line number, root cause).
- Targeted context retrieval for failing components.
- Automated hypothesis generation, patch application in a temporary staging area, and test re-execution.
- Hard retry cap (default max 3 attempts) to prevent runaway execution.

### FR-10: Version Control & Git Operations
- Git repository status, diff, branch creation, commit creation, and log inspection.
- Sensitive operations (e.g. `git push origin main`) require mandatory interactive user approval.

## 4. Non-Functional Requirements

### NFR-01: Performance & Latency
- Vector retrieval latency < 250ms for repos up to 100k lines of code.
- File tree navigation and search response < 100ms.
- Streaming LLM token delivery begins within 1.5 seconds.

### NFR-02: Security & Isolation
- Zero host system execution for arbitrary dev commands.
- Zero secret leakage: API keys, database credentials, and Git tokens are never sent to LLMs or written to external logs.
- Per-project and per-user storage isolation.

### NFR-03: Extensibility & Agnosticism
- Provider-agnostic LLM interface supporting OpenAI, Anthropic, Gemini, local Ollama, and test mocks.
- Database layer supporting both PostgreSQL+pgvector and SQLite for zero-dependency local development.
