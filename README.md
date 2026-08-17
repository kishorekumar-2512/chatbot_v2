# AI Database Report Chatbot v2 (Antigravity DB)

> **Natural-Language → SQL → Charts → Insights** — Enterprise-grade NL-to-SQL platform powered by a 6-layer Hybrid RAG pipeline, circuit-breaker LLM routing, Model Context Protocol (MCP) subprocesses, multi-tenant security, and zero-downtime Blue-Green production deployment.

---

## 📑 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [6-Layer Accuracy Pipeline](#6-layer-accuracy-pipeline)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Local Development Setup](#local-development-setup)
- [Model Context Protocol (MCP)](#model-context-protocol-mcp)
- [Production Blue-Green Deployment](#production-blue-green-deployment)
- [Cloud Database Migration](#cloud-database-migration)
- [CI/CD Pipeline](#cicd-pipeline)
- [Environment Configuration](#environment-configuration)
- [Troubleshooting & Diagnostics](#troubleshooting--diagnostics)
- [Author & Credits](#author--credits)

---

## 🌟 Overview

**Antigravity DB (Chatbot v2)** is an end-to-end conversational database assistant designed for high-accuracy analytics. Users query business databases using natural English, and the platform generates validated, read-only SQL, executes it against PostgreSQL, and renders interactive charts, statistical insights, and streamed reasoning explanations.

The system is architected for **zero downtime**, supporting **Blue-Green releases**, automated schema embeddings, multi-tenant Bring-Your-Own-Key (BYO) credentials, and autonomous query repair.

---

## 🚀 Key Features

- **6-Layer Hybrid & Graph RAG:** Combines Dense Vector Search (ChromaDB + SentenceTransformers), Sparse Keyword Search (BM25 with Reciprocal Rank Fusion), and FK Schema Graph pathfinding (NetworkX) for reliable multi-table JOIN synthesis.
- **Circuit-Breaker LLM Routing:** Fault-tolerant multi-tier fallback chain:
  `Tenant BYO Keys` → `Groq (Primary)` → `Gemini (Fallback 1)` → `Local Ollama (Fallback 2)`
  with per-provider circuit breakers, exponential backoff, and timed auto-recovery.
- **Model Context Protocol (MCP) Integration:** Standardized MCP host managing 3 isolated subprocesses (`database_server`, `schema_server`, `report_server`) over JSON-RPC stdio.
- **Multimodal Dashboard Vision:** Upload pictures of dashboards or diagrams; Google Gemini Vision extracts visual requirements and translates them into live queries.
- **Self-Correction & Zero-Row Diagnosis:** Automatically identifies query errors, parses diff-based previous attempt history, diagnoses zero-row filter mismatches, and auto-repairs SQL.
- **Multi-Tenant Security & RLS:** AST SQL parsing restricts execution to read-only queries with enforced tenant scoping (`zecure_org_id`) and PostgreSQL Row-Level Security (RLS).
- **Interactive UI & Real-Time SSE:** React 19 SPA with Server-Sent Events (SSE) reasoning streams, dynamic Plotly visualizations, PDF report exports, and an in-app Schema Explorer.
- **Blue-Green Deployment Infrastructure:** Dual containerized environments with Nginx reverse proxy routing, atomic cutover, and instant zero-downtime rollback.

---

## 🏗️ System Architecture

```
                                Public User Traffic (:80 / :443)
                                               │
                                               ▼
                             ┌───────────────────────────────────┐
                             │  Host Nginx Reverse Proxy / LB    │
                             │  (/etc/nginx/conf.d/upstream.conf)│
                             └─────────────────┬─────────────────┘
                                               │
                       ┌───────────────────────┴───────────────────────┐
                       │ (Active Upstream)                             │ (Idle / Staging)
                       ▼                                               ▼
             ┌───────────────────┐                           ┌───────────────────┐
             │    BLUE STACK     │                           │   GREEN STACK     │
             │  web-blue   :8081 │                           │  web-green  :8082 │
             │  backend-blue:8001│                           │  backend-green:8002│
             └─────────┬─────────┘                           └─────────┬─────────┘
                       │                                               │
                       └───────────────────────┬───────────────────────┘
                                               │
                                               ▼
                     ┌───────────────────────────────────────────────────┐
                     │              SHARED STATE & DATA LAYER            │
                     │  • Managed Cloud PostgreSQL (RDS / Supabase)      │
                     │  • Shared ChromaDB Volume (chatbot_chroma_data)   │
                     │  • Shared Key Store Volume (chatbot_key_data)     │
                     │  • Shared Feedback & Reports Volumes              │
                     └───────────────────────────────────────────────────┘
```

---

## 🔬 6-Layer Accuracy Pipeline

Every query passes through a multi-stage deterministic pipeline:

```text
User Question ──► L1: Query Intelligence ──► L2: Hybrid Retrieval ──► L3: Schema Graph
                        │                          │                        │
                        ▼                          ▼                        ▼
                 Intent & Entities          ChromaDB + BM25           NetworkX JOINs
                                                                            │
SQL Execution ◄── L6: Self-Correction ◄── L5: SQL Validation ◄── L4: Context Assembly
      │                 │                          │                        │
      ▼                 ▼                          ▼                        ▼
Charts & Insights  Retry & Repair            AST & RLS Guard          Prompt + DDL + DB Values
```

1. **L1 — Query Intelligence:** Classifies intent (analytical, transactional, conversational) and extracts table/column entities.
2. **L2 — Hybrid Retrieval:** Queries ChromaDB embeddings + BM25 keyword index to select top $K$ relevant tables.
3. **L3 — Schema Graph:** Computes shortest foreign-key join paths across disconnected tables using NetworkX.
4. **L4 — Context Assembly:** Samples distinct database column values and injects dynamic few-shot examples.
5. **L5 — SQL Generation & Validation:** Generates SQL via circuit-breaker LLMs and validates table/column existence against information schema metadata.
6. **L6 — Self-Correction Loop:** Executes query; if errors or zero rows occur, feeds diff context back into the LLM for automatic query rewriting.

---

## 💻 Tech Stack

### Backend
- **Framework:** Python 3.11, FastAPI, Uvicorn, Pydantic v2
- **Database Connector:** Psycopg2 Connection Pool, PostgreSQL
- **RAG & NLP:** ChromaDB, SentenceTransformers (`all-MiniLM-L6-v2`), Rank-BM25, NetworkX
- **MCP Framework:** Model Context Protocol (MCP) SDK 1.2+
- **Reporting & Visuals:** Pandas, Plotly, Kaleido, FPDF2

### Frontend
- **Framework:** React 19, Vite 6, TailwindCSS
- **State Management:** Zustand
- **Visuals & Icons:** Plotly.js (`react-plotly.js`), Lucide React
- **Container Server:** Nginx 1.27 Alpine

### Infrastructure & CI/CD
- **Containerization:** Docker, Docker Compose (Blue/Green)
- **Reverse Proxy:** Nginx with SSE streaming support
- **Registry & CI/CD:** GitHub Actions, GitHub Container Registry (GHCR)

---

## 📁 Repository Structure

```text
chatbot_v2/
├── backend/                        # FastAPI core application
│   ├── main.py                     # HTTP & SSE streaming endpoints
│   ├── llm_orchestrator.py         # Request-scoped router, circuit breakers & failure logs
│   ├── llm_registry.py             # Active model catalog for Groq, Gemini, OpenAI, Claude
│   ├── llm_config.py               # Live runtime configuration snapshotting
│   ├── llm_key_store.py            # Encrypted tenant BYO key persistence
│   ├── hybrid_retriever.py         # Dense vector + BM25 retrieval
│   ├── schema_graph.py             # NetworkX FK join graph builder
│   ├── query_intelligence.py       # Intent & entity extraction
│   ├── sql_validator.py            # AST validation & safety checks
│   ├── self_correction.py          # Auto-repair & zero-row diagnosis
│   └── mcp_client.py               # MCP Host connecting to subprocess servers
├── mcp_servers/                    # Decoupled MCP server subprocesses
│   ├── database_server.py          # Query execution & table listing
│   ├── schema_server.py            # Schema inspection & relationship search
│   └── report_server.py            # PDF generation & CSV export
├── web/                            # React 19 Production SPA
│   ├── src/                        # React components, stores & hooks
│   ├── Dockerfile                  # Multi-stage production build
│   └── nginx.conf.template         # Dynamic upstream proxy template
├── frontend/                       # Legacy Streamlit UI (optional)
├── embeddings/                     # ChromaDB index creation & introspection
│   ├── build_index.py              # Semantic table/column indexing
│   └── schema_introspect.py        # Database metadata reflection
├── nginx/                          # Production reverse-proxy configs
│   ├── nginx.conf                  # Host Nginx configuration
│   ├── upstream_blue.conf          # Blue upstream definition (:8081)
│   └── upstream_green.conf         # Green upstream definition (:8082)
├── scripts/                        # Production operations scripts
│   ├── switch_traffic.sh           # Zero-downtime cutover & rollback
│   └── health_check.sh             # Smoke test runner for idle stack
├── .github/workflows/
│   └── deploy.yml                  # Automated Blue-Green CI/CD workflow
├── docker-compose.yml              # Local development stack
├── docker-compose.blue.yml         # Production Blue Compose stack
├── docker-compose.green.yml        # Production Green Compose stack
├── .env.blue / .env.green          # Environment files for Blue/Green stacks
├── .env.production.example         # Production environment template
├── requirements.txt                # Python backend dependencies
└── DEPLOYMENT.md                   # Detailed deployment & operations manual
```

---

## ⚙️ Prerequisites

- **Python:** 3.10 or 3.11
- **Node.js:** 18 or 20+
- **Docker & Docker Compose:** Required for containerized workflows
- **PostgreSQL:** Local instance (for dev) or Managed Cloud DB (RDS / Supabase / Neon)
- **API Keys:**
  - [Groq API Key](https://console.groq.com/keys) (Primary recommended model: `openai/gpt-oss-120b`)
  - [Google Gemini API Key](https://aistudio.google.com/app/apikey) (Vision & fallback: `gemini-3.6-flash`)

---

## 🛠️ Local Development Setup

### 1. Clone & Configure Environment
```bash
git clone https://github.com/kishorekumar-2512/chatbot_v2.git
cd chatbot_v2
cp .env.example .env
```
Edit `.env` with your `DATABASE_URL`, `GROQ_API_KEY`, and `GEMINI_API_KEY`.

### 2. Backend Setup
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scriptsctivate

# Install dependencies
pip install -r requirements.txt

# Build initial schema embeddings index
python -m embeddings.build_index --full

# Start FastAPI backend
uvicorn backend.main:app --reload --port 8000
```

### 3. Frontend Setup
In a second terminal:
```bash
cd web
npm install
npm run dev
```
- **Web Interface:** `http://localhost:5173`
- **FastAPI Interactive Docs:** `http://localhost:8000/docs`

### 4. Running with Local Docker Compose
To run the containerized local development stack:
```bash
docker compose up --build
```
- **Web App:** `http://localhost:8080`
- **Backend API:** `http://localhost:8000/health`

---

## 🔌 Model Context Protocol (MCP)

The backend implements the open **Model Context Protocol (MCP)** specification. Instead of executing sensitive database operations or report generation directly in the web request thread, `backend/mcp_client.py` (`MCPHost`) spawns and manages three isolated JSON-RPC subprocesses:

1. **`database-mcp-server`** (`mcp_servers/database_server.py`): Connects to PostgreSQL, enforces read-only query restrictions, and runs paginated SELECT queries.
2. **`schema-mcp-server`** (`mcp_servers/schema_server.py`): Introspects table structures, column definitions, and foreign keys.
3. **`report-mcp-server`** (`mcp_servers/report_server.py`): Compiles visual analytics into downloadable PDF reports.

---

## 🔄 Production Blue-Green Deployment Guide

The platform uses a containerized **Blue-Green Deployment** strategy to guarantee **zero-downtime updates** and **instant rollback** capabilities.

### 💡 Core Concept
Instead of taking down your running app during an update, two identical stacks run side-by-side:
- **Blue Stack** (Internal: `web` on `:8081`, `backend` on `:8001`) — Active production environment.
- **Green Stack** (Internal: `web` on `:8082`, `backend` on `:8002`) — Idle / Staging environment.
- **Host Nginx Proxy** (Public: `:80` / `:443`) — Dynamically routes live traffic to the active color.

---

### 🚀 How to Use Blue-Green (Step-by-Step)

#### Step 1: Start the Initial "Blue" Stack
```bash
# 1. Build and bring up Blue stack
docker compose -f docker-compose.blue.yml up -d --build

# 2. Verify health of Blue services
./scripts/health_check.sh blue

# 3. Route live Nginx traffic to Blue
./scripts/switch_traffic.sh blue
```

#### Step 2: Deploy a New Release to the Idle "Green" Stack
When code or container updates are ready:
```bash
# 1. Build and start Green without affecting live users on Blue
docker compose -f docker-compose.green.yml up -d --build

# 2. Run automated smoke tests against Green
./scripts/health_check.sh green

# 3. Perform atomic zero-downtime traffic cutover to Green
./scripts/switch_traffic.sh green
```

#### Step 3: Instant Zero-Downtime Rollback
If any unexpected issues occur on Green post-deployment, switch traffic back to Blue in under 1 millisecond:
```bash
./scripts/switch_traffic.sh blue
```

---

### 🌐 One-Time Production Server Setup

On your host VM (AWS EC2 / DigitalOcean Droplet / Ubuntu Server):

```bash
# 1. Clone repo to server
git clone https://github.com/kishorekumar-2512/chatbot_v2.git /opt/chatbot_v2
cd /opt/chatbot_v2
chmod +x scripts/*.sh

# 2. Configure environment files
cp .env.production.example .env.blue
cp .env.production.example .env.green

# 3. Setup host Nginx reverse proxy
sudo apt-get update && sudo apt-get install -y nginx
sudo cp nginx/upstream_blue.conf /etc/nginx/conf.d/upstream_active.conf
sudo cp nginx/nginx.conf /etc/nginx/sites-available/chatbot.conf
sudo ln -s /etc/nginx/sites-available/chatbot.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

# 4. Start initial Blue stack
echo "blue" > .active_color
docker compose -f docker-compose.blue.yml up -d --build
./scripts/health_check.sh blue
```

---

### 📋 Blue-Green Command Cheat Sheet

| Action | Command |
| :--- | :--- |
| **Check currently active stack** | `cat .active_color` |
| **Start / Build Blue Stack** | `docker compose -f docker-compose.blue.yml up -d --build` |
| **Start / Build Green Stack** | `docker compose -f docker-compose.green.yml up -d --build` |
| **Smoke Test Blue Stack** | `./scripts/health_check.sh blue` |
| **Smoke Test Green Stack** | `./scripts/health_check.sh green` |
| **Switch Traffic to Blue** | `./scripts/switch_traffic.sh blue` |
| **Switch Traffic to Green** | `./scripts/switch_traffic.sh green` |
| **View Blue Logs** | `docker compose -f docker-compose.blue.yml logs -f` |
| **View Green Logs** | `docker compose -f docker-compose.green.yml logs -f` |
| **Stop Idle Stack (Optional)** | `docker compose -f docker-compose.blue.yml stop` (or green) |

---

## 🗄️ Cloud Database Migration

To migrate your local PostgreSQL database (`intern_db`) to AWS RDS or Supabase:

```bash
# 1. Export local schema and data
pg_dump -U postgres -h localhost -p 5432 -d intern_db -F c -b -v -f intern_db_backup.dump

# 2. Restore into managed cloud PostgreSQL
pg_restore -U <cloud_user> -h <cloud_host> -p 5432 -d <cloud_db> -v intern_db_backup.dump

# 3. Update DATABASE_URL in .env.blue and .env.green
DATABASE_URL=postgresql://<cloud_user>:<cloud_pass>@<cloud_host>:5432/<cloud_db>?sslmode=require

# 4. Generate embeddings against the cloud database
python -m embeddings.build_index --full
```

---

## 🚀 CI/CD Pipeline

The repository includes a complete GitHub Actions workflow ([`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)):

1. **Build & Test:** Multi-stage builds for `backend` and `web` images pushed to GHCR (`ghcr.io`).
2. **Idle Stack Target:** Reads `.active_color` on the production VM to determine the idle color.
3. **Automated Smoke Test:** Deploys new images to the idle stack and executes `scripts/health_check.sh`.
4. **Traffic Cutover:** On passing all health tests, triggers `scripts/switch_traffic.sh` for zero-downtime switch.

---

## 🔑 Environment Configuration

| Variable | Description | Required | Example / Default |
| :--- | :--- | :---: | :--- |
| `DATABASE_URL` | PostgreSQL connection string | **Yes** | `postgresql://user:pass@host:5432/db?sslmode=require` |
| `PRIMARY_LLM` | Default provider (`groq`, `gemini`, `qwen`) | No | `groq` |
| `GROQ_API_KEY` | Groq cloud API key | No | `gsk_...` |
| `GROQ_MODEL` | Groq model override | No | `openai/gpt-oss-120b` |
| `GEMINI_API_KEY` | Google Gemini API key | No | `AIza...` |
| `GEMINI_MODEL` | Google Gemini model override | No | `gemini-3.6-flash` |
| `OLLAMA_BASE_URL` | Local Ollama endpoint | No | `http://localhost:11434` |
| `OLLAMA_NUM_CTX` | Ollama context window size | No | `8192` |
| `CHROMA_DB_PATH` | Storage path for vector embeddings | No | `/app/embeddings/chroma_store` |
| `RETRIEVAL_TOP_K` | Number of tables to retrieve | No | `8` |
| `ADMIN_API_KEY` | Key for admin reindex and cross-org | No | Secure random string |
| `REQUIRE_AUTH` | Enforce JWT verification | No | `false` (dev) / `true` (prod) |
| `KEY_STORE_PATH` | Path for encrypted BYO tenant keys | No | `/app/data/llm_keys.json` |

---

## 🩺 Troubleshooting & Diagnostics

Run the integrated diagnostic tool to test all configured API keys, model availability, and database connectivity:

```bash
python diagnose_llm.py
```

### Common Issues:
- **Provider HTTP 404 (Model not found):** Ensure you are using active model identifiers (`openai/gpt-oss-120b` for Groq, `gemini-3.6-flash` for Gemini).
- **ChromaDB Dimension Error:** Delete `./embeddings/chroma_store` and run `python -m embeddings.build_index --full`.
- **Port Conflicts:** Ensure ports `8000`/`8001`/`8002` (backend) and `5173`/`8080`/`8081`/`8082` (frontend) are free.

---

## 👤 Author & Credits

- **Author:** Kishore Kumar
- **Project:** AI Database Report Chatbot v2 (Antigravity DB)
- **Repository:** [GitHub](https://github.com/kishorekumar-2512/chatbot_v2)
