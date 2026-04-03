from typing import Annotated
from typing_extensions import TypedDict
import os
from dotenv import load_dotenv

# Carga las variables de entorno desde un archivo .env (vital para OPENAI_API_KEY)
load_dotenv()

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode, tools_condition

# Importaciones locales (nuestras herramientas)
from local_tools import local_tools
from mcp_client import mcp_tools_list

# Definimos la memoria de estado del Agente
class State(TypedDict):
    messages: Annotated[list, add_messages]

# Unimos todas las "Tools" de manera indistinta para el Agente
all_tools = local_tools + mcp_tools_list

# Se inyectan las herramientas al LLM
llm = ChatOpenAI(model="gpt-5.4", temperature=0.2, streaming=True) # Asume OPENAI_API_KEY
llm_with_tools = llm.bind_tools(all_tools)

# Nodo principal: El LLM decide qué hacer
def chatbot(state: State):
    # Verificamos si ya hay un SystemMessage. Si no, lo inyectamos al inicio del historial de este turno
    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        sys_msg = SystemMessage(content="""You are a professional research assistant. ALWAYS answer in spanish.

## Core Rules
- Never answer from your own knowledge. Only use information retrieved from tools.
- If no source is found, say so honestly.
- Save important findings and user info with guardar_si_es_hecho.

## Research Methodology
When the user asks a question, conduct a THOROUGH investigation:

1. **Plan your research**: Break the topic into 3-5 different search angles or threads. Think like a researcher — what subtopics, perspectives, or keywords would give you comprehensive coverage?

2. **Execute multiple searches**: Run search_web for EACH angle. Do NOT stop after one search. A serious investigation needs at minimum 3 different search queries exploring different facets of the topic.

3. **Process results from each search**:
   - PDF URLs (.pdf in the URL) → use process_pdf to index them
   - Regular web pages → use scrape_web to extract content
   - NEVER send PDF URLs to scrape_web — it cannot parse them.
   - NEVER send web pages to process_pdf.
   - Pass all HTML URLs from a single search together in one scrape_web call.

4. **Follow leads**: If a source mentions an interesting reference, study, or claim — do a follow-up search on it. Good research is iterative, not a single pass.

5. **Save PDF index to memory**: After process_pdf returns the structural map (title, abstract, sections, chunk ranges), ALWAYS save it to memory using guardar_si_es_hecho. This way you can recall what PDFs you've processed and what's in them without reprocessing.

6. **Query indexed PDFs**: Use rag_pdf to query specific sections of a processed PDF for deeper understanding. Check memory first to recall the structural map and know which chunks to request.

7. **Synthesize**: Once you have enough sources (aim for 8-15 sources minimum), write a well-structured answer with inline citations. Organize by themes, not by source.

## Answer Format
- Structure with clear headings
- Cite sources inline: [Fuente: título o URL]
- End with a "Fuentes" section listing all sources used
- Flag any contradictions between sources""")
        messages = [sys_msg] + messages
    return {"messages": [llm_with_tools.invoke(messages)]}

# Nodo de herramientas proporcionado por LangGraph
tool_node = ToolNode(all_tools)

# Construcción de las aristas y el flujo del grafo
graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_node("tools", tool_node)

graph_builder.add_edge(START, "chatbot")
# tools_condition redirige automáticamente si el LLM invocó alguna tool
graph_builder.add_conditional_edges("chatbot", tools_condition)
graph_builder.add_edge("tools", "chatbot")

import os
# Compilamos el grafo. Usar memoria Checkpointer. (por simplicidad, no en uso avanzado acá)
from langgraph.checkpoint.memory import MemorySaver
memory = MemorySaver()
graph = graph_builder.compile(checkpointer=memory)
