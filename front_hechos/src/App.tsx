import { useEffect, useState } from 'react';
import './index.css';

interface Hecho {
  id: number;
  contenido: string;
  fecha: string;
}

function App() {
  const [hechos, setHechos] = useState<Hecho[]>([]);

  useEffect(() => {
    // Consulta a la instancia de la API LangGraph que actúa de Proxy de la BD local
    fetch('http://localhost:8000/api/hechos')
      .then((res) => res.json())
      .then((data) => setHechos(data.hechos || []))
      .catch((err) => console.error(err));
  }, []);

  return (
    <div className="container">
      <header>
        <h1>📚 Base de Hechos (MCP)</h1>
        <p>Visualización directa de la base de datos gestionada por el MCP.</p>
      </header>
      <main>
        {hechos.length === 0 ? (
          <p className="empty-state">No hay hechos registrados todavía. ¡Conversa con el Agente para guardar nuevos hechos!</p>
        ) : (
          <table className="hechos-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Fecha</th>
                <th>Contenido</th>
              </tr>
            </thead>
            <tbody>
              {hechos.map((hecho) => (
                <tr key={hecho.id}>
                  <td>{hecho.id}</td>
                  <td>{new Date(hecho.fecha).toLocaleString()}</td>
                  <td>{hecho.contenido}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>
    </div>
  );
}

export default App;
