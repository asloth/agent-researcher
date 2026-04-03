import sys
import os
from dotenv import load_dotenv

# Carga las variables de entorno desde un archivo .env (vital para OPENAI_API_KEY)
load_dotenv()

# Agregamos la ruta base para poder importar herramientas del cliente si fuera necesario
sys.path.append(os.path.dirname(__file__))

def search_web(query: str) -> str:
    """Search the web for information. Returns a list of results with URLs and snippets.
   
      After getting results, you MUST process the URLs:
      - PDF URLs (.pdf) → use process_pdf
      - Web page URLs → use scrape_web
      """
    from tavily import TavilyClient
    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    response = client.search(
        query=query,
        search_depth="advanced",
        num_results=10,
    )
    return response['results'] 

def scrape_web(urls: list[str], query: str) -> str:                                                                                                                                                                                                
    """Extract and summarize content from HTML web pages. Pass all page URLs in one call.
   
      DO NOT use for PDF links — PDFs must go through process_pdf instead.
      Use 'query' to focus the summary on what's relevant to the research.
      """
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
    Download a PDF from a URL, split it into chunks, and index it in the vector database.
   
      Use this when a URL points to a PDF file (contains .pdf in the URL).
      Returns a structural map with title, abstract, sections, and chunk ranges.
      After indexing, use rag_pdf to query specific content from the PDF.
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
        try:
            with httpx.Client(follow_redirects=True, timeout=60.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                with open(file_path, "wb") as f:
                    f.write(resp.content)
        except httpx.HTTPStatusError as e:
            return f"❌ Could not download PDF (HTTP {e.response.status_code}): {url}"
        except httpx.RequestError as e:
            return f"❌ Could not download PDF (connection error): {url}"

    try:
        pages = pymupdf4llm.to_markdown(file_path, page_chunks=True)
    except Exception as e:
        return f"❌ Could not parse PDF: {url} — {str(e)}"

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


def rag_pdf_local(url: str, query: str) -> str:
    """Search within a previously indexed PDF by semantic query.
    Use this after process_pdf to find specific content in a PDF you already indexed.
    Requires the same 'url' that was passed to process_pdf.
    """
    import lancedb
    from openai import OpenAI

    db_path = os.path.join(os.path.dirname(__file__), "..", "mcp_hechos", "hechos_lancedb")
    db = lancedb.connect(db_path)

    if "pdf_chunks" not in db.table_names():
        return "❌ No PDFs have been indexed yet."

    try:
        openai_client = OpenAI()
        query_vec = openai_client.embeddings.create(
            input=[query], model="text-embedding-3-small"
        ).data[0].embedding

        table = db.open_table("pdf_chunks")
        results = table.search(query_vec).where(f"source_url = '{url}'").limit(5).to_pandas()

        if results.empty:
            return f"❌ No relevant results found for query in PDF: {url}"

        output = []
        for _, row in results.iterrows():
            header = f"[Page {row['page']}, Chunk {row['chunk_index']}]"
            output.append(f"{header}\n{row['texto']}")

        return f"--- Semantic Search Results for '{query}' ---\n\n" + "\n\n---\n\n".join(output)
    except Exception as e:
        return f"❌ Error querying PDF: {str(e)}"


local_tools = [search_web, scrape_web, process_pdf, rag_pdf_local]
