import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './index.css';

interface ToolCall {
  name: string;
  args: any;
}

interface MessageHistory {
  type: string;
  content: string;
  tool_calls?: ToolCall[];
  name?: string;
}

interface WorkerProgress {
  angle: string;
  findings: string;
  sources: string[];
}

interface Progress {
  angles: string[];
  workers: WorkerProgress[];
}

interface Hecho {
  id: number;
  contenido: string;
  fecha: string;
}

interface PdfChunk {
  texto: string;
  source_url: string;
  page: number;
  chunk_index: number;
  fecha: string;
}

type Tab = 'chat' | 'memory' | 'pdfs';

const SUGGESTIONS = [
  '🔬 Summarize recent AI safety papers',
  '📊 Compare transformer architectures',
  '🧪 Find studies on protein folding',
  '📝 Draft a literature review outline',
];

function App() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<{
    role: 'user' | 'agent';
    content: string;
    history?: MessageHistory[];
    progress?: Progress;
    streaming?: boolean;
  }[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>('chat');
  const [hechos, setHechos] = useState<Hecho[]>([]);
  const [hechosLoading, setHechosLoading] = useState(false);
  const [pdfChunks, setPdfChunks] = useState<PdfChunk[]>([]);
  const [pdfChunksLoading, setPdfChunksLoading] = useState(false);
  const [selectedChunk, setSelectedChunk] = useState<PdfChunk | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (activeTab === 'memory') {
      setHechosLoading(true);
      fetch('http://localhost:8000/api/hechos')
        .then((res) => res.json())
        .then((data: { hechos: Hecho[] }) => setHechos(data.hechos))
        .catch(() => setHechos([]))
        .finally(() => setHechosLoading(false));
    }
    if (activeTab === 'pdfs') {
      setPdfChunksLoading(true);
      fetch('http://localhost:8000/api/pdf-chunks')
        .then((res) => res.json())
        .then((data: { chunks: PdfChunk[] }) => setPdfChunks(data.chunks))
        .catch(() => setPdfChunks([]))
        .finally(() => setPdfChunksLoading(false));
    }
  }, [activeTab]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;

    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text },
      { role: 'agent', content: '', streaming: true, progress: { angles: [], workers: [] } },
    ]);
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    setLoading(true);

    // Mutate the last (assistant) message in-place via functional updates
    const updateLast = (updater: (m: typeof messages[number]) => typeof messages[number]) => {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = updater(next[next.length - 1]);
        return next;
      });
    };

    try {
      const res = await fetch('http://localhost:8000/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      });
      if (!res.body) throw new Error('No response body');

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith('data:')) continue;
          const payload = line.slice(5).trim();
          if (!payload) continue;

          let evt: any;
          try {
            evt = JSON.parse(payload);
          } catch {
            continue;
          }

          switch (evt.type) {
            case 'planner':
              updateLast((m) => ({ ...m, progress: { angles: evt.angles, workers: m.progress?.workers || [] } }));
              break;
            case 'direct':
              updateLast((m) => ({ ...m, content: evt.content }));
              break;
            case 'worker_done':
              updateLast((m) => ({
                ...m,
                progress: {
                  angles: m.progress?.angles || [],
                  workers: [
                    ...(m.progress?.workers || []),
                    { angle: evt.angle, findings: evt.findings, sources: evt.sources },
                  ],
                },
              }));
              break;
            case 'token':
              updateLast((m) => ({ ...m, content: m.content + evt.text }));
              break;
            case 'done':
              updateLast((m) => ({ ...m, streaming: false }));
              break;
            case 'error':
              updateLast((m) => ({ ...m, content: `Error: ${evt.message}`, streaming: false }));
              break;
          }
        }
      }
    } catch (error) {
      console.error(error);
      updateLast((m) => ({ ...m, content: 'Error connecting to backend.', streaming: false }));
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const handleTextareaInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  };

  const isMCPTool = (name: string) => name.startsWith('mcp_') || name.includes('hecho');

  const hasMessages = messages.length > 0;

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="logo">
          <div className="logo-dot" />
          <span className="logo-text">RESEARCHER</span>
        </div>
        <nav className="nav-tabs">
          <button
            className={`nav-tab ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            CHAT
          </button>
          <button
            className={`nav-tab ${activeTab === 'memory' ? 'active' : ''}`}
            onClick={() => setActiveTab('memory')}
          >
            MEMORY
          </button>
          <button
            className={`nav-tab ${activeTab === 'pdfs' ? 'active' : ''}`}
            onClick={() => setActiveTab('pdfs')}
          >
            PDFs
          </button>
        </nav>
      </header>

      {/* Main content */}
      {activeTab === 'pdfs' ? (
        <div className="memory-panel">
          <div className="memory-icon">📄</div>
          <h2 className="memory-heading">PDF Chunks</h2>
          <p className="memory-desc">
            Indexed PDF chunks stored in the vector database. Click a card to see the full content.
          </p>
          {pdfChunksLoading ? (
            <div className="typing" style={{ justifyContent: 'center', padding: '2rem' }}>
              <span /><span /><span />
            </div>
          ) : pdfChunks.length === 0 ? (
            <p className="memory-desc">No PDF chunks indexed yet.</p>
          ) : (
            <div className="hechos-list">
              {pdfChunks.map((chunk, i) => (
                <div key={i} className="hecho-card chunk-card" onClick={() => setSelectedChunk(chunk)}>
                  <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
                    <span className="tool-badge local" style={{ fontSize: '0.7rem' }}>Page {chunk.page}</span>
                    <span className="tool-badge mcp" style={{ fontSize: '0.7rem' }}>Chunk {chunk.chunk_index}</span>
                  </div>
                  <p className="hecho-contenido chunk-preview">{chunk.texto}</p>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.5rem' }}>
                    <span className="hecho-fecha" style={{ fontSize: '0.65rem', opacity: 0.6, wordBreak: 'break-all' }}>{chunk.source_url}</span>
                    <span className="hecho-fecha">{chunk.fecha}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {selectedChunk && (
            <div className="modal-overlay" onClick={() => setSelectedChunk(null)}>
              <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                <div className="modal-header">
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                    <span className="tool-badge local" style={{ fontSize: '0.7rem' }}>Page {selectedChunk.page}</span>
                    <span className="tool-badge mcp" style={{ fontSize: '0.7rem' }}>Chunk {selectedChunk.chunk_index}</span>
                  </div>
                  <button className="modal-close" onClick={() => setSelectedChunk(null)}>✕</button>
                </div>
                <div className="modal-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{selectedChunk.texto}</ReactMarkdown>
                </div>
                <div className="modal-footer">
                  <span className="hecho-fecha" style={{ wordBreak: 'break-all' }}>{selectedChunk.source_url}</span>
                  <span className="hecho-fecha">{selectedChunk.fecha}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : activeTab === 'memory' ? (
        <div className="memory-panel">
          <div className="memory-icon">🧠</div>
          <h2 className="memory-heading">Memory</h2>
          <p className="memory-desc">
            Facts the researcher remembers across conversations.
          </p>
          {hechosLoading ? (
            <div className="typing" style={{ justifyContent: 'center', padding: '2rem' }}>
              <span /><span /><span />
            </div>
          ) : hechos.length === 0 ? (
            <p className="memory-desc">No memories yet.</p>
          ) : (
            <div className="hechos-list">
              {hechos.map((h) => (
                <div key={h.id} className="hecho-card">
                  <p className="hecho-contenido">{h.contenido}</p>
                  <span className="hecho-fecha">{h.fecha}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="main-content">
          {!hasMessages ? (
            <div className="welcome">
              <h1 className="welcome-heading">
                Your<br />
                <span className="highlight">Research Agent</span><br />
                is ready.
              </h1>
              <p className="welcome-sub">
                Ask anything — from literature reviews to data analysis.
                The agent decides which tools to use automatically.
              </p>
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    className="suggestion-btn"
                    onClick={() => sendMessage(s.replace(/^.+?\s/, ''))}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="messages">
              {messages.map((msg, idx) => (
                <div key={idx} className={`msg ${msg.role === 'user' ? 'user' : 'assistant'}`}>
                  {msg.role === 'agent' && <span className="msg-label">RESEARCHER</span>}
                  {msg.role === 'agent' && msg.progress && (msg.progress.angles.length > 0 || msg.progress.workers.length > 0) && (
                    <div className="thought-process">
                      {msg.progress.angles.length > 0 && (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginBottom: '0.5rem' }}>
                          <span style={{ fontSize: '0.7rem', opacity: 0.6, alignSelf: 'center' }}>PLAN:</span>
                          {msg.progress.angles.map((a, i) => {
                            const done = i < msg.progress!.workers.length;
                            return (
                              <span key={i} className={`tool-badge ${done ? 'local' : 'mcp'}`} style={{ fontSize: '0.7rem' }}>
                                {done ? '✓' : '…'} {a}
                              </span>
                            );
                          })}
                        </div>
                      )}
                      {msg.progress.workers.map((w, i) => (
                        <div key={`w-${i}`} className="tool-result" style={{ marginBottom: '0.4rem' }}>
                          <strong>✓ {w.angle}</strong>
                          {w.sources.length > 0 && (
                            <div style={{ fontSize: '0.7rem', opacity: 0.7, marginTop: '0.25rem' }}>
                              {w.sources.length} source{w.sources.length === 1 ? '' : 's'}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  {msg.role === 'agent' && msg.history && (
                    <div className="thought-process">
                      {msg.history.map((h, i) => {
                        if (h.tool_calls && h.tool_calls.length > 0) {
                          return h.tool_calls.map((tc, j) => (
                            <div key={`tc-${i}-${j}`} className={`tool-badge ${isMCPTool(tc.name) ? 'mcp' : 'local'}`}>
                              <span>🔌</span>
                              <strong>{isMCPTool(tc.name) ? 'MCP' : 'Local'}:</strong> {tc.name}
                            </div>
                          ));
                        }
                        if (h.type === 'ToolMessage') {
                          return (
                            <div key={`tr-${i}`} className="tool-result">
                              ✓ {h.content}
                            </div>
                          );
                        }
                        return null;
                      })}
                    </div>
                  )}
                  {msg.role === 'agent' && msg.streaming && !msg.content && (
                    <div className="typing"><span /><span /><span /></div>
                  )}
                  {(msg.role === 'user' || msg.content) && (
                    <div className="msg-bubble">
                      {msg.role === 'agent' ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                      ) : (
                        msg.content
                      )}
                    </div>
                  )}
                  {msg.role === 'user' && <span className="msg-label">YOU</span>}
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          )}

          {/* Input bar — only in chat view */}
          <div className="input-bar">
            <form className="input-box" onSubmit={handleSubmit}>
              <textarea
                ref={textareaRef}
                value={input}
                onChange={handleTextareaInput}
                onKeyDown={handleKeyDown}
                placeholder="Ask the researcher anything..."
                disabled={loading}
                rows={1}
              />
              <button type="submit" className="send-btn" disabled={loading || !input.trim()}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="12" y1="19" x2="12" y2="5" />
                  <polyline points="5 12 12 5 19 12" />
                </svg>
              </button>
            </form>
            <div className="input-hint">Enter to send · Shift+Enter for new line</div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
