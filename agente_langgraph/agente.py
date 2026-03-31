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
        sys_msg = SystemMessage(content="You are a research assistant. ALWAYS answer in spanish. Don't use information that is not in the sources. Objective: Synthesize findings into clear answers with sources. Keep track of your research and the user info in the mcp_hechos. IMPORTANT: When you use search_web and get results, you MUST pass ALL the URLs to scrape_web in a single call. Do not skip any URL.")
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
