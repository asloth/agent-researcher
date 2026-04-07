from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from pydantic import BaseModel
from langgraph.types import Send
from langchain_openai import ChatOpenAI
from state import OverallState
from worker import WORKER_SYSTEM_PROMPT, worker_subgraph


load_dotenv()

llm_planner = ChatOpenAI(model="gpt-5.4-mini", temperature=0.2, streaming=True) # Asume OPENAI_API_KEY

class PlannerOutput(BaseModel):
    needs_research: bool
    angles: list[str]          # populated if needs_research=True, else []
    direct_response: str | None # populated if needs_research=False, else None

def planner_node(state: OverallState) :
    # Este nodo es un ejemplo de cómo podríamos usar el LLM para planificar la investigación
    # Retorna una estructura indicando si se necesita investigación y qué ángulos seguir
    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        sys_msg = SystemMessage(content="""Eres un asistente de investigacion. 
            Analiza el mensaje del usuario y decide si necesitas hacer investigación usando herramientas para responder adecuadamente. 
            Si necesitas investigar: needs_research=true, angles=[3-5 ángulos], direct_response=null. 
            Si no: needs_research=false, angles=[], direct_response=tu respuesta.
           """)
        messages = [sys_msg] + messages
    
    llm_structured = llm_planner.with_structured_output(PlannerOutput)
    plan = llm_structured.invoke(messages)   
    if plan.needs_research:                                                                                                                                                                                                                      
        return {"research_angles": plan.angles}
    else:                                                                                                                                                                                                                                        
        return {"messages": [AIMessage(content=plan.direct_response)], "research_angles": []}

def route_after_planner(state: OverallState):
    if len(state.get("research_angles") or []) > 0:
        question = next(m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage))
        return [
            Send("research_worker", {
                "messages": [
                    SystemMessage(content=WORKER_SYSTEM_PROMPT),
                    HumanMessage(content=f"ÁNGULO: {angle}\nPREGUNTA: {question}"),
                ],
                "angle": angle,
                "iteration_count": 0,
            })
            for angle in state["research_angles"]
        ]
    else:
        return END

llm_synthe = ChatOpenAI(model="gpt-5.4", temperature=0.2, streaming=True) # Asume OPENAI_API_KEY

async def synthesizer_node(state: OverallState):
    # Only synthesize results from THIS turn. `worker_results` accumulates across
    # turns via operator.add, but `research_angles` is overwritten each turn by the
    # planner, so the current turn's results are the last N entries (N = angles).
    n_current = len(state.get("research_angles", []))
    current_results = state["worker_results"][-n_current:] if n_current else []

    findings_text = "\n\n".join([
      f"## Ángulo: {wr['angle']}\n\nHallazgos:\n{wr['findings']}\n\nFuentes:\n" +
      "\n".join(f"- {s}" for s in wr['sources'])
      for wr in current_results
      ])
    original_question = next(m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage))
    synthesis_prompt = HumanMessage(content=f"""Pregunta original: {original_question}
        Hallazgos de los investigadores:
        {findings_text}
        Sintetiza estos hallazgos en una respuesta final en español con citas.""")

    response = await llm_synthe.ainvoke([synthesis_prompt])

    return {"messages": [response]}


# Construcción de las aristas y el flujo del grafo
graph_builder = StateGraph(OverallState)
graph_builder.add_node("planner", planner_node)                                                                                                                                                                                              
graph_builder.add_node("research_worker", worker_subgraph)  # from worker.py
graph_builder.add_node("synthesizer", synthesizer_node)                                                                                                                                                                                      
                  
graph_builder.add_edge(START, "planner")                                                                                                                                                                                                     
graph_builder.add_conditional_edges("planner", route_after_planner, ["research_worker", END])
graph_builder.add_edge("research_worker", "synthesizer")                                                                                                                                                                                     
graph_builder.add_edge("synthesizer", END)                                                                                                                                                                                                   
                                                                                                                                                                                                                                               

# Compilamos el grafo. Usar memoria Checkpointer. (por simplicidad, no en uso avanzado acá)
from langgraph.checkpoint.memory import MemorySaver
memory = MemorySaver()
graph = graph_builder.compile(checkpointer=memory)
