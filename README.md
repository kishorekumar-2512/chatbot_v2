# AI Database Report Chatbot v2 (Antigravity DB)

> **Natural-Language → SQL → Charts → Insights** — powered by a 6-layer RAG pipeline, circuit-breaker LLM routing, PostgreSQL RLS security, and multimodal vision.

## Overview

This project was built during an internship as an advanced, end-to-end AI Database Chatbot. It allows users to ask questions about their database in plain English, securely generating and executing validated SQL. It then returns the results accompanied by auto-selected charts, written explanations, confidence scores, and a live stream of the model's reasoning.

**Key Features:**
- **Hybrid & Graph RAG:** Combines ChromaDB semantic search, BM25 keyword search, and a NetworkX FK-relationship graph for perfect JOIN path resolution.
- **Corrective RAG:** Auto-repairs failing SQL queries, diagnoses zero-row outputs, and intelligently escalates models.
- **Multimodal RAG:** Extract data requirements directly from uploaded chart or dashboard images using Gemini Vision.
- **Circuit Breaker Routing:** Primary (Groq) → Fallback (Gemini) → Fallback 2 (Local Qwen) with seamless auto-recovery.
- **Multi-Tenant Security:** Features Postgres Row-Level Security (RLS) policies and app-level AST filtering (`zecure_org_id`).
- **Live Streaming & Smart Charts:** Real-time reasoning stream to the UI, automatically picking the best chart type (line, area, bar, donut, etc.) for the data payload.

---

## Tech Stack

- **Backend:** Python 3.10+, FastAPI, Uvicorn, Pydantic
- **Frontend:** React, Vite, Zustand, Plotly (for charts)
- **Database:** PostgreSQL, psycopg2
- **AI & RAG:** ChromaDB (Vector DB), rank-bm25 (Keyword Search), sentence-transformers, NetworkX (Schema Graph)
- **LLM APIs:** Groq API, Google Gemini API, Ollama (for local offline LLMs)
- **Security:** PyJWT, Cryptography, Postgres RLS

---

## Architecture

The system is separated into a React Single Page Application and a robust FastAPI backend.

```text
┌──────────────────────────────────────────────────┐
│                   React SPA (Vite)                │
│  Zustand state · SSE consumer · Plotly charts     │
└──────────────────┬───────────────────────────────┘
                   │ SSE Stream (Reasoning & Results)
┌──────────────────▼───────────────────────────────┐
│              FastAPI Backend                       │
│                                                    │
│  L0: Meta bypass (schema cache)                    │
│  L1: Query intelligence & intent detection         │
│  L2: Hybrid retrieval (ChromaDB + BM25 + RRF)      │
│  L3: Schema graph (Shortest-path JOINs via NetworkX│
│  L4: SQL generation (Chain-of-thought prompting)   │
│  L5: Validation, self-correction & auto-repair     │
│  L6: Multimodal RAG (Gemini Vision Agent)          │
│                                                    │
│  Circuit Breaker: Groq → Gemini → Local Qwen       │
└──────────────────┬───────────────────────────────┘
                   │
       ┌───────────▼────────────┐
       │     PostgreSQL DB      │
       │  (App AST + RLS Rules) │
       └────────────────────────┘
```

---

## Prerequisites

Ensure you have the following installed before starting:
- **Python:** 3.10 or higher
- **Node.js:** 18 or higher
- **PostgreSQL:** Running locally or remotely
- **Accounts / API Keys:**
  - A [Groq](https://console.groq.com/keys) API Key (Primary)
  - A [Google Gemini](https://aistudio.google.com/app/apikey) API Key (Fallback / Vision)
- **Ollama (Optional):** For local fallback (e.g., `qwen2.5-coder:7b`)

---

## Installation

**1. Clone the repository**
```bash
git clone https://github.com/kishorekumar-2512/chatbot_v2.git
cd chatbot_v2
```

**2. Install Backend Dependencies**
```bash
pip install -r requirements.txt
```

**3. Install Frontend Dependencies**
```bash
cd web
npm install
cd ..
```

**4. Set up Environment Variables**
Copy the example environment file to `.env`:
```bash
cp .env.example .env
```
Fill out the variables in `.env` (see the Environment Variables table below for details).

**5. Database & Schema Initialization**
Enable Row-Level Security (optional, for multi-tenancy):
```bash
psql "postgresql://postgres:yourpassword@localhost:5432/intern_db" -f migrations/001_enable_rls.sql
```

Build the semantic search and schema embedding index:
```bash
python -m embeddings.build_index
```

---

## Running the app locally

Start the services in two separate terminal windows.

**Backend (Terminal 1):**
```bash
# Starts the FastAPI backend on port 8000
uvicorn backend.main:app --reload --port 8000
```

**Frontend (Terminal 2):**
```bash
# Starts the React development server
cd web
npm run dev
```

The frontend will be available at **http://localhost:5173** and the backend API docs at **http://localhost:8000/docs**.

---

## Folder Structure

```text
chatbot_v2/
├── backend/            # FastAPI backend application
│   ├── main.py         # App entry point & HTTP endpoints
│   ├── llm_orchestrator.py  # Central reasoning and LLM pipeline manager
│   ├── hybrid_retriever.py  # ChromaDB + BM25 RAG implementation
│   ├── schema_graph.py # NetworkX graph for automated foreign key JOINs
│   └── ...
├── web/                # React SPA Frontend (Vite)
│   ├── src/            # React components, state, API callers
│   └── package.json    # Node dependencies
├── frontend/           # Legacy Streamlit UI (optional alternative)
│   └── app.py
├── embeddings/         # Scripts for embedding generation & Chroma store
├── data/               # Local user data, failed requests, key storage
├── migrations/         # PostgreSQL schema and RLS setup scripts
├── .env.example        # Reference for environment variables
├── requirements.txt    # Python dependencies
└── docker-compose.yml  # Docker deployment configuration
```

---

## Usage

1. **Access the Web Interface:** Open `http://localhost:5173` in your browser.
2. **Settings:** Navigate to the Settings tab to provide your API keys if you didn't define them in the `.env` file (the app supports Bring-Your-Own-Keys).
3. **Ask a Question:** In the chat input, try prompts like:
   - *"Show me a bar chart of the top 5 customers by revenue this month."*
   - *"What is our total sales volume broken down by region?"*
4. **Multimodal:** Upload a picture of a legacy dashboard chart and ask the bot to recreate it using live data.
5. **View Reasoning:** Expand the "Reasoning" tab on a response to watch the model's step-by-step logic, schema retrieval, and SQL generation streamed in real time.

---

## Environment Variables

| Variable Name | Description | Required | Default |
|---------------|-------------|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string | **Yes** | `postgresql://...` |
| `PRIMARY_LLM` | Primary model provider (`groq`, `gemini`, `qwen`) | No | `groq` |
| `GROQ_API_KEY` | Your Groq API Key | No | |
| `GEMINI_API_KEY` | Your Google Gemini API Key | No | |
| `OLLAMA_BASE_URL` | Local URL if running Ollama | No | `http://localhost:11434` |
| `CHROMA_DB_PATH` | Path to store ChromaDB embeddings | No | `./embeddings/chroma_store` |
| `RETRIEVAL_TOP_K` | Number of schema documents to retrieve | No | `8` |
| `REQUIRE_AUTH` | Enable/disable JWT authentication | No | `false` |
| `FRONTEND_ORIGIN_REACT` | Allowed CORS origin for the Vite app | No | `http://localhost:5173` |

*(See `.env.example` for the full list of advanced configurables like caching intervals, JWT endpoints, and connection pooling).*

---

## Troubleshooting

- **Error: `psycopg2.OperationalError: connection to server at "localhost"... failed`**
  - **Fix:** Ensure PostgreSQL is running, and the credentials in `DATABASE_URL` are correct.
- **Error: Vector DB / ChromaDB throwing dimension mismatch**
  - **Fix:** Delete the `./embeddings/chroma_store` folder and rerun `python -m embeddings.build_index` to regenerate cleanly.
- **Error: Ollama silently fails or truncates responses**
  - **Fix:** Ensure `OLLAMA_NUM_CTX` in your `.env` is set to `8192` or higher.
- **Error: Frontend won't connect to Backend (Network Error)**
  - **Fix:** Ensure `BACKEND_URL` is set or default localhost ports match. Check backend terminal for CORS issues; ensure `FRONTEND_ORIGIN_REACT` includes your Vite server port.

---

## Future Improvements

- Add support for SQLite and MySQL dialects.
- Enhance the Vision Agent to parse multi-chart dashboards into parallel SQL execution branches.
- Implement conversational history context awareness (memory) for follow-up questions.
- Introduce caching for identical SQL query executions to save database load.

---

## License / Author / Contact

- **Author:** Kishore Kumar
- **Role:** Software Engineering Intern
- **Project Scope:** Proof of concept / Internship Deliverable
- **Contact:** [GitHub Profile](https://github.com/kishorekumar-2512)

*(This project is not currently licensed for public redistribution)*
