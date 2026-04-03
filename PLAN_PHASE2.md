# Phase 2: Parallel Research Subagents

## Context

The current agent is a single ReAct loop (chatbot->tools->chatbot). While Phase 1 improved the prompt to plan multiple search angles, the LLM still executes them sequentially in one long chain. This makes research slow and shallow -- it often stops after 3-4 sources.

Phase 2 restructures the graph into an **orchestrator-workers pattern**: a planner breaks the question into research threads, parallel workers investigate each thread independently, and a synthesizer merges all findings into a final answer.

## Progress

- [x] **Step 1**: Add `rag_pdf_local` to `local_tools.py` -- DONE, code written
- [ ] **Step 2**: Add `mcp_rag_pdf` to `mcp_client.py` -- NOT STARTED
- [ ] **Step 3**: Create `worker.py` -- NOT STARTED
- [ ] **Step 4**: Rewrite `agente.py` (orchestrator graph) -- NOT STARTED
- [ ] **Step 5**: Update `api.py` (response format) -- NOT STARTED

## What was done in Phase 1 (today's session)

1. Rewrote system prompt to instruct multi-angle research methodology
2. Improved all tool docstrings (ACI) with clear when-to-use / when-NOT-to-use guidance
3. Fixed `process_pdf` crash on HTTP 403 -- tools now return error messages instead of throwing
4. Added PDF index saving instruction to system prompt (guardar_si_es_hecho after process_pdf)
5. Updated `rag_pdf` MCP docstring

## Architecture

```
START -> planner -> [Send x N workers in parallel] -> synthesizer -> END

Each worker (ReAct subgraph):
  chatbot -> tools_condition -> tools -> chatbot -> ... -> collect -> END
```

## Files to Change

| File | Action | What |
|------|--------|------|
| `agente_langgraph/agente.py` | Rewrite | New OverallState, planner, routing, synthesizer, main graph |
| `agente_langgraph/worker.py` | **Create** | WorkerState, worker subgraph with ReAct loop, collect node |
| `agente_langgraph/local_tools.py` | Add function | `rag_pdf_local()` -- DONE |
| `agente_langgraph/mcp_client.py` | Add wrapper | `mcp_rag_pdf()` for synthesizer use |
| `agente_langgraph/api.py` | Adapt | Extract worker_results for frontend, keep existing response contract |

## Step-by-step Plan

### Step 1: Add `rag_pdf_local` to `local_tools.py` -- DONE

Local version of MCP rag_pdf that queries LanceDB directly. Workers need this because they can't use MCP (single stdio pipe, no concurrency).

### Step 2: Add `mcp_rag_pdf` to `mcp_client.py`

Add the missing async wrapper for the synthesizer to use:

```python
async def mcp_rag_pdf(url: str, query: str = None, chunk_range: str = None) -> str:
    global mcp_session
    arguments = {"url": url}
    if query:
        arguments["query"] = query
    if chunk_range:
        arguments["chunk_range"] = chunk_range
    res = await mcp_session.call_tool("rag_pdf", arguments=arguments)
    return res.content[0].text
```

Add to `mcp_tools_list`.

### Step 3: Create `worker.py` -- Worker Subgraph

**WorkerState:**
```python
class WorkerState(TypedDict):
    messages: Annotated[list, add_messages]
    angle: str
    iteration_count: int
```

**Nodes:**
- `worker_chatbot`: calls LLM (gpt-5.4) with local tools bound (search_web, scrape_web, process_pdf, rag_pdf_local). Increments iteration_count.
- `tools`: ToolNode with local tools only (no MCP -- avoids concurrent session issues)
- `collect_result`: terminal node that extracts findings and sources from messages, returns `{"worker_results": [one_result]}` mapping WorkerState -> OverallState

**Routing:**
- `worker_route`: if `iteration_count >= 6` -> "collect" (force stop). If last message has tool_calls -> "tools". Else -> "collect".

**Build:**
```python
StateGraph(WorkerState, output=OverallState)  # output schema maps to parent
```

Worker system prompt (injected via Send):
```
You are a research worker. Investigate this specific angle thoroughly.
ANGLE: {angle}
ORIGINAL QUESTION: {question}
Use search_web, scrape_web, process_pdf, and rag_pdf_local.
When done, write a detailed summary with [Source: URL] citations.
```

### Step 4: Rewrite `agente.py` -- Orchestrator Graph

**OverallState:**
```python
class WorkerResult(TypedDict):
    angle: str
    findings: str
    sources: list[str]
    tool_history: list[dict]

class OverallState(TypedDict):
    messages: Annotated[list, add_messages]
    research_angles: list[str]
    worker_results: Annotated[list[WorkerResult], operator.add]
```

**Planner node:**
- Uses LLM with structured output (Pydantic model) to produce 3-5 research angles from the user question
- Stores in `research_angles`

**Routing function (`route_to_workers`):**
- Returns `list[Send("research_worker", WorkerState(...))]` -- one per angle
- Each Send initializes fresh WorkerState with system prompt + angle

**Synthesizer node:**
- Collects all `worker_results`
- Builds a synthesis prompt with all findings organized by angle
- Single LLM call to produce final structured answer in Spanish
- Saves summary to MCP memory via `mcp_guardar_si_es_hecho`
- Appends final AIMessage to `messages` for API compatibility

**Graph:**
```python
graph_builder = StateGraph(OverallState)
graph_builder.add_node("planner", planner_node)
graph_builder.add_node("research_worker", worker_subgraph)
graph_builder.add_node("synthesizer", synthesizer_node)

graph_builder.add_edge(START, "planner")
graph_builder.add_conditional_edges("planner", route_to_workers, ["research_worker"])
graph_builder.add_edge("research_worker", "synthesizer")
graph_builder.add_edge("synthesizer", END)
```

### Step 5: Update `api.py` -- Response Format

Keep existing contract (`response` + `history`) and add optional `workers` field:

```python
return {
    "response": result["messages"][-1].content,
    "history": log_msgs,
    "workers": [
        {"angle": wr["angle"], "findings": wr["findings"][:500], "sources": wr["sources"]}
        for wr in result.get("worker_results", [])
    ]
}
```

Backward-compatible -- frontend can ignore `workers` until updated.

## Key Design Decisions

1. **Workers use local tools only, no MCP** -- avoids concurrent stdio session corruption. MCP tools only in synthesizer (runs after all workers).
2. **Workers are ReAct agents** (not fixed pipelines) -- they decide which tools to call and can follow leads.
3. **Max 6 iterations per worker** -- caps cost at ~18-30 LLM calls for 3-5 workers + planner + synthesizer.
4. **`rag_pdf_local` as local tool** -- duplicates MCP rag_pdf logic but avoids session dependency. Workers can query PDFs they just indexed.
5. **Planner uses structured output** -- guarantees parseable list of angles, no regex parsing needed.

## Verification

1. Start server: `cd agente_langgraph && python -c "import uvicorn; from api import app; uvicorn.run(app, port=8000)"`
2. Test simple greeting: `curl -X POST localhost:8000/api/chat -H 'Content-Type: application/json' -d '{"message":"hola"}'`
3. Test research: `curl -X POST localhost:8000/api/chat -d '{"message":"investiga sobre el impacto de la IA en educacion"}'` -- should return response with multiple worker results and 8+ sources
4. Check MCP memory: `curl localhost:8000/api/hechos` -- should show saved research summary
5. Check PDF indexing: `curl localhost:8000/api/pdf-chunks` -- should show chunks if PDFs were found
