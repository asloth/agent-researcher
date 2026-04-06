import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import os

from agente import graph
from langchain_core.messages import HumanMessage
from mcp_client import mcp_lifespan

# Pasamos el manejador asíncrono que inicializa y destruye MCP limpiamente
app = FastAPI(title="Agente Educacional MCP y LangGraph", lifespan=mcp_lifespan)

# Habilitamos CORS para que los frontends (React) nos puedan consultar
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Endpoint principal para conversar con el Agente LangGraph.
    Retorna tanto la respuesta textual como el historial detallado de las Tools que usó.
    """
    try:
        # Configuración de memoria (el thread se fija a 1 para simular sesión continua)
        config = {"configurable": {"thread_id": "1"}}
        
        input_message = HumanMessage(content=request.message)
        # Invocación asíncrona del grafo
        result = await graph.ainvoke({"messages": [input_message]}, config)
        
        # Procesamos solo la porción nueva del historial, omitiendo cosas de turnos anteriores
        new_messages = result["messages"]
        # Encontramos desde dónde empezó la conversación de ESTE turno específico
        # que sería a partir del último HumanMessage.
        start_index = 0
        for i in range(len(new_messages) - 1, -1, -1):
            if isinstance(new_messages[i], HumanMessage):
                start_index = i + 1
                break
                
        turn_messages = new_messages[start_index:]
        
        log_msgs = []
        for m in turn_messages:
            tool_calls = getattr(m, 'tool_calls', [])
            log_msgs.append({
                "type": m.__class__.__name__,
                "content": m.content,
                "tool_calls": tool_calls,
                "name": getattr(m, 'name', '') # Importante para saber qué Tool se ejecutó
            })
            
        return {
            "response": result["messages"][-1].content,
            "history": log_msgs,
            "workers": [
                {
                    "angle": wr["angle"],
                    "findings": wr["findings"],
                    "sources": wr["sources"],
                }
                for wr in (
                    result.get("worker_results", [])[-len(result.get("research_angles", [])):]
                    if result.get("research_angles") else []
                )
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """
    Streaming variant of /api/chat. Returns Server-Sent Events with progress updates:
      - {"type": "planner", "angles": [...]}      planner chose to research
      - {"type": "direct", "content": "..."}      planner answered without research
      - {"type": "worker_done", "angle": "...", "findings": "...", "sources": [...]}
      - {"type": "token", "text": "..."}          synthesizer streaming tokens
      - {"type": "done"}                          graph finished
      - {"type": "error", "message": "..."}       something blew up
    """
    config = {"configurable": {"thread_id": "1"}}
    input_message = HumanMessage(content=request.message)

    async def event_generator():
        def sse(payload: dict) -> str:
            return f"data: {json.dumps(payload)}\n\n"

        try:
            async for mode, chunk in graph.astream(
                {"messages": [input_message]},
                config,
                stream_mode=["updates", "messages"],
            ):
                if mode == "updates":
                    # chunk is {node_name: state_update}
                    for node_name, update in chunk.items():
                        if node_name == "planner":
                            if update.get("research_angles"):
                                yield sse({"type": "planner", "angles": update["research_angles"]})
                            elif update.get("messages"):
                                # Direct-response path (no research needed)
                                yield sse({"type": "direct", "content": update["messages"][-1].content})
                        elif node_name == "research_worker":
                            # Each worker finishing produces its own update with one WorkerResult
                            for wr in update.get("worker_results", []):
                                yield sse({
                                    "type": "worker_done",
                                    "angle": wr["angle"],
                                    "findings": wr["findings"],
                                    "sources": wr["sources"],
                                })
                        # synthesizer 'updates' event is redundant — tokens already streamed
                elif mode == "messages":
                    # chunk is (AIMessageChunk, metadata)
                    msg_chunk, metadata = chunk
                    if metadata.get("langgraph_node") == "synthesizer":
                        text = getattr(msg_chunk, "content", "") or ""
                        if text:
                            yield sse({"type": "token", "text": text})

            yield sse({"type": "done"})
        except Exception as e:
            yield sse({"type": "error", "message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/hechos")
def get_hechos():
    """
    Endpoint auxiliar expuesto por el backend para el segundo frontend ('front_hechos')
    Lee directamente SQLite. (Aunque la buena práctica podría ser exponer esto vía MCP también, 
    para este ejercicio simple, lo servimos mediante la REST API).
    """
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mcp_hechos", "hechos_lancedb"))
    if not os.path.exists(db_path):
        return {"hechos": []}
        
    import lancedb
    db = lancedb.connect(db_path)
    # Buscamos la table 'hechos', si no existe, retornamos lista vacía
    if "hechos" not in db.table_names():
        return {"hechos": []}
        
    tbl = db.open_table("hechos")
    
    # Extraemos y ordenamos sin usar Pandas para mantener el SDK ligero
    rows = tbl.to_arrow().to_pylist()
    
    if not rows:
        return {"hechos": []}
        
    rows.sort(key=lambda x: x["fecha"], reverse=True)
    
    return {"hechos": [{"id": len(rows) - i, "contenido": r["texto"], "fecha": r["fecha"]} for i, r in enumerate(rows)]}

@app.get("/api/pdf-chunks")
def get_pdf_chunks():
    """
    Endpoint para listar los chunks de PDFs indexados en LanceDB.
    """
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mcp_hechos", "hechos_lancedb"))
    if not os.path.exists(db_path):
        return {"chunks": []}

    import lancedb
    db = lancedb.connect(db_path)
    if "pdf_chunks" not in db.table_names():
        return {"chunks": []}

    tbl = db.open_table("pdf_chunks")
    rows = tbl.to_arrow().to_pylist()

    if not rows:
        return {"chunks": []}

    rows.sort(key=lambda x: (x.get("source_url", ""), x.get("chunk_index", 0)))

    return {"chunks": [
        {
            "texto": r["texto"],
            "source_url": r.get("source_url", ""),
            "page": r.get("page", 0),
            "chunk_index": r.get("chunk_index", 0),
            "fecha": r.get("fecha", ""),
        }
        for r in rows
    ]}
