# STACKPILOT — Build Progress Tracker

This document tracks progress across all 17 phases defined in Section 8 of the **STACKPILOT Full Build Specification**.

---

## Phased Development Status

| Phase | Description | Status | Completion Date | Notes |
|:---|:---|:---:|:---:|:---|
| **Phase 1** | **Project Setup**: repo, frontend scaffold, backend scaffold, PostgreSQL config, env vars, base project structure, Docker config | 🟢 Completed | 2026-09-23 | FastAPI backend verified (pytest passed), Next.js frontend built & running, SQLite/pgvector DB engine ready, Docker configs & full 11-part documentation suite initialized |
| **Phase 2** | **UI**: login, dashboard, project creation, project explorer, code editor, AI chat panel (3-pane layout: Files \| Editor \| AI Chat) | 🟡 Ready to Build | — | Target: 3-pane layout, Monaco Editor, reactive chat interface |
| **Phase 3** | **Project Upload / Git Import**: upload, create project, Git import, file storage, explorer wiring | ⚪ Planned | — | Project workspace management & file hierarchy |
| **Phase 4** | **Codebase Indexing**: scanner, filtering, AST parser, semantic chunking, embeddings, vector storage | ⚪ Planned | — | Tree-sitter AST extraction & pgvector chunk persistence |
| **Phase 5** | **RAG**: embed query → vector search → relevant chunks → context builder → LLM → grounded answer | ⚪ Planned | — | Provider-agnostic retrieval pipeline |
| **Phase 6** | **AI Chat**: wire RAG into chat, conversation history, streaming responses, file/code references | ⚪ Planned | — | Streaming WebSocket/SSE with citation cards |
| **Phase 7** | **AI Planning**: agent produces numbered task decomposition plan before acting | ⚪ Planned | — | Implementation planner with user review gate |
| **Phase 8** | **Tool Calling**: implement and wire all 12 controlled tools, log calls & results | ⚪ Planned | — | `read_file`, `search_code`, `modify_file`, `run_tests`, etc. |
| **Phase 9** | **Code Modification**: multi-file edits, unified diff generation, accept/reject UI, rollback | ⚪ Planned | — | Multi-file transaction & rollback support |
| **Phase 10** | **Test Generation**: generate unit tests for selected function/service based on code behavior | ⚪ Planned | — | Automatic test suite creation (pytest / jest) |
| **Phase 11** | **Sandbox Execution**: Docker-based safe command runner (`npm test`, `pytest`, `npm run lint`) | ⚪ Planned | — | Command validation & resource-capped execution |
| **Phase 12** | **Automated Debugging**: error → stack trace → context retrieval → fix → test → retry loop | ⚪ Planned | — | Hard-capped recursive self-healing loop |
| **Phase 13** | **Code Review**: structured findings (bugs, security, perf, quality, maintainability, testing gaps) | ⚪ Planned | — | Static & LLM-driven structured code audit |
| **Phase 14** | **Git Integration**: status, diff, branch, commit, push (push requires explicit approval gate) | ⚪ Planned | — | Safe VCS operations with approval workflow |
| **Phase 15** | **Documentation Generation**: README, API docs, architecture explanation, function docs | ⚪ Planned | — | Automatic Markdown & docstring synthesis |
| **Phase 16** | **Auth & Security**: user auth, project isolation, API tokens, secret masking, rate limiting | ⚪ Planned | — | JWT/OAuth with zero-secret exposure to LLMs |
| **Phase 17** | **Testing & Validation**: unit, integration, and end-to-end test suites | ⚪ Planned | — | Comprehensive automated test validation |

---

## Acceptance Checklist Tracking (Section 15)

- [ ] Project creation, repo upload, file explorer, code editor all work
- [ ] AI chat + RAG work and are grounded in actual project context
- [ ] AI can generate code and create implementation plans
- [ ] Tools work: read/modify files, run tests, analyze errors
- [ ] Diff viewer + user approval flow work
- [ ] Git integration (status/diff/commit) works
- [ ] Documentation generation works
- [ ] Code executes only in sandbox; secrets protected; permissions and resource limits enforced
- [ ] Production build, database, API, and frontend all work
