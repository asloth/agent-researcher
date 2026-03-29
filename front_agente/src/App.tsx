import { useState, useRef, useEffect } from 'react';
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

interface ChatResponse {
  response: string;
  history: MessageHistory[];
}

type Tab = 'chat' | 'memory';

const SUGGESTIONS = [
  '🔬 Summarize recent AI safety papers',
  '📊 Compare transformer architectures',
  '🧪 Find studies on protein folding',
  '📝 Draft a literature review outline',
];

function App() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<{ role: 'user' | 'agent'; content: string; history?: MessageHistory[] }[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>('chat');
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;

    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    setLoading(true);

    try {
      const res = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text })
      });
      const data: ChatResponse = await res.json();
      setMessages((prev) => [...prev, { role: 'agent', content: data.response, history: data.history }]);
    } catch (error) {
      console.error(error);
      setMessages((prev) => [...prev, { role: 'agent', content: 'Error connecting to backend.' }]);
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
        </nav>
      </header>

      {/* Main content */}
      {activeTab === 'memory' ? (
        <div className="memory-panel">
          <div className="memory-icon">🧠</div>
          <h2 className="memory-heading">Memory</h2>
          <p className="memory-desc">
            Memory allows the researcher to remember context across conversations.
            This feature is coming soon.
          </p>
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
                  <div className="msg-bubble">{msg.content}</div>
                  {msg.role === 'user' && <span className="msg-label">YOU</span>}
                </div>
              ))}
              {loading && (
                <div className="msg assistant">
                  <span className="msg-label">RESEARCHER</span>
                  <div className="typing">
                    <span /><span /><span />
                  </div>
                </div>
              )}
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
