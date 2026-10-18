# STACKPILOT — AI Architecture & Agent Design

## 1. Principles
STACKPILOT rejects the naive `User -> LLM -> Code` paradigm. Codebases are complex, highly interconnected graphs of logic and state. STACKPILOT enforces:

`User Prompt -> Task Planner -> Codebase RAG -> AI Agent -> {Read/Write/Test Tools} -> Result Check -> {Pass -> Review | Fail -> Debug Loop} -> User Approval -> Git`

---

## 2. Core Subsystems

### 2.1 Codebase Parser & Semantic Indexer
- **AST Parsing**: Employs Tree-sitter parsers for TypeScript, JavaScript, Python, Java, Go, and C++.
- **Semantic Chunking**: Instead of arbitrary token slicing, chunks are aligned with AST nodes:
  - Functions & async routines
  - Classes, interfaces, traits
  - Structs & type definitions
  - Module exports & dependency maps
- **Metadata Tagging**: Each chunk carries line numbers, symbol name, parameter list, and import dependencies.

### 2.2 Retrieval-Augmented Generation (RAG)
- **Vector Search**: Embeds user query and runs cosine distance queries over `code_chunks` via `pgvector`.
- **Context Ranking & Compression**:
  - Drops irrelevant imports/boilerplate.
  - Sorts chunks by semantic relevance and topological call order.
  - Keeps total context tokens bounded within LLM prompt limits.
- **Project Memory**: Injects project metadata (framework, package manager, test runner, styling library) to eliminate redundant queries.

### 2.3 Agent Orchestration Loop
The central agent orchestrator operates on a state-machine loop:
1. **Analyze**: Categorizes prompt into intent (Exploration, Refactor, Feature, Fix).
2. **Plan**: Formulates a clear, numbered plan of action.
3. **Approval Gate**: In interactive mode, presents the plan to the user for explicit confirmation.
4. **Tool Execution**: Selects and calls controlled tools sequentially:
   - `read_file`
   - `search_code`
   - `list_files`
   - `create_file`
   - `modify_file`
   - `delete_file`
   - `run_tests`
   - `run_linter`
   - `run_build`
   - `git_diff`
   - `git_status`
   - `git_commit`
5. **Validation**: Runs sandbox test or build verification.
6. **Automated Self-Healing**: If tests fail, captures error trace, retrieves relevant code, formulates a fix, applies change, and re-runs test (max 3 retry cycles).
7. **Diff Presentation**: Generates unified diff and requests user approval before staging Git commit.

---

## 3. Provider-Agnostic LLM Layer
The AI interface abstracts model providers behind a unified asynchronous client:
```python
class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str = "") -> str: ...
    
    @abstractmethod
    async def generate_stream(self, prompt: str, system_prompt: str = "") -> AsyncIterator[str]: ...
    
    @abstractmethod
    async def call_tools(self, prompt: str, tools: list[dict], system_prompt: str = "") -> ToolCallResponse: ...
```
Implemented providers:
- `OpenAIProvider` (`gpt-4o`, `gpt-4o-mini`, etc.)
- `AnthropicProvider` (`claude-3-5-sonnet`, etc.)
- `GeminiProvider` (`gemini-1.5-pro`, `gemini-1.5-flash`, etc.)
- `MockProvider` (Deterministic responses for unit testing and offline development)
