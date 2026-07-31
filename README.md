# AI Database Report Chatbot v2 (Antigravity DB)

> **Natural-Language → SQL → Charts → Insights** — powered by a 6-layer RAG pipeline, circuit-breaker LLM routing, PostgreSQL RLS security, and multimodal vision.

Ask questions about your database in plain English. The system generates validated SQL, executes it, and returns results with auto-selected charts, written explanations, confidence scores, and live streaming of the model's reasoning.

---

## ✨ Feature Highlights

| Category | What it does |
|----------|-------------|
| **Hybrid RAG** | ChromaDB semantic search + BM25 keyword search with Reciprocal Rank Fusion |
| **GraphRAG** | NetworkX FK-relationship graph computes correct JOIN paths automatically |
| **Corrective RAG** | Self-healing SQL: auto-repair, retry, zero-row diagnosis, model escalation |
| **Multimodal RAG** | Upload chart/dashboard images → Gemini Vision extracts data requirements → SQL |
| **Circuit Breaker** | Groq (primary) → Gemini (fallback 1) → Qwen/Ollama (fallback 2) failover chain with 300s auto-recovery across all models |
| **BYO Keys** | Bring your own API keys for OpenAI, Anthropic, DeepSeek, Groq, Gemini, Ollama |
| **Live Streaming** | SSE pipeline streams model reasoning tokens and progress to the UI in real time |
| **Smart Charts** | Auto-selects line, area, bar, grouped bar, donut, or animated counter by data shape |
| **Confidence Scoring** | 4-signal weighted score: table relevance, column accuracy, attempt score, row sanity |
| **Multi-Tenant Security** | App-level `zecure_org_id` AST filtering + optional Postgres Row-Level Security (RLS) policies |
| **Fail-Secure Auth** | Pluggable JWT/OIDC authentication (`REQUIRE_AUTH=true` by default, set `false` for local dev) |

---

## 🏗 Architecture Overview

```
┌──────────────────────────────────────────────────┐
│                   React SPA (Vite)                │
│  Zustand state · SSE consumer · Plotly charts     │
└──────────────────┬───────────────────────────────┘
                   │ SSE stream
┌──────────────────▼───────────────────────────────┐
│              FastAPI Backend                       │
│                                                    │
│  L0  Meta bypass (zero-LLM, schema cache)          │
│  L1  Query intelligence (intent detection)         │
│  L2  Hybrid retrieval (ChromaDB + BM25 + RRF)      │
│  L3  Schema graph (NetworkX shortest-path JOINs)   │
│  L4  SQL generation (chain-of-thought prompt)      │
│  L5  Validation + self-correction + auto-repair    │
│  L6  Multimodal RAG (Gemini Vision Agent)          │
│                                                    │
│  Circuit Breaker Router: Groq → Gemini → Qwen     │
└──────────────────┬───────────────────────────────┘
                   │
       ┌───────────▼────────────┐
       │     PostgreSQL DB      │
       │  (App AST + RLS Rules) │
       └────────────────────────┘
```

---

## 🚀 Quick Start (Clean & Error-Free)

### Prerequisites

| Tool | Required | Purpose |
|------|----------|---------|
| Python 3.10+ | ✅ | Backend, embeddings, indexer |
| Node.js 18+ | ✅ | React frontend |
| PostgreSQL | ✅ | Target relational database |
| Ollama | Optional | Local LLM (`qwen2.5-coder:7b`) |
| Docker | Optional | Containerized deployment |

### 1. Install dependencies

```bash
# Python backend dependencies
pip install -r requirements.txt

# React frontend dependencies
cd web && npm install && cd ..
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit your `.env` file:
```env
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/your_database
FRONTEND_ORIGIN=http://localhost:5173
REQUIRE_AUTH=false
GROQ_API_KEY=your_groq_key_here
GEMINI_API_KEY=your_gemini_key_here
```
*(Note: Set `REQUIRE_AUTH=false` for local dev so authentication is bypassed. Set `true` in production with JWT JWKS).*

### 3. Build the embedding index

```bash
python -m embeddings.build_index
```
*(Runs an incremental sync introspecting your PostgreSQL schema and building ChromaDB vector embeddings).*

### 4. Enable Database Row-Level Security (Optional)

```bash
psql -d your_database -f migrations/001_enable_rls.sql
```

### 5. Start the application

```bash
# Terminal 1 — FastAPI Backend API
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — React Web Frontend
cd web && npm run dev
```

Open **http://localhost:5173** in your browser.

---

## 🐳 Running with Docker Compose

```bash
cp .env.example .env   # configure DATABASE_URL, GROQ_API_KEY, GEMINI_API_KEY, REQUIRE_AUTH=false
docker compose up --build
```
- Backend: **http://localhost:8000**
- React Web UI: **http://localhost:8080**

---

## 📖 Documentation & Guides

- **[SETUP_GUIDE.md](SETUP_GUIDE.md)** — Detailed step-by-step setup guide for new developers
- **[DEPLOYMENT.md](DEPLOYMENT.md)** — AWS ECS, Fargate, Terraform, and CI/CD deployment guide
- **[migrations/001_enable_rls.sql](migrations/001_enable_rls.sql)** — PostgreSQL Row-Level Security migration script

---

## 🛡 Security Policy

- **Read-Only Enforcer**: All write/DDL keywords (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, etc.) are blocked at AST validation.
- **Fail-Secure Auth**: `REQUIRE_AUTH` defaults to `true` for production JWT/OIDC safety.
- **Database RLS**: Multi-tenant isolation enforced both in application logic and optionally via Postgres RLS policies (`zecure_org_id`).
- **Secrets Cleanliness**: `.env` and `.env.save` are strictly gitignored and excluded from repositories.
