import os
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), "..", "agente_langgraph", ".env")
load_dotenv(env_path)

import lancedb
from openai import OpenAI
import datetime
from mcp.server.fastmcp import FastMCP

# Configuración de base de datos
DB_PATH = os.path.join(os.path.dirname(__file__), "hechos_lancedb")
db = lancedb.connect(DB_PATH)

# El cliente OpenAI asume que OPENAI_API_KEY está en entorno
client = OpenAI()

def get_embedding(text: str) -> list[float]:
    response = client.embeddings.create(
        input=[text],
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

# Inicializamos el servidor FastMCP
mcp = FastMCP("ServidorHechosLanceDB")

@mcp.tool()
def guardar_si_es_hecho(texto: str) -> str:
    """
    Guarda un texto en la base de datos de hechos vectoriales.
    
    El Agente LLM debería utilizar esta herramienta si, a su juicio, la frase del 
    usuario constituye un 'hecho' o información vital que debe ser recordada.
    """
    try:
        vector = get_embedding(texto)
        fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = [{"texto": texto, "vector": vector, "fecha": fecha}]
        
        if "hechos" not in db.table_names():
            db.create_table("hechos", data=data)
        else:
            tbl = db.open_table("hechos")
            tbl.add(data)
            
        return f"✅ Hecho guardado y vectorizado en LanceDB: '{texto}'"
    except Exception as e:
        return f"❌ Error guardando hecho: {str(e)}"

@mcp.tool()
def search_best_hecho(query: str) -> str:
    """
    Busca el hecho más relevante en la BD de forma semántica usando embeddings.
    Retorna el hecho que más coincida con el significado de la búsqueda.
    """
    if "hechos" not in db.table_names():
        return "❌ La base de datos está vacía, no hay hechos."
        
    try:
        query_vector = get_embedding(query)
        tbl = db.open_table("hechos")
        results = tbl.search(query_vector).limit(1).to_list()
        
        if results:
            mejor_hecho = results[0]["texto"]
            distancia = results[0].get("_distance", 0.0)
            return f"🔎 Mejor hecho encontrado (Distancia {distancia:.4f}): {mejor_hecho}"
        return "❌ No se encontraron hechos relevantes."
    except Exception as e:
        return f"❌ Error buscando hecho: {str(e)}"

@mcp.tool()
def rag_hechos(query: str) -> str:
    """
    Genera un contexto recuperando los 5 hechos más cercanos semánticamente (RAG vectorial).
    """
    if "hechos" not in db.table_names():
        return "❌ No hay contexto en la DB."
        
    try:
        query_vector = get_embedding(query)
        tbl = db.open_table("hechos")
        results = tbl.search(query_vector).limit(5).to_list()
        
        if results:
            hechos = [res["texto"] for res in results]
            contexto = " | ".join(hechos)
            return f"📚 Contexto semántico recuperado para '{query}': {contexto}"
        return f"❌ No se pudo recuperar contexto."
    except Exception as e:
        return f"❌ Error recuperando contexto: {str(e)}"

if __name__ == "__main__":
    # Ejecuta el servidor MCP comunicándose por standard input/output (stdio)
    mcp.run(transport="stdio")
