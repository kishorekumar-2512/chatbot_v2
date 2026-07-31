# 🚀 Setup Guide: Antigravity DB (chatbot_v2)

This guide walks you through setting up, configuring, and running the **AI Database Report Chatbot v2** cleanly with zero errors.

---

## 📋 Prerequisites

| Tool | Required | Version | Download Link |
|------|----------|---------|---------------|
| **Python** | ✅ Yes | 3.10 or higher | [python.org](https://www.python.org/downloads/) |
| **Node.js & npm** | ✅ Yes | Node 18+ | [nodejs.org](https://nodejs.org/) |
| **PostgreSQL** | ✅ Yes | 12+ | [postgresql.org](https://www.postgresql.org/download/) |
| **Ollama** | ⚡ Optional | Latest | [ollama.com](https://ollama.com/) (For local Qwen LLM) |
| **Docker** | ⚡ Optional | Latest | [docker.com](https://www.docker.com/) (For containers) |

---

## 🛠 Step-by-Step Installation

### Step 1: Clone the Repository
```bash
git clone <your-repo-url>
cd chatbot_v2
```

### Step 2: Install Python Backend Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Install Frontend Dependencies
```bash
cd web
npm install
cd ..
```

### Step 4: Configure `.env` File
Copy the template to create your `.env`:
```bash
cp .env.example .env
```

Open `.env` in your text editor and set the required variables:

```env
# ── Database Connection (REQUIRED) ─────────────────────────
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/your_db_name

# ── Frontend CORS Origin (REQUIRED) ─────────────────────────
FRONTEND_ORIGIN=http://localhost:5173

# ── Authentication Flag (CRITICAL) ─────────────────────────
# Default in production is REQUIRE_AUTH=true (JWT verification).
# Set to 'false' for local development to bypass JWT token checks:
REQUIRE_AUTH=false

# ── LLM API Keys (RECOMMENDED) ──────────────────────────────
GROQ_API_KEY=gsk_your_groq_api_key_here
GEMINI_API_KEY=AIzaSy_your_gemini_api_key_here

# ── Optional Model Configs ──────────────────────────────────
PRIMARY_LLM=groq
# Model defaults and supported values are defined in backend/llm_registry.py.
# Add a model override only when a deployment intentionally requires one.
```

> [!IMPORTANT]
> **Local Development Setting:**
> Make sure `REQUIRE_AUTH=false` is set in your local `.env` file unless you have an active JWKS identity provider (Cognito, Auth0) running locally.

---

### Step 5: Build the Semantic Embedding Index

Before running the application for the first time, introspect your PostgreSQL schema and build the ChromaDB vector index:

```bash
python -m embeddings.build_index
```

- This reads your PostgreSQL tables, column names, comments, and relationships.
- It builds incremental embeddings inside `./embeddings/chroma_store/`.
- Re-run this command whenever you alter or add new database tables.

---

### Step 6: Enable Row-Level Security (Optional)

If your database hosts multi-tenant data with a `zecure_org_id` column:
```bash
# Option A: Pass your DATABASE_URL directly:
psql "$DATABASE_URL" -f migrations/001_enable_rls.sql

# Option B: Pass host, user, and your actual database name:
psql -h localhost -U postgres -d your_actual_db_name -f migrations/001_enable_rls.sql
```

---

### Step 7: Run the Application

Open **two terminal windows**:

#### Terminal 1: FastAPI Backend
```bash
uvicorn backend.main:app --reload --port 8000
```
- Health check: `http://localhost:8000/health`
- Swagger docs: `http://localhost:8000/docs`

#### Terminal 2: React Web Frontend
```bash
cd web
npm run dev
```
- Open **http://localhost:5173** in your web browser.

---

## 🐳 Docker Deployment (Alternative)

If you prefer containerized deployment:

```bash
cp .env.example .env
# Edit .env with your DATABASE_URL, GROQ_API_KEY, GEMINI_API_KEY, and REQUIRE_AUTH=false

docker compose up --build
```

- Backend API: `http://localhost:8000`
- React Web App: `http://localhost:8080`

---

## 🔍 Troubleshooting & Verification

| Issue | Solution |
| :--- | :--- |
| **`401 Unauthorized` on API requests** | Set `REQUIRE_AUTH=false` in your `.env` file for local development. |
| **`Database Connection Error`** | Verify `DATABASE_URL` format and test connectivity with `psql`. |
| **`ChromaDB / Embeddings Warning`** | Run `python -m embeddings.build_index` to build the vector store. |
| **`Groq API Key error`** | Set `GROQ_API_KEY` in `.env` or configure local Ollama. |
