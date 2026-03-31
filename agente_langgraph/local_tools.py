import sys
import os
from dotenv import load_dotenv

# Carga las variables de entorno desde un archivo .env (vital para OPENAI_API_KEY)
load_dotenv()

# Agregamos la ruta base para poder importar herramientas del cliente si fuera necesario
sys.path.append(os.path.dirname(__file__))

def search_web(query: str) -> str:
    """Búsqueda de informacion en la web."""
    from tavily import TavilyClient
    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    response = client.search(
        query=query,
        search_depth="advanced",
        num_results=10,
    )
    return response['results'] 

def scrape_web(urls: list[str], query: str) -> str:                                                                                                                                                                                                
    """Extrae y resume el contenido de múltiples páginas web. Recibe una lista de URLs y resume cada una. Siempre pasa TODAS las URLs disponibles. Usa 'query' para enfocar el resumen en lo relevante."""
    import trafilatura                                                                                                                                                                                                                      
    from langchain_openai import ChatOpenAI
    results = []
    for url in urls:
        # 1. Descargar y extraer contenido limpio
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            results.append(f"❌ No se pudo descargar: {url}")
            continue

        text = trafilatura.extract(downloaded, include_links=True, include_tables=True)
        if not text:
            results.append(f"❌ No se pudo extraer contenido de: {url}")
            continue                                                                                                                                                                                 
                                                                                                                                                                                                                                              
        # 2. Truncar a ~8000 chars para no exceder contexto del LLM de resumen                                                                                                                                                                  
        text = text[:8000]                                                                                                                                                                                                                      
                                                                                                                                                                                                                                              
        # 3. Resumir con LLM aparte (no entra al estado del agente principal)                                                                                                                                                                   
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        summary = llm.invoke(                                                                                                                                                                                                                   
            f"Resume el siguiente contenido web enfocándote en lo relevante a: '{query}'\n\n{text}"
        )                                  
        results.append(f"📄 {url}:\n{summary}")                                                                                                                                                                                                     
                                                                                                                                                                                                                                              
    return "\n\n".join(results)

def process_pdf(url: str) -> str:
    """
    Downloads, chunks, and indexes a PDF. Returns a structural map 
    of the document including sections, page numbers, and chunk ranges.
    """
    import httpx
    import pymupdf4llm
    import re
    import lancedb
    import datetime
    from openai import OpenAI

    openai_client = OpenAI()
    db = lancedb.connect(os.path.join(os.path.dirname(__file__), "..", "mcp_hechos", "hechos_lancedb"))
    # --- A, B, C) Filename, Cache & Download ---
    raw_filename = url.split("/")[-1].split("?")[0].split("#")[0]
    clean_filename = re.sub(r'[^\w\d.\-]', '_', raw_filename)
    if not clean_filename.lower().endswith(".pdf"):
        clean_filename += ".pdf"
    
    os.makedirs("papers", exist_ok=True)
    file_path = os.path.join("papers", clean_filename)

    if not os.path.exists(file_path):
        with httpx.Client(follow_redirects=True, timeout=60.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            with open(file_path, "wb") as f:
                f.write(resp.content)
    pages = pymupdf4llm.to_markdown(file_path, page_chunks=True)

    # --- First pass: chunk text and extract structure ---
    chunks_to_store = []
    sections = []
    current_chunk_text = ""
    current_page = 1
    chunk_index = 0
    MAX_CHARS = 3200
    title = clean_filename
    abstract = ""

    for page_idx, page in enumerate(pages):
        page_num = page_idx + 1
        paragraphs = page["text"].split("\n\n")

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            header_match = re.match(r'^(#+)\s+(.*)', para)
            if header_match:
                level = len(header_match.group(1))
                header_text = header_match.group(2)
                if level == 1 and title == clean_filename:
                    title = header_text
                sections.append({"title": header_text, "page": page_num, "start_chunk": chunk_index})

            if "abstract" in para.lower() and len(para) > 50 and not abstract:
                abstract = para.replace("Abstract", "").strip()[:500] + "..."

            if len(current_chunk_text) + len(para) > MAX_CHARS and current_chunk_text:
                chunks_to_store.append({"texto": current_chunk_text.strip(), "page": current_page, "chunk_index": chunk_index})
                chunk_index += 1
                current_chunk_text = para
                current_page = page_num
            else:
                if not current_chunk_text:
                    current_page = page_num
                current_chunk_text += "\n\n" + para if current_chunk_text else para

    if current_chunk_text:
        chunks_to_store.append({"texto": current_chunk_text.strip(), "page": current_page, "chunk_index": chunk_index})

    texts = [c["texto"] for c in chunks_to_store]
    embeddings = openai_client.embeddings.create(input=texts, model="text-embedding-3-small").data
    fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    records = [
        {
            "texto": chunk["texto"],
            "vector": embeddings[i].embedding,
            "source_url": url,
            "page": chunk["page"],
            "chunk_index": chunk["chunk_index"],
            "fecha": fecha,
        }
        for i, chunk in enumerate(chunks_to_store)
    ]

    # --- Batch insert into LanceDB ---
    if records:
        if "pdf_chunks" not in db.table_names():
            db.create_table("pdf_chunks", data=records)
        else:
            db.open_table("pdf_chunks").add(records)

    # --- H) Format Structured Return ---
    # Map end_chunks for sections
    section_list = []
    for i, sec in enumerate(sections):
        end_chunk = sections[i+1]["start_chunk"] - 1 if i+1 < len(sections) else chunk_index
        section_list.append(f"- {sec['title']} (page {sec['page']}, chunks {sec['start_chunk']}-{max(sec['start_chunk'], end_chunk)})")

    sections_str = "\n  ".join(section_list) if section_list else "- No clear sections detected."
    
    return (
        f"PDF: \"{title}\"\n"
        f"Stored: {file_path} ({len(chunks_to_store)} chunks indexed)\n"
        f"Source: {url}\n\n"
        f"Abstract: \"{abstract if abstract else 'No abstract detected.'}\"\n\n"
        f"Sections:\n  {sections_str}"
    )


local_tools = [search_web, scrape_web, process_pdf]
