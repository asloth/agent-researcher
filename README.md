# Agente Educacional MCP: Arquitectura Basada en "Building Effective Agents" (Anthropic)

Este proyecto es una implementación educativa de un ecosistema de IA moderno. Toda la arquitectura, diseño de dependencias y flujos de control están respaldados conceptualmente por las mejores prácticas expuestas por **Anthropic** en su investigación ["Building Effective Agents"](https://www.anthropic.com/engineering/building-effective-agents).

El propósito principal no es solo "chatear" con una IA, sino desplegar un sistema capaz de evaluar contextos, invocar dependencias externas vía **MCP** (Model Context Protocol) de forma autónoma, y asegurar información de "verdad fundamental" (Ground Truth) a través de bases de datos vectoriales semánticas antes de responder.

---

## 1. El Bloque Fundacional: El LLM Aumentado (Augmented LLM)
Tal como postula Anthropic, los sistemas agénticos no nacen de la nada. Comienzan con un "LLM Aumentado". En nuestro caso usamos **GPT-4o-Mini** (vía LangChain/LangGraph) aumentado con dos herramientas clave:
*   **Capacidad de Cálculo (Herramienta Local):** Operaciones matemáticas puras sin depender de alucinaciones matemáticas del LLM.
*   **Capacidad de Memoria/RAG (Herramienta Externa):** Almacenaje de hechos biográficos en una base de datos vectorial a través del protocolo oficial **MCP**.

## 2. Diferenciación Arquitectónica: Somos un "Agente", no solo un "Workflow"
Anthropic hace una distinción muy estricta:
*   _Workflows_: El código predefine la ruta exacta que debe tomar el LLM (Ej: paso 1 -> paso 2 -> paso 3).
*   _Agents_: El LLM dirige su propio proceso, manteniendo el control de cómo va a completar la tarea.

**Nuestro proyecto (`agente_langgraph`) es un Agente Autónomo**. Mediante `StateGraph`, el LLM inicia la tarea interactiva tras leer el *prompt* del usuario humano. Evalúa si posee la información, decide si debe invocar la herramienta remota de SQLite/LanceDB o la calculadora local, recibe el *feedback* del entorno, reconsidera sus acciones, y finalmente emite una respuesta al humano cuando está satisfecho.

## 3. Principio Rector de Anthropic: "Simplicity First" (Mantenlo Simple)
La guía de ingeniería sugiere fervientemente **evitar la sobreingeniería** introducida por frameworks pesados cuando puedes escribir código nativo con APIs directas de Python. 

Alineados a este principio de robustez:
*   **RAG (Retrieval-Augmented Generation) Semántico Nativo:** En vez de levantar frameworks pesados de memoria (como ChromaDB o LangChain pre-construidos), el subproceso `mcp_hechos` interactúa directamente con **LanceDB** de forma empotrada (Local embedded) sin requerir infraestructura externa de servidores. Se utilizan los embeddings de OpenAI nativos (`text-embedding-3-small`) que traducen el conocimiento a tuplas vectoriales que el MCP Server evalúa directamente por Similitud de Coseno (`distance`).
*   **Interacción Directa con la BD Frontend:** Extraemos y pintamos los datos de React (`front_hechos`) interactuando con las tablas locales de LanceDB mediante tipos `Arrow` nativos sin instalar dependencias monstruosas como Pandas que harían lento nuestro despliegue.

## 4. Agent-Computer Interface (ACI) y Prompt Engineering
Anthropic recalca que la calidad de un Agente depende en enorme medida de cómo estén documentadas sus herramientas (su ACI).
*   **Nuestras Tools:** Si observas `mcp_hechos/server.py`, el bloque `@mcp.tool()` no solamente expone un servicio. El `docstring` de cada función en Python (ej: _"Guarda un texto... El Agente LLM debería utilizar esta herramienta si..."_) funge exactamente como la barrera de seguridad. El LLM comprende estos contratos al vuelo gracias al protocolo MCP antes de tomar una decisión.
*   **System Prompt Restrictivo:** Usamos una táctica de diseño conocida como *Routing Contextual* en nuestro loop principal (`agente.py`), inyectando un System Message inquebrantable. Este prompt desvía la confianza del LLM desde su *conocimiento paramétrico (interno)* hacia la *Verdad Fundamental (Entorno real)* obligándole sistemáticamente a usar `search_best_hecho` y `rag_hechos` como primera capa de validación. Si recibe una respuesta negativa del servidor MCP, el agente "se rinde" admitiendo ignorancia en lugar de alucinar.

---

## Mapa de la Estructura del Código

El sistema está construido desacoplando las responsabilidades (Separation of Concerns):

1. **`/mcp_hechos`**: Proveedor del Conocimiento (Workers / Toolings). 
   *    Basado en el SDK de `mcp` (Model Context Protocol).
   *    Contiene la lógica pesada: Vectorización (OpenAI), Almacenamiento (LanceDB), Scoring y Retrieve.
   *    Corre instanciado como subproceso.
2. **`/agente_langgraph`**: Cerebro Orquestador (The Central LLM).
   *    Añade un manejador asíncrono robusto cruzando `AnyIO` (LIFO cancel scopes) mediante un Hook `lifespan` de FastAPI que enciende y enlaza de maravilla el cliente de `stdio` del subproceso `mcp_hechos`.
   *    Fija el *MemorySaver* para recordar la discusión, y despacha en exclusiva en endpoint `/api/chat` la ventana del último turno activo a los frontends sin desbordarlos en datos obsoletos de historiales de *tooling*.
3. **`/front_agente`**: Frontend en React. Demuestra de manera transparente al operador humano cada decisión que toma el agente en el trasfondo (identificando visualmente con insignias si ejecutó código local en Python o se comunicó con los satélites externos MCP).
4. **`/front_hechos`**: Monitor en tiempo real para visualizar cómo la "memoria" asíncrona va mutando en LanceDB conforme el humano y el agente dialogan.

### Cómo arrancar todo el sistema:
*(Nota: Asume que has activado el Entorno Virtual de Python y tienes `OPENAI_API_KEY` definido en `/agente_langgraph/.env`)*

```bash
# Terminal 1 - Inicia Backend FastAPI y Subproceso MCP LanceDB
source .venv/bin/activate
cd agente_langgraph
uvicorn api:app --reload

# Terminal 2 - Inicia Dashboard de Agente
cd front_agente
npm run dev

# Terminal 3 - Inicia Dashboard de Hechos LanceDB
cd front_hechos
npm run dev
```
