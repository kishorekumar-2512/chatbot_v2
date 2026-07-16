# 🚀 Setup Guide for New Contributors / Recipients

This is what someone needs to do after receiving the **AI Database Report Chatbot v2** project.

---

## Prerequisites (Install These First)

| Tool | Why it's needed | Install link |
|------|----------------|-------------|
| **Python 3.10+** | Backend (FastAPI), MCP servers, embeddings | [python.org](https://www.python.org/downloads/) |
| **Node.js 18+** & npm | React frontend (`web/` folder) | [nodejs.org](https://nodejs.org/) |
| **PostgreSQL** | The database the chatbot queries | [postgresql.org](https://www.postgresql.org/download/) |
| **Ollama** *(optional)* | Local LLM (Qwen) — only if using local model | [ollama.com](https://ollama.com/) |
| **Docker** *(optional)* | If they want to run via containers instead | [docker.com](https://www.docker.com/) |
| **Git** | To clone the repo | [git-scm.com](https://git-scm.com/) |

---

## Step-by-Step Setup

### Step 1: Clone / Download the Project

```bash
git clone <your-repo-url>
cd chatbot_v2
```

### Step 2: Install Python Dependencies

```bash
pip install -r requirements.txt
```

> [!NOTE]
> `sentence-transformers` will auto-download the `all-MiniLM-L6-v2` model (~80 MB) on first run. After that it works fully offline.

### Step 3: Install React Frontend Dependencies

```bash
cd web
npm install
cd ..
```

### Step 4: Create the `.env` File

```bash
cp .env.example .env
```

Then **edit `.env`** and fill in these values:

| Variable | Required? | What to put |
|----------|-----------|-------------|
| `DATABASE_URL` | ✅ **Yes** | Their own PostgreSQL connection string, e.g. `postgresql://postgres:password@localhost:5432/their_db` |
| `GROQ_API_KEY` | ⚡ Recommended | Free key from [console.groq.com](https://console.groq.com) (no credit card) |
| `GEMINI_API_KEY` | ⚡ Recommended | Free key from [aistudio.google.com](https://aistudio.google.com) (no credit card) |
| `OLLAMA_MODEL` | Only if using Ollama | Default is `qwen2.5-coder:7b` |
| `PRIMARY_LLM` | Optional | `groq` (default, cloud) or `qwen` (local Ollama) |

> [!IMPORTANT]
> **They MUST have their own database** — the chatbot generates SQL against a live PostgreSQL database. Without `DATABASE_URL` pointing to a real DB, nothing works.

> [!TIP]
> If they skip Groq + Gemini keys, the chatbot still works with just Ollama locally, but the circuit-breaker fallback chain won't have cloud models to fall back to.

### Step 5: Set Up the Database

They need a PostgreSQL database with tables and data. If you're sharing your schema:
- Export your schema: `pg_dump --schema-only -d your_db > schema.sql`
- They import it: `psql -d their_db < schema.sql`
- Optionally share sample data too

### Step 6: Build the Semantic Embedding Index

```bash
python embeddings/build_index.py
```

> [!IMPORTANT]
> **This must run once before the app works.** It reads the database schema and creates vector embeddings in `./embeddings/chroma_store/`. Must be re-run if the database schema changes.

### Step 7: (Optional) Pull the Ollama Model

Only if they want local LLM inference:

```bash
ollama pull qwen2.5-coder:7b
```

> Needs ~4.5 GB of disk space and a decent GPU/RAM. If their machine can't handle 7B, they can use `qwen2.5:3b` instead (set `OLLAMA_MODEL=qwen2.5:3b` in `.env`).

### Step 8: Run the App

They need **3 terminals** (or 2 if not using Ollama):

```bash
# Terminal 1 (only if using Ollama)
ollama serve

# Terminal 2 — Backend API
uvicorn backend.main:app --reload --port 8000

# Terminal 3 — Streamlit Frontend
streamlit run frontend/app.py
```

Then open **http://localhost:8501** in the browser.

#### Alternative: React Frontend (instead of Streamlit)

```bash
# Terminal 3 — React frontend (instead of Streamlit)
cd web
npm run dev
```

Then open **http://localhost:5173** in the browser.

---

## Alternative: Run with Docker (Simpler)

If they have Docker installed, they can skip most of the above:

```bash
cp .env.example .env
# Edit .env with DATABASE_URL, GROQ_API_KEY, GEMINI_API_KEY

docker compose up --build
```

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:8080`

---

## Quick Checklist Summary

```
✅ Python 3.10+ installed
✅ Node.js 18+ installed (for React frontend)
✅ PostgreSQL database running with tables
✅ .env file created with DATABASE_URL filled in
✅ At least one LLM configured (Groq key OR Ollama installed)
✅ pip install -r requirements.txt
✅ npm install (in web/ folder)
✅ python embeddings/build_index.py (run once)
✅ Start backend + frontend
```

---

## Common Issues

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` again |
| Embedding build fails | Check `DATABASE_URL` in `.env` — must point to a live, reachable database |
| "All models failed" | No LLM is available — add a `GROQ_API_KEY` or start `ollama serve` |
| Port 8000 in use | Another app is using it — kill that process or change the port |
| `mcp` import error | Need Python 3.10+ (MCP library requires it) |

---

## What They Do NOT Need

- ❌ Your `.env` file (has your private keys — they make their own)
- ❌ Your `embeddings/chroma_store/` folder (they rebuild it from their own DB)
- ❌ Your `feedback_log.jsonl` (your usage data)
- ❌ Your `data/llm_keys.json` (your stored API keys)
- ❌ AWS account (only needed for cloud deployment, not local dev)
