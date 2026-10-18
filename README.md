# STACKPILOT

> **AI-Powered Software Development Assistant**
> A unified platform combining AST codebase understanding, RAG retrieval, agentic planning, controlled tool execution, and sandboxed testing with human-in-the-loop approval.

---

## 🌟 Overview

Existing AI coding assistants focus mostly on chat-based autocomplete or isolated code generation. Developers must still manually navigate large codebases, discover dependencies, construct mental context, edit multiple related files, execute tests, debug runtime failures, and manage Git operations.

**STACKPILOT** unifies the entire engineering lifecycle into an autonomous, tool-calling agentic workflow:

```
USER REQUEST 
  → Task Analyzer 
  → Task Planner 
  → Codebase RAG 
  → AI Agent 
  → {Read / Modify / Test Code} 
  → Result Check 
  → {Pass → Review | Fail → Debug Loop} 
  → User Approval 
  → Git
```

---

## 🛠️ Architecture & Tech Stack

| Component | Technology |
|:---|:---|
| **Frontend** | Next.js 14+ / React, TypeScript, Tailwind CSS |
| **Code Editor** | Monaco Editor |
| **Backend API** | Python 3.13 + FastAPI, Pydantic, SQLAlchemy Async |
| **Database** | PostgreSQL 16 + `pgvector` (with SQLite fallback for lightweight dev) |
| **AI Layer** | Provider-agnostic LLM interface (OpenAI, Anthropic, Gemini, Mock) |
| **Code Parser** | Tree-sitter / AST semantic chunking |
| **Execution Sandbox** | Docker containerized runner (`npm test`, `pytest`, `npm run build`) |
| **Version Control** | Git service with approval gates |

---

## 📂 Repository Structure

```
stackpilot/
├── backend/
│   ├── app/
│   │   ├── api/             # FastAPI REST & WebSocket routers
│   │   ├── agents/          # Agent orchestrator & implementation planners
│   │   ├── rag/             # Vector retrieval & context compression
│   │   ├── code_parser/     # AST language parsers & semantic chunker
│   │   ├── tools/           # Controlled tool registry
│   │   ├── database/        # Async DB connection & session managers
│   │   ├── models/          # SQLAlchemy relational models
│   │   ├── services/        # Business logic & services
│   │   ├── config.py        # Pydantic settings
│   │   └── main.py          # FastAPI application entrypoint
│   ├── tests/               # Pytest suite
│   ├── Dockerfile           # Backend container
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── app/                 # Next.js App Router (Layouts & Pages)
│   ├── components/          # Reusable UI elements (Navbar, Badges, Cards)
│   ├── editor/              # Monaco Editor integration
│   ├── chat/                # AI Chat & Citation components
│   ├── project/             # File Explorer & Project Manager
│   ├── services/            # API client service
│   ├── hooks/               # Custom React hooks
│   ├── lib/                 # Utility helpers
│   ├── Dockerfile           # Frontend container
│   └── package.json         # Frontend dependencies
├── docker-compose.yml       # Multi-service stack (DB, Backend, Frontend)
├── PROGRESS.md              # Phased build progression tracking
└── README.md                # Project documentation
```

---

## 🚀 Quickstart

### Prerequisites
- Node.js v18+ (Node 24 recommended)
- Python 3.11+ (Python 3.13 recommended)
- Docker & Docker Compose (optional for local SQLite mode)

### 1. Clone & Configure
```bash
cp .env.example .env
```

### 2. Run Backend
```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Backend runs at `http://localhost:8000`. API docs available at `http://localhost:8000/docs`.

### 3. Run Frontend
```bash
cd frontend
npm install
npm run dev
```
Frontend runs at `http://localhost:3000`.

### 4. Run via Docker Compose
```bash
docker-compose up --build
```

---

## 📜 Documentation Reference
- [PROGRESS.md](PROGRESS.md) — Phased Roadmap & Progress
- [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) — Architectural Design & Data Flow
- [PROJECT_REQUIREMENTS.md](PROJECT_REQUIREMENTS.md) — Functional Specifications
- [API_DOCUMENTATION.md](API_DOCUMENTATION.md) — REST & WebSocket Endpoints
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) — Relational Models & pgvector Schemas
- [AI_ARCHITECTURE.md](AI_ARCHITECTURE.md) — Agent Loops, AST Parser, RAG Specs
- [SECURITY.md](SECURITY.md) — Sandboxing, Isolation, and Secret Controls
- [TESTING.md](TESTING.md) — Unit, Integration, and E2E Testing Strategy
- [DEPLOYMENT.md](DEPLOYMENT.md) — Production Deployment Guides
- [USER_GUIDE.md](USER_GUIDE.md) — End-User Handbook
