# AI Database Report Chatbot v2

> **Natural-Language → SQL → Charts → Insights** — powered by a 6-layer RAG pipeline, circuit-breaker LLM routing, and multimodal vision.

Ask questions about your database in plain English. The system generates validated SQL, executes it, and returns results with auto-selected charts, written explanations, confidence scores, and live streaming of the model's reasoning.

---

## ✨ Feature Highlights

| Category | What it does |
|----------|-------------|
| **Hybrid RAG** | ChromaDB semantic search + BM25 keyword search with Reciprocal Rank Fusion |
| **GraphRAG** | NetworkX FK-relationship graph computes correct JOIN paths automatically |
| **Corrective RAG** | Self-healing SQL: auto-repair, retry, zero-row diagnosis, model escalation |
| **Multimodal RAG** | Upload chart/dashboard images → Gemini Vision extracts data requirements → SQL |
| **Multi-Chart Dashboards** | Upload a screenshot with multiple charts → generates separate queries for each |
| **Circuit Breaker** | Qwen (local) → Groq → Gemini failover chain with automatic recovery |
| **BYO Keys** | Bring your own API keys for OpenAI, Anthropic, DeepSeek, Groq, Gemini, Ollama |
| **Live Streaming** | SSE pipeline streams model reasoning tokens and progress to the UI in real time |
| **Smart Charts** | Auto-selects line, area, bar, grouped bar, donut, or animated counter by data shape |
| **Confidence Scoring** | 4-signal weighted score: table relevance, column accuracy, attempt score, row sanity |
| **Multi-Turn Context** | Follow-up questions carry forward table context and previous SQL |
| **Multi-Tenant Security** | Org-level data isolation via `zecure_org_id` filtering |

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
│  Circuit Breaker Router: Qwen → Groq → Gemini     │
└──────────────────┬───────────────────────────────┘
                   │
       ┌───────────▼────────────┐
       │     PostgreSQL DB      │
       │     (234 tables)       │
       └────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

| Tool | Required | Purpose |
|------|----------|---------|
| Python 3.10+ | ✅ | Backend, embeddings, MCP servers |
| Node.js 18+ | ✅ | React frontend |
| PostgreSQL | ✅ | The database being queried |
| Ollama | Optional | Local LLM (Qwen 2.5 Coder 7B) |
| Docker | Optional | Containerized deployment |

### 1. Install dependencies

```bash
pip install -r requirements.txt
cd web && npm install && cd ..
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum set DATABASE_URL
```

### 3. Build the embedding index (run once)

```bash
python embeddings/build_index.py
```

### 4. Start the app

```bash
# Terminal 1 (optional — only if using local Ollama)
ollama serve

# Terminal 2 — Backend
uvicorn backend.main:app --reload --port 8000

# Terminal 3 — React Frontend
cd web && npm run dev
```

Open **http://localhost:5173** in your browser.

### Docker alternative

```bash
cp .env.example .env   # edit with your values
docker compose up --build
# Backend:  http://localhost:8000
# Frontend: http://localhost:8080
```

---

## 📖 Documentation

- **[SETUP_GUIDE.md](SETUP_GUIDE.md)** — Detailed step-by-step setup for new contributors
- **[DOCUMENTATION.md](DOCUMENTATION.md)** — Full technical architecture and engineering report
- **[DEPLOYMENT.md](DEPLOYMENT.md)** — AWS deployment guide (ECS, S3, CloudFront, Terraform)

---

## 🔑 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `FRONTEND_ORIGIN` | ✅ | CORS origin (default: `http://localhost:5173`) |
| `GROQ_API_KEY` | Recommended | Groq cloud fallback (free tier) |
| `GEMINI_API_KEY` | Recommended | Gemini cloud fallback + Vision Agent (free tier) |
| `OLLAMA_MODEL` | Optional | Local model name (default: `qwen2.5-coder:7b`) |
| `PRIMARY_LLM` | Optional | Starting tier: `qwen` (default) or `groq` |
| `RETRIEVAL_TOP_K` | Optional | Tables retrieved per query (default: 8) |

---

## 🛡 Security

- **Read-only SQL**: Every query is validated — `DROP`, `DELETE`, `UPDATE`, `INSERT` are blocked
- **Multi-tenant**: `org_id` → `zecure_org_id` filtering enforced at the prompt level
- **Rate limiting**: 10 requests/minute/IP via SlowAPI
- **BYO keys**: Customer API keys stored encrypted in `data/llm_keys.json` (gitignored)

---

## 📁 Project Structure

```
chatbot_v2/
├── backend/
│   ├── main.py              # FastAPI app + 6-layer pipeline
│   ├── model_router.py      # Circuit-breaker LLM chain
│   ├── llm_key_store.py     # BYO-key storage + Vision Agent
│   ├── hybrid_retriever.py  # ChromaDB + BM25 retrieval
│   ├── schema_graph.py      # NetworkX FK graph
│   ├── query_intelligence.py# Intent detection
│   ├── sql_validator.py     # Security + schema validation
│   ├── self_correction.py   # Auto-repair + retry logic
│   ├── chart_builder.py     # Shape-based chart selection
│   ├── confidence.py        # 4-signal scoring
│   └── Dockerfile
├── embeddings/              # build_index.py, retrieve.py
├── mcp_servers/             # database, schema, report servers
├── web/                     # React SPA (Vite + Zustand)
├── frontend/                # Legacy Streamlit UI
├── deploy/                  # Terraform + CI/CD
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## 📊 Confidence Scoring

Every answer shows 4 progress bars:
- **Table Relevance** — ChromaDB cosine similarity of selected tables
- **Column Accuracy** — 100% if zero schema validation errors
- **Attempt Score** — penalizes 2nd/3rd retries
- **Row Sanity** — flags suspicious 0-row or >10k-row results

Overall ≥80% = High | ≥55% = Medium | <55% = Low
