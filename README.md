# Agent Researcher

![Python](https://img.shields.io/badge/Python_3.14-3776AB?style=flat&logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?style=flat&logo=langchain&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React_19-61DAFB?style=flat&logo=react&logoColor=black)
![LanceDB](https://img.shields.io/badge/LanceDB-embedded-FF6B6B?style=flat)
![MCP](https://img.shields.io/badge/MCP-stdio-7B61FF?style=flat)

A research assistant you run locally. You ask a question; it splits the question into research angles (typically 3–5), sends one worker agent after each angle in parallel (web search, page scraping, PDF indexing), and merges what they found into one answer with source links. Research is grouped into projects, and each project keeps its own chats, remembered facts and indexed PDFs.

Built with **LangGraph** (planner → parallel workers → synthesizer), **FastAPI** with Server-Sent Events, **React**, and **LanceDB**. The design follows the Orchestrator-Workers pattern from Anthropic's [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents).

> **Language:** the prompts are written in Spanish and the synthesizer is told to answer in Spanish. You can ask in any language; researched answers come back in Spanish.

## How a question gets answered

```
question ─► PLANNER ──(already known / small talk)──► direct answer
               │
               └─(needs research: typically 3-5 angles)
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
       WORKER 1   WORKER 2   WORKER N     each: LLM ⇄ tools, up to 6 steps
          └──────────┼──────────┘         (search_web, scrape_web, process_pdf,
                     ▼                     rag_pdf_local, list_indexed_pdfs)
               SYNTHESIZER ──► answer with sources, streamed token by token
                     │
                     ▼
                MEMORY NODE ──► saves durable facts for this project
```

1. **Planner** reads the chat history and the project's saved facts. If the answer is already there, or the message is small talk, it replies directly. Otherwise it returns a list of research angles. Its prompt asks for 3–5; the output schema doesn't enforce a count.
2. **Workers** run in parallel, one per angle. Each one searches the web with Tavily, summarizes pages, and downloads and indexes PDFs so it can search inside them.
3. **Synthesizer** combines the workers' findings and sources into one cited answer.
4. **Memory node** decides whether the exchange contains a lasting fact (a goal, a constraint, something about you) and stores it in the project's memory, where the planner will find it next time.

## What you see in the app

- **Projects and chats.** A top bar to create or switch projects, and a chat selector inside each project. Sending the first message creates a chat named after it. Chat history is saved and reloads when you switch back.
- **Live progress.** While a question is being researched, the reply shows a `PLAN:` row with one badge per angle. Each badge is marked done when its worker finishes, along with how many sources it cited: the `[Source: URL]` references in the worker's final answer, which can be fewer than the pages it visited. Then the final answer streams in.
- **MEMORY tab.** Facts the agent saved for the current project, newest first.
- **DOCS tab.** PDFs indexed in the current project, with their chunk count and a download link.
- **CHUNKS tab.** The raw text chunks stored for those PDFs, with page and chunk numbers.

There are no screenshots or demo recordings in the repository yet.

## Quick start

### Requirements

| Need | Version / source | Checked against |
|---|---|---|
| Python | 3.14 or newer | `requires-python = ">=3.14"` in [`pyproject.toml`](pyproject.toml), [`.python-version`](.python-version) |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | any recent version (pip also works) | [`uv.lock`](uv.lock) |
| Node.js + npm | 20.19+ or 22.12+ | `engines` of Vite 7.3 in [`front_agente/package-lock.json`](front_agente/package-lock.json) |
| [OpenAI API key](https://platform.openai.com/api-keys) | billed per use | all LLM calls and embeddings |
| [Tavily API key](https://tavily.com/) | your Tavily plan's limits apply | `search_web` tool |

### 1. Clone and install

```bash
git clone https://github.com/asloth/agent-researcher.git
cd agent-researcher
uv sync                                  # creates .venv from pyproject.toml / uv.lock
cd front_agente && npm install && cd ..
```

<details>
<summary>Without uv (pip)</summary>

Install the dependencies listed in `pyproject.toml` with pip. `pip install -e .` fails in this repo because it has no package layout for setuptools.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" \
  | pip install -r /dev/stdin
```

With this route, activate the venv in the backend terminal (`source .venv/bin/activate` from the repository root) and run `uvicorn api:app --reload` instead of `uv run uvicorn api:app --reload`.

</details>

### 2. Add your API keys

The backend and the MCP server both load `agente_langgraph/.env`. The code needs two keys:

- `OPENAI_API_KEY`: read by the OpenAI and LangChain clients (`ChatOpenAI`, `OpenAI()`) for every LLM and embedding call.
- `TAVILY_API_KEY`: read with `os.getenv("TAVILY_API_KEY")` in `agente_langgraph/local_tools.py` for `search_web`.

A template is tracked at `agente_langgraph/.env.example`. Copy it, or create the file yourself, and set both keys:

```bash
cp agente_langgraph/.env.example agente_langgraph/.env
```

```env
OPENAI_API_KEY="your-openai-key"
TAVILY_API_KEY="your-tavily-key"
```

Model names, ports and paths are set in the source files.

### 3. Run it (two terminals)

Both terminals start from the repository root (`agent-researcher/`).

```bash
# terminal 1, from the repository root: backend on http://localhost:8000
cd agente_langgraph
uv run uvicorn api:app --reload
```

The `cd agente_langgraph` step is required: the backend must run from that folder. The modules import each other by bare name (`from state import ...`), and downloaded PDFs are saved to a `papers/` folder relative to the current directory. On startup the backend also launches the MCP server (`mcp_hechos/server.py`) as a subprocess.

```bash
# terminal 2, from the repository root: frontend on http://localhost:5173
cd front_agente
npm run dev
```

### 4. First use

1. Open `http://localhost:5173`.
2. Type a name in the **Nuevo proyecto...** field to create a project, or pick one from the list.
3. Ask something that needs research, for example a comparison of two technologies or the state of a policy topic. Watch the `PLAN:` badges fill in as workers finish, then read the cited answer.
4. Tell it something about your project ("I'm writing for a non-technical audience") and open **MEMORY** to see whether it was saved.
5. If a worker found PDFs, open **DOCS** and **CHUNKS** to see what was indexed.

## Cost and limitations

**API cost.** Every researched question triggers many paid calls. As an illustration, with a typical plan of 3–5 angles: one planner call, then one worker per angle, each making up to 6 LLM calls (the worker loop limit in `worker.py`) plus whatever Tavily searches (`search_depth="advanced"`) it decides to run, one summary call per scraped web page, embedding calls for every indexed PDF, one synthesizer call and one memory call. The number of angles is set by the planner's prompt and is not capped in code, so a question can fan out to more workers and cost more. A direct answer costs much less: the planner call, the memory call and a few embedding calls. The code uses these OpenAI models, so your key needs access to them:

| Where | Model |
|---|---|
| Planner, memory node | `gpt-5.4-mini` |
| Research workers | `gpt-5.4-nano` |
| Synthesizer | `gpt-5.4` |
| Web page summaries (`scrape_web`) | `gpt-4o-mini` |
| Embeddings (memory, PDF chunks) | `text-embedding-3-small` |

**Local development only.**

- The frontend calls `http://localhost:8000` directly (hard-coded in `front_agente/src/App.tsx`); there is no setting to point it elsewhere.
- The API has no authentication and allows CORS from any origin. Do not expose it to a network.
- All storage is local files: `projects.json`, `agente_langgraph/checkpoints.db` (chats, SQLite), `mcp_hechos/hechos_lancedb/` (facts and PDF chunks), `agente_langgraph/papers/` and `agente_langgraph/pdf_index.json`.
- The repository currently includes data from development: entries in `projects.json`, LanceDB tables and some downloaded PDFs. A fresh clone may show those projects in the app, with their saved facts and indexed documents. Chat history is not guaranteed: `checkpoints.db` itself is not tracked in git (only stray `-shm`/`-wal` files are), so those projects' chats can be missing or empty.
- There is no test suite.

**Known gaps in the current code.**

- `pdf_index.json` (the "already processed" cache) is shared by all projects. If a PDF was indexed in project A, a worker in project B gets the cached map, but its chunks are stored under project A, so searching inside it from B returns nothing.
- Deleting a project removes it from `projects.json` only; its facts, chunks and chats stay in storage.
- The MCP server starts with the backend and its tools are wrapped in `agente_langgraph/mcp_client.py`, but the graph does not use them yet. The planner and memory node read and write facts directly in LanceDB.

## Technical reference

<details>
<summary><strong>Full architecture diagram</strong></summary>

```
┌─────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (React)                           │
│   Projects | Chats | Chat (SSE streaming) | Memory | Docs | Chunks  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTP / SSE
┌──────────────────────────────▼──────────────────────────────────────┐
│                        FASTAPI BACKEND                              │
│                                                                     │
│  /api/chat/stream  /api/projects  /api/chats  /api/hechos  /api/... │
│         │                                                           │
│         ▼                                                           │
│  ┌─────────────── LangGraph StateGraph (AsyncSqliteSaver) ─────┐    │
│  │                                                             │    │
│  │   START                                                     │    │
│  │     │                                                       │    │
│  │     ▼                                                       │    │
│  │  ┌──────────┐  no research                                  │    │
│  │  │ PLANNER  │──────────────────────────────┐                │    │
│  │  └──────────┘                              │                │    │
│  │     │ needs research (typ. 3-5 angles)     │                │    │
│  │     ▼  Send() fan-out                      │                │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐    │                │    │
│  │  │ WORKER 1 │ │ WORKER 2 │ │ WORKER N │    │  (parallel)    │    │
│  │  │ chatbot  │ │ chatbot  │ │ chatbot  │    │  each worker:  │    │
│  │  │   ⇅      │ │   ⇅      │ │   ⇅      │    │  chatbot ⇄     │    │
│  │  │ tools    │ │ tools    │ │ tools    │    │  tools (max 6) │    │
│  │  └─────┬────┘ └─────┬────┘ └─────┬────┘    │                │    │
│  │        └────────────┼────────────┘         │                │    │
│  │                     ▼  fan-in              │                │    │
│  │              ┌──────────────┐              │                │    │
│  │              │ SYNTHESIZER  │              │                │    │
│  │              └──────┬───────┘              │                │    │
│  │                     ▼                      │                │    │
│  │              ┌──────────────┐◄─────────────┘                │    │
│  │              │ MEMORY NODE  │──► LanceDB `hechos`           │    │
│  │              └──────┬───────┘                               │    │
│  │                     ▼                                       │    │
│  │                   END                                       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  MCP client ◄──── stdio ────► MCP server (mcp_hechos/server.py)     │
│                                 │                                   │
│                                 ▼                                   │
│                         ┌──────────────┐                            │
│                         │   LanceDB    │  - hechos     (memory)     │
│                         │  (embedded)  │  - pdf_chunks (documents)  │
│                         └──────────────┘                            │
└─────────────────────────────────────────────────────────────────────┘
```

</details>

<details>
<summary><strong>Graph nodes</strong></summary>

### Planner

Retrieves the top 5 saved facts for the project that match the latest user message, adds them to its system prompt, and decides the route with structured output:

```python
class PlannerOutput(BaseModel):
    needs_research: bool        # research required?
    angles: list[str]           # populated if needs_research=True, else []
    direct_response: str | None # answer directly if no research needed
```

- `needs_research=True` → sets `research_angles` and fans out to workers with `Send()`, one per angle. The prompt asks for 3–5 angles; nothing in the schema or graph limits the count.
- `needs_research=False` → returns `direct_response` and goes to the memory node
- The prompt tells it to prefer answering from history or memory over launching new research.
- Model: `gpt-5.4-mini` (temperature 0.2)

### Research workers (subgraph)

Each worker is a ReAct loop: an LLM with tool access that keeps calling tools until it stops asking for them or hits the iteration limit.

```
START → chatbot → [has tool_calls?] → tool_node → chatbot → ...
                  [no tool_calls]   → collect_result → END
```

- Model: `gpt-5.4-nano` (temperature 0.0)
- Limit: 6 chatbot iterations per worker
- Output: `WorkerResult` with findings, sources (parsed from `[Source: URL]` markers) and tool history

### Synthesizer

Takes the worker results from the current turn, formats them by angle with their sources, and asks for a final answer in Spanish with citations.

- Model: `gpt-5.4` (temperature 0.2)
- Reads only the last N results, where N is the number of angles in this turn.

### Memory node

Runs at the end of both paths. It looks at the last user message and the last agent reply and decides, with structured output, whether they contain durable facts (user details, project goals or constraints, confirmed information). Each fact is embedded and appended to the `hechos` table with the project id. Failures are swallowed so they never break the conversation.

- Model: `gpt-5.4-mini` (temperature 0.0)

</details>

<details>
<summary><strong>State definitions</strong></summary>

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

`worker_results` uses `operator.add` as a reducer so each worker's output appends to the list. The synthesizer reads only the last N entries (N = number of current angles).

State is checkpointed with `AsyncSqliteSaver` in `agente_langgraph/checkpoints.db`. The thread id is the chat id (or the project id when no chat id is sent), and `project_id` travels in the run config.

</details>

<details>
<summary><strong>Worker tools</strong></summary>

| Tool | Description | Key behavior |
|---|---|---|
| `search_web(query)` | Web search via Tavily | `search_depth="advanced"`; returns results with URLs and snippets |
| `process_pdf(url)` | Download, chunk and index a PDF | Splits into ~3200-character chunks, embeds them with OpenAI, stores them in LanceDB, returns a structural map (title, abstract, sections with chunk ranges). Cached in `pdf_index.json` |
| `scrape_web(urls, query)` | Extract and summarize web pages | Sends PDF URLs to `process_pdf`. Extracts HTML with trafilatura, truncates to 8000 characters, summarizes with `gpt-4o-mini` |
| `rag_pdf_local(url, query)` | Semantic search inside an indexed PDF | Top 5 chunks filtered by source URL and project |
| `list_indexed_pdfs()` | List processed PDFs | Reads `pdf_index.json` |

Tools that touch the vector database (`process_pdf`, `scrape_web`, `rag_pdf_local`) receive `project_id` through LangGraph's `RunnableConfig` injection.

PDF parsing uses `pymupdf4llm`, with a page-by-page `pymupdf` fallback for files it cannot convert.

</details>

<details>
<summary><strong>MCP server</strong></summary>

`mcp_hechos/server.py` is a FastMCP server over stdio. `agente_langgraph/mcp_client.py` starts it as a subprocess when the backend starts and keeps a session open for the app's lifetime. It loads `agente_langgraph/.env` for the OpenAI key.

| MCP tool | Purpose |
|---|---|
| `guardar_si_es_hecho(texto, project_id)` | Store a fact as a vector embedding |
| `search_best_hecho(query, project_id)` | Find the single most relevant stored fact |
| `rag_hechos(query, project_id)` | Return the top 5 facts as context |
| `rag_pdf(url, query, chunk_range, project_id)` | Query indexed PDF chunks by semantic search or by chunk range |

As noted under limitations, the graph does not call these tools today; the wrappers in `mcp_client.py` are not bound to any node.

</details>

<details>
<summary><strong>API endpoints</strong></summary>

Interactive docs are available at `http://localhost:8000/docs` (FastAPI default) while the backend runs.

### Chat

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat` | One request/response turn. Body: `{message, project_id, chat_id?}` |
| `POST` | `/api/chat/stream` | Same body, Server-Sent Events with live progress |

SSE event types for `/api/chat/stream`:

```
{"type": "planner",     "angles": [...]}                       # planner decided to research
{"type": "direct",      "content": "..."}                      # planner answered directly
{"type": "worker_done", "angle": "...", "findings": "...", "sources": [...]}
{"type": "token",       "text": "..."}                         # synthesizer token
{"type": "done"}                                                # graph complete
{"type": "error",       "message": "..."}                      # something failed
```

### Projects and chats

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects` | List projects |
| `POST` | `/api/projects` | Create a project (12-character id). Body: `{name}` |
| `DELETE` | `/api/projects/{project_id}` | Remove a project from `projects.json` |
| `GET` | `/api/projects/{project_id}/chats` | List a project's chats |
| `POST` | `/api/projects/{project_id}/chats` | Create a chat. Body: `{name}` |
| `DELETE` | `/api/chats/{chat_id}` | Delete a chat entry |
| `GET` | `/api/chats/{chat_id}/messages?project_id=` | Rebuild a chat's visible history from the checkpoint |

### Knowledge

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/hechos?project_id=` | List saved facts |
| `GET` | `/api/pdf-chunks?project_id=` | List indexed PDF chunks |
| `GET` | `/api/documents?project_id=` | List documents with chunk counts and download status |
| `GET` | `/api/documents/download/{filename}` | Download a stored PDF |

Knowledge endpoints filter by `project_id`, which defaults to `"default"`.

</details>

<details>
<summary><strong>Data model</strong></summary>

### LanceDB tables (`mcp_hechos/hechos_lancedb/`)

**`hechos`**: semantic memory

| Column | Type | Description |
|---|---|---|
| `texto` | string | The stored fact |
| `vector` | float[1536] | OpenAI embedding |
| `fecha` | string | Timestamp |
| `project_id` | string | Project isolation key |

**`pdf_chunks`**: indexed document content

| Column | Type | Description |
|---|---|---|
| `texto` | string | Chunk text (~3200 characters) |
| `vector` | float[1536] | OpenAI embedding |
| `source_url` | string | Original PDF URL |
| `page` | int | Page number (1-indexed) |
| `chunk_index` | int | Sequential chunk id |
| `fecha` | string | Timestamp |
| `project_id` | string | Project isolation key |

### SQLite (`agente_langgraph/checkpoints.db`)

- LangGraph checkpoint tables (conversation state per thread)
- `chats` table: `id`, `project_id`, `name`, `created_at`

</details>

<details>
<summary><strong>Project structure</strong></summary>

```
agent-researcher/
├── agente_langgraph/           # Backend and agent graph (run uvicorn from here)
│   ├── agente.py               # StateGraph: planner → workers → synthesizer → memory node
│   ├── worker.py               # Worker subgraph (ReAct loop with tools)
│   ├── state.py                # State type definitions
│   ├── local_tools.py          # search_web, scrape_web, process_pdf, rag_pdf_local, list_indexed_pdfs
│   ├── api.py                  # FastAPI endpoints (REST + SSE) and app lifespan
│   ├── mcp_client.py           # MCP subprocess lifecycle and tool wrappers
│   ├── projects.py             # Project CRUD (projects.json)
│   ├── chats.py                # Chat CRUD (SQLite)
│   ├── .env.example            # Tracked template for agente_langgraph/.env
│   ├── pdf_index.json          # Cache of processed PDFs
│   └── papers/                 # Downloaded PDFs
│
├── mcp_hechos/                 # MCP server (started by the backend)
│   ├── server.py               # FastMCP server with 4 tools
│   └── hechos_lancedb/         # LanceDB data directory
│
├── front_agente/               # React frontend
│   ├── src/App.tsx             # Single-page app (chat, memory, docs, chunks tabs)
│   └── package.json            # React 19, Vite 7, react-markdown
│
├── projects.json               # Project list
├── pyproject.toml              # Python dependencies (installed by uv sync)
└── .python-version             # 3.14
```

`agente_langgraph/requirements.txt` and `mcp_hechos/requirements.txt` are older partial lists; use `pyproject.toml`.

</details>

<details>
<summary><strong>Tech stack</strong></summary>

| Layer | Technology |
|---|---|
| Agent framework | LangGraph (`StateGraph`, `Send`, `ToolNode`, `AsyncSqliteSaver`) |
| LLMs | OpenAI `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, `gpt-4o-mini` via langchain-openai |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dimensions) |
| Vector database | LanceDB (embedded, no server) |
| Tool protocol | MCP (Model Context Protocol) over stdio |
| Backend API | FastAPI + Uvicorn |
| Web search | Tavily |
| PDF parsing | pymupdf4llm, with pymupdf fallback |
| Web scraping | trafilatura |
| Frontend | React 19 + TypeScript + Vite 7 |
| Streaming | Server-Sent Events |

</details>

## Design decisions

**Orchestrator-Workers.** The planner decides whether to research and how to split the work. Workers run in parallel with their own tool access, following Anthropic's distinction between agents (LLM-directed) and workflows (code-directed).

**Fan-out and fan-in with `Send()`.** Each research angle runs as an independent subgraph. Workers don't share state, so one angle's findings can't leak into another's. Results merge at the synthesizer.

**Memory before research.** The planner reads the project's saved facts and the chat history first, so follow-up questions and recalled details get a direct answer without a new round of paid research.

**Embedded vector database.** LanceDB runs in-process with nothing to deploy, which fits a single-user local tool.

**MCP for memory.** The memory operations also exist as an MCP server so the memory layer can be swapped or shared with other MCP clients. The graph currently bypasses it (see limitations).

**Streaming UI.** SSE events let the frontend show each phase (plan, each worker finishing, synthesis) as it happens.

**Project isolation.** Facts, PDF chunks and chats carry a `project_id`, so separate research topics stay apart (with the `pdf_index.json` exception noted above).

## Other documentation

- [front_agente/DESIGN_SPEC.md](front_agente/DESIGN_SPEC.md): visual design spec for the frontend (colors, typography, components).

The following notes are in Spanish and were written for an earlier version of the agent (calculator tools and, in the sub-folder notes, a SQLite memory). They still explain the concepts, but their setup steps and tool lists are out of date:

- [README-no-tecnico.md](README-no-tecnico.md): non-technical introduction to agents, MCP and vector memory
- [agente_langgraph/README.md](agente_langgraph/README.md): backend notes
- [mcp_hechos/README.md](mcp_hechos/README.md): MCP server notes
- [front_agente/README.md](front_agente/README.md): frontend notes

## License

No license file is committed yet.
