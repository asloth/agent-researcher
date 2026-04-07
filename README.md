# Agent Researcher

An autonomous research agent built with **LangGraph**, **FastAPI**, and **React**. It uses an **Orchestrator-Workers** architecture where a planner decomposes questions into research angles, dispatches parallel worker agents with tool access, and synthesizes findings into a cited response.

Inspired by Anthropic's [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents).

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (React)                           │
│   Projects  |  Chat (SSE streaming)  |  Memory  |  Docs  | Chunks  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTP / SSE
┌──────────────────────────────▼──────────────────────────────────────┐
│                        FASTAPI BACKEND                              │
│                                                                     │
│  /api/chat/stream    /api/projects    /api/hechos    /api/documents │
│         │                                                           │
│         ▼                                                           │
│  ┌─────────────────── LangGraph StateGraph ───────────────────┐    │
│  │                                                             │    │
│  │   START                                                     │    │
│  │     │                                                       │    │
│  │     ▼                                                       │    │
│  │  ┌──────────┐  no research   ┌─────┐                       │    │
│  │  │ PLANNER  │───────────────►│ END │                       │    │
│  │  └──────────┘                └─────┘                       │    │
│  │     │ needs research                                        │    │
│  │     │ (3-5 angles)                                          │    │
│  │     │                                                       │    │
│  │     ▼  Send() fan-out                                       │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐                   │    │
│  │  │ WORKER 1 │ │ WORKER 2 │ │ WORKER N │  (parallel)       │    │
│  │  │          │ │          │ │          │                     │    │
│  │  │ ┌──────┐ │ │ ┌──────┐ │ │ ┌──────┐ │                   │    │
│  │  │ │ LLM  │◄┼─┼─┤Tools │ │ │ │ ...  │ │  each worker:     │    │
│  │  │ │      ├─┼─┼─►      │ │ │ │      │ │  chatbot ⇄ tools  │    │
│  │  │ └──────┘ │ │ └──────┘ │ │ └──────┘ │  (max 6 loops)    │    │
│  │  └─────┬────┘ └─────┬────┘ └─────┬────┘                   │    │
│  │        └────────────┼────────────┘                          │    │
│  │                     ▼  fan-in                               │    │
│  │              ┌──────────────┐                               │    │
│  │              │ SYNTHESIZER  │                               │    │
│  │              │ (cites all)  │                               │    │
│  │              └──────┬───────┘                               │    │
│  │                     ▼                                       │    │
│  │                  ┌─────┐                                    │    │
│  │                  │ END │                                    │    │
│  │                  └─────┘                                    │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  MCP Client ◄──── stdio ────► MCP Server (hechos/memory)           │
│                                 │                                   │
│                                 ▼                                   │
│                         ┌──────────────┐                           │
│                         │   LanceDB    │                           │
│                         │  (embedded)  │                           │
│                         │              │                           │
│                         │ - hechos     │  semantic memory          │
│                         │ - pdf_chunks │  indexed documents        │
│                         └──────────────┘                           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Graph Nodes

### Planner

Receives the user message and decides the routing strategy using structured output:

```python
class PlannerOutput(BaseModel):
    needs_research: bool        # research required?
    angles: list[str]           # 3-5 investigation angles
    direct_response: str | None # answer directly if no research needed
```

- If `needs_research=True` → emits `research_angles` and fans out to workers
- If `needs_research=False` → returns `direct_response` and goes to `END`
- Model: `gpt-5.4-nano` (temperature 0.2)

### Research Workers (Subgraph)

Each worker is a **full ReAct agent** — an LLM with tool access that loops until it has enough information or hits the iteration limit.

```
START → chatbot → [has tool_calls?] → tool_node → chatbot → ...
                  [no tool_calls]   → collect_result → END
```

- Model: `gpt-5.4-nano` (temperature 0.0)
- Safety: max 6 tool-call iterations per worker
- Output: `WorkerResult` with findings, sources, and tool history
- Dispatched in parallel via LangGraph's `Send()` primitive

### Synthesizer

Receives all worker results for the current turn, formats them by angle, and produces a final cited response in Spanish.

- Model: `gpt-5.4` (temperature 0.2)
- Only processes current turn's results (not accumulated from prior turns)

---

## State Definitions

```python
class WorkerState(TypedDict):
    messages: Annotated[list, add_messages]  # worker conversation
    angle: str                                # assigned research angle
    iteration_count: int                      # loop safety counter

class WorkerResult(TypedDict):
    angle: str              # the research angle
    findings: str           # research output text
    sources: list[str]      # cited URLs
    tool_history: list[dict] # tools invoked

class OverallState(TypedDict):
    messages: Annotated[list, add_messages]                       # conversation history
    research_angles: list[str]                                     # current turn's angles
    worker_results: Annotated[list[WorkerResult], operator.add]   # accumulates via reducer
```

`worker_results` uses `operator.add` as a reducer so each worker's output appends to the list. The synthesizer reads only the last N entries (where N = number of current angles).

---

## Tools

Workers have access to five tools for gathering information:

| Tool | Description | Key Behavior |
|---|---|---|
| `search_web(query)` | Web search via Tavily API | Returns up to 10 results with URLs and snippets |
| `process_pdf(url)` | Download, chunk, and index a PDF | Splits into ~3200 char chunks, embeds with OpenAI, stores in LanceDB. Returns structural map. Caches in `pdf_index.json` to avoid reprocessing |
| `scrape_web(urls, query)` | Extract and summarize web pages | Auto-routes PDF URLs to `process_pdf`. Summarizes HTML content with gpt-4o-mini |
| `rag_pdf_local(url, query)` | Semantic search within an indexed PDF | Top 5 chunks by cosine similarity, filtered by source URL and project |
| `list_indexed_pdfs()` | Show all previously processed PDFs | Reads from `pdf_index.json` cache |

Tools that modify the vector database (`process_pdf`, `rag_pdf_local`) receive `project_id` via LangGraph's `RunnableConfig` injection to ensure data isolation between projects.

---

## MCP Server (Semantic Memory)

A separate **Model Context Protocol** server (`mcp_hechos/server.py`) manages the agent's long-term memory. It runs as a subprocess connected via **stdio**.

| MCP Tool | Purpose |
|---|---|
| `guardar_si_es_hecho(texto, project_id)` | Store a fact/statement as a vector embedding |
| `search_best_hecho(query, project_id)` | Find the single most relevant stored fact |
| `rag_hechos(query, project_id)` | Retrieve top 5 facts as RAG context |
| `rag_pdf(url, query, chunk_range, project_id)` | Query indexed PDF chunks (semantic search or direct range access) |

The MCP server uses **LanceDB** (embedded) with **OpenAI embeddings** (`text-embedding-3-small`, 1536 dimensions). The FastAPI backend manages the MCP connection lifecycle via an async context manager.

---

## API Endpoints

### Chat

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat` | Single request/response chat turn |
| `POST` | `/api/chat/stream` | SSE streaming with real-time progress |

**SSE event types** for `/api/chat/stream`:

```
{"type": "planner",     "angles": [...]}          # planner decided to research
{"type": "direct",      "content": "..."}         # planner answered directly
{"type": "worker_done", "angle": "...", ...}      # a worker finished
{"type": "token",       "text": "..."}            # synthesizer streaming token
{"type": "done"}                                   # graph complete
{"type": "error",       "message": "..."}         # something failed
```

### Projects

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects` | List all projects |
| `POST` | `/api/projects` | Create project (generates 12-char UUID) |
| `DELETE` | `/api/projects/{id}` | Delete project |

### Knowledge

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/hechos?project_id=` | List stored facts/memories |
| `GET` | `/api/pdf-chunks?project_id=` | List indexed PDF chunks |
| `GET` | `/api/documents?project_id=` | List documents with chunk counts |
| `GET` | `/api/documents/download/{filename}` | Download a stored PDF |

All knowledge endpoints filter by `project_id` (defaults to `"default"`).

---

## Data Model

### LanceDB Tables

**`hechos`** — semantic memory

| Column | Type | Description |
|---|---|---|
| `texto` | string | The stored fact |
| `vector` | float[1536] | OpenAI embedding |
| `fecha` | string | Timestamp |
| `project_id` | string | Project isolation key |

**`pdf_chunks`** — indexed document content

| Column | Type | Description |
|---|---|---|
| `texto` | string | Chunk text (~3200 chars) |
| `vector` | float[1536] | OpenAI embedding |
| `source_url` | string | Original PDF URL |
| `page` | int | Page number (1-indexed) |
| `chunk_index` | int | Sequential chunk ID |
| `fecha` | string | Timestamp |
| `project_id` | string | Project isolation key |

---

## Project Structure

```
agent-researcher/
├── agente_langgraph/           # Backend + Agent engine
│   ├── agente.py               # Main LangGraph StateGraph (planner → workers → synthesizer)
│   ├── worker.py               # Worker subgraph (ReAct loop with tools)
│   ├── state.py                # State type definitions
│   ├── local_tools.py          # search_web, process_pdf, scrape_web, rag_pdf_local
│   ├── api.py                  # FastAPI endpoints (REST + SSE)
│   ├── mcp_client.py           # MCP connection lifecycle + wrapper functions
│   ├── projects.py             # Project CRUD (JSON file storage)
│   ├── papers/                 # Downloaded PDFs
│   └── .env                    # API keys (OPENAI_API_KEY, TAVILY_API_KEY)
│
├── mcp_hechos/                 # MCP Server (subprocess)
│   ├── server.py               # FastMCP server with 4 tools
│   └── hechos_lancedb/         # LanceDB data directory
│
├── front_agente/               # React frontend
│   ├── src/App.tsx             # Main SPA component (chat, memory, docs, chunks tabs)
│   └── package.json            # React 19 + Vite 7 + react-markdown
│
├── projects.json               # Persistent project list
├── pyproject.toml              # Python dependencies
└── .python-version             # Python 3.14
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent Framework | LangGraph (StateGraph, Send, ToolNode, MemorySaver) |
| LLMs | OpenAI GPT-5.4 / GPT-5.4-nano (via langchain-openai) |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims) |
| Vector Database | LanceDB (embedded, no server required) |
| Tool Protocol | MCP (Model Context Protocol) via stdio |
| Backend API | FastAPI + Uvicorn |
| Web Search | Tavily API |
| PDF Parsing | pymupdf4llm (with pymupdf fallback) |
| Web Scraping | trafilatura |
| Frontend | React 19 + TypeScript + Vite 7 |
| Streaming | Server-Sent Events (SSE) |

---

## Getting Started

### Prerequisites

- [Python 3.14+](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (recommended) or pip
- [Node.js 18+](https://nodejs.org/) and npm
- [OpenAI API key](https://platform.openai.com/api-keys)
- [Tavily API key](https://tavily.com/) (for web search)

### Step 1 — Clone the repository

```bash
git clone https://github.com/<your-user>/agent-researcher.git
cd agent-researcher
```

### Step 2 — Install Python dependencies

```bash
uv sync
```

This creates the `.venv` virtual environment and installs all dependencies from `pyproject.toml`.

> If you don't use `uv`, you can do it manually:
> ```bash
> python3.14 -m venv .venv
> source .venv/bin/activate
> pip install -e .
> ```

### Step 3 — Configure environment variables

```bash
cp agente_langgraph/.env.example agente_langgraph/.env
```

Edit `agente_langgraph/.env` and add your keys:

```env
OPENAI_API_KEY="sk-..."
TAVILY_API_KEY="tvly-..."
```

### Step 4 — Install frontend dependencies

```bash
cd front_agente
npm install
cd ..
```

### Step 5 — Start the backend

```bash
cd agente_langgraph
uv run uvicorn api:app --reload
```

The FastAPI server starts at `http://localhost:8000` and automatically spawns the MCP subprocess for semantic memory.

> If you activated the venv manually instead of using `uv`, just run:
> ```bash
> uvicorn api:app --reload
> ```

### Step 6 — Start the frontend (new terminal)

```bash
cd front_agente
npm run dev
```

The React app starts at `http://localhost:5173`.

### Step 7 — Use the app

1. Open `http://localhost:5173` in your browser
2. Create a new project using the top bar
3. Type a research question in the chat
4. Watch the agent plan research angles, dispatch parallel workers, and stream the synthesized answer
5. Browse the **Memory**, **Docs**, and **Chunks** tabs to inspect stored facts and indexed documents

---

## Design Decisions

**Orchestrator-Workers over linear workflow** — The planner decides *if* and *how* to research. Workers run in parallel with independent tool access. This follows Anthropic's distinction between agents (LLM-directed) and workflows (code-directed).

**Fan-out/Fan-in via `Send()`** — Each research angle spawns an independent subgraph. Workers don't share state, preventing cross-contamination of findings. Results merge at the synthesizer.

**Embedded vector DB** — LanceDB runs in-process with no server to manage. Good enough for single-user research and keeps deployment simple.

**MCP for memory** — Separating memory operations into an MCP server makes the memory layer swappable and protocol-compliant, even though it currently runs as a local subprocess.

**Streaming-first UI** — SSE events let the frontend show each phase (planning, worker progress, synthesis) as it happens, rather than waiting for the full graph to complete.

**Project isolation** — Every piece of data (chunks, facts, conversation threads) is tagged with `project_id`, so multiple research projects don't bleed into each other.

---

## License

MIT
