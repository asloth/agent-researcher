# Proyecto Educacional: Frontend Hechos

Este es un visor simple desarrollado en **React, Vite y TypeScript**.

## Objetivo
El objetivo de este frontend es mostrar el estado actual de la **Base de Datos local (SQLite)** gestionada por el MCP (`mcp_hechos`).
Contiene una tabla sencilla que despliega todos los "Hechos" que el Agente ha decidido guardar.

## Arquitectura y Conexión
1. La aplicación hace un `fetch` a `http://localhost:8000/api/hechos`.
2. Esta ruta es proporcionada por el servidor FastAPI (`agente_langgraph`), el cual en este caso sirve como proxy para leer `hechos.db`.

## ¿Cómo ejectuarlo?
Asegúrate de haber corrido `npm install` previamente.

```bash
# Arranca el servidor de desarrollo de Vite (usualmente en puerto 5173 o 5174)
npm run dev
```

Este proyecto está estilizado libremente con CSS nativo (`index.css`), ofreciendo una estética moderna con UI Glassmorphism y temas oscuros.
