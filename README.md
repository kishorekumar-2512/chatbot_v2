# AI Database NL-to-SQL Backend Engine v2

> **Enterprise-Grade Natural Language to SQL Execution Engine**  
> Powered by a **6-Layer Hybrid & Graph RAG Pipeline**, **Model Context Protocol (MCP)** Subprocesses, **Circuit-Breaker LLM Routing**, and **Multi-Tenant Security**.

---

## 📑 Table of Contents

- [Overview](#-overview)
- [System Architecture](#-system-architecture)
- [6-Layer Accuracy Pipeline](#-6-layer-accuracy-pipeline)
- [Multi-LLM Fallback & Circuit Breaker](#-multi-llm-fallback--circuit-breaker)
- [Model Context Protocol (MCP) Architecture](#-model-context-protocol-mcp-architecture)
- [Multi-Tenant Security & AST Validation](#-multi-tenant-security--ast-validation)
- [API Reference & Postman Guide](#-api-reference--postman-guide)
- [Repository Structure](#-repository-structure)
- [Quickstart & Local Setup](#-quickstart--local-setup)
- [Environment Configuration](#-environment-configuration)

---

## 🌟 Overview

This repository is a **standalone, high-accuracy backend API** that converts natural language business questions into precise, read-only SQL queries, executes them against PostgreSQL, and returns validated answers.

### Core Highlights:
- **Zero Frontend Dependency:** Tested and operated directly via REST API calls and Postman.
- **Deterministic 6-Layer Pipeline:** Eliminates hallucinated table names, invalid column references, and incorrect joins using a combination of vector search, keyword ranking, and foreign-key graph traversal.
- **Fault-Tolerant LLM Routing:** Prioritizes tenant-supplied BYO keys, falling back dynamically across Groq &rarr; Google Gemini &rarr; Local Qwen (Ollama) with per-provider circuit breakers.
- **Standardized MCP Architecture:** Database queries and schema lookups run through sandboxed Model Context Protocol subprocesses over JSON-RPC stdio.

---

## 🏗️ System Architecture

The backend utilizes an asynchronous dual-server architecture:

```mermaid
graph TD
    Client[Postman / API Client] -->|Port 8000: /chat, /chat/json, /chat/stream| Server1[Server 1: Public Gateway FastAPI]
    Client -->|Port 8001: /process| Server2[Server 2: Internal Processing Engine]

    Server1 -->|Internal HTTP Relay /chat/json| Server2
    
    Server2 --> Pipeline[6-Layer Accuracy Pipeline]
    Server1 --> Pipeline

    subgraph "Core Backend Services"
        Pipeline --> Retriever[Hybrid Retriever BM25 + ChromaDB]
        Pipeline --> Graph[Schema Graph Engine NetworkX]
        Pipeline --> Router[LLM Orchestrator & Circuit Breakers]
        Pipeline --> Validator[AST SQL & Org Security Validator]
    end

    subgraph "Model Context Protocol MCP"
        Pipeline --> MCPHost[MCP Host stdio JSON-RPC]
        MCPHost --> DBSrv[database-mcp-server]
        MCPHost --> SchemaSrv[schema-mcp-server]
    end

    DBSrv --> PostgreSQL[(PostgreSQL Database)]
    SchemaSrv --> PostgreSQL
```

---

## 🔬 6-Layer Accuracy Pipeline

Every natural language question flows through a 6-layer accuracy pipeline designed to ensure 100% syntactically valid and schema-grounded SQL:

```mermaid
flowchart TD
    Q[User Question] --> L0{L0: Meta / Schema Query?}
    L0 -- Yes --> MetaAns[Instant Response from Schema Cache]
    L0 -- No --> L1[L1: Query Intelligence<br/>Intent Detection & SQL Skeleton]
    
    L1 --> L2[L2: Hybrid Retrieval<br/>Dense ChromaDB + Sparse BM25 + Table Anchors]
    L2 --> L3[L3: Schema Graph<br/>NetworkX Foreign Key Join Pathfinding]
    L3 --> L4[L4: Context Assembly<br/>Live Column Sampling + Dynamic Few-Shot Examples]
    
    L4 --> L5[L5: SQL Generation<br/>LLM Chain-of-Thought with Prompt Budgeting]
    L5 --> Val{AST & Security Validation}
    
    Val -- Passed --> Exec[Execute Query via Database MCP]
    Val -- Failed --> Retry[L6: Self-Correction Loop]
    
    Exec -- Error --> Repair[L6: Deterministic Auto-Repair & Zero-Row Diagnosis]
    Repair --> Retry
    Retry -- Max 3 Attempts --> L5
    
    Exec -- Success --> Final[Final Response Output]
```

### Layer Details:
1. **L0 — Meta Bypass:** Instant response for schema questions (e.g. *"list all tables"*) directly from cache without consuming LLM tokens.
2. **L1 — Query Intelligence:** Classifies intent (aggregation, filter, ranking) and extracts candidate entities.
3. **L2 — Hybrid Retrieval:** Combines BM25 sparse keyword matching and ChromaDB dense embeddings to select the most relevant tables.
4. **L3 — Schema Graph:** Computes the shortest foreign-key join paths between candidate tables to eliminate hallucinated joins.
5. **L4 — Context Assembly:** Injects few-shot examples and live database column values (e.g. `'active'`, `'offline'`).
6. **L5 — Generation & AST Validation:** Generates SQL, strips `<think>` tokens, and validates that every table and column exists.
7. **L6 — Self-Correction:** Automatically corrects syntax errors and diagnoses 0-row query mismatches on the fly.

---

## ⚡ Multi-LLM Fallback & Circuit Breaker

The orchestrator dynamically routes requests through a priority chain with automatic failover and outage tracking:

```mermaid
graph LR
    Req[SQL Request] --> Step1{Tenant BYO Key Configured?}
    Step1 -- Yes --> BYO[Execute via Customer BYO Key]
    Step1 -- No --> Step2{Groq Llama 3.3 Available?}
    
    BYO -- Fail / Disabled --> Step2
    Step2 -- Yes --> Groq[Execute via Groq API]
    Step2 -- Fail / 429 --> Step3{Gemini Available?}
    
    Groq -- Outage --> Step3
    Step3 -- Yes --> Gemini[Execute via Google Gemini]
    Step3 -- Fail / Outage --> Step4[Execute via Local Ollama / Qwen]
```

- **BYOK Support:** Encrypted customer API key store in `data/llm_keys.json`.
- **Circuit Breaker:** Automatic cooldown and backoff when rate limits (HTTP 429) or timeouts occur, logged to `data/llm_failures.jsonl`.

---

## 🔌 Model Context Protocol (MCP) Architecture

Instead of executing direct database calls from route handlers, the backend communicates with isolated MCP servers over standard input/output (`stdio`) using JSON-RPC:

1. **`database-mcp-server`** (`mcp_servers/database_server.py`):
   - `run_query(sql)`: Executes read-only queries with connection pooling.
   - `get_schema(tables)`: Fetches exact PostgreSQL DDL definitions.
   - `list_tables()`: Retrieves active database tables.
2. **`schema-mcp-server`** (`mcp_servers/schema_server.py`):
   - `search_tables(question, top_k)`: Returns semantic table matches.
   - `get_columns(table)` & `get_relations(table)`: Introspects column details and foreign keys.

---

## 🛡️ Multi-Tenant Security & AST Validation

- **Read-Only Enforcement:** Regex and AST parser blocks all non-SELECT commands (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, chained statements).
- **Tenant Isolation (`zecure_org_id`):** When `REQUIRE_AUTH=true`, queries are inspected by `validate_org_security()` to verify that all customer tables include `zecure_org_id = '{org_id}'`.
- **Administrative Bypass:** Cross-tenant queries (`all_orgs=True`) are strictly protected by the `X-Admin-Key` header.

---

## 📡 API Reference & Postman Guide

### Base URLs:
- **Server 1 (Gateway):** `http://localhost:8000`
- **Server 2 (Internal Engine):** `http://127.0.0.1:8001`

### Summary of Endpoints:

| Method | Endpoint | Port | Description |
| :---: | :--- | :---: | :--- |
| `POST` | **`/process`** | `8001` | **Clean 3-Field Output:** Returns strictly `{"sql", "model_used", "attempts"}`. |
| `POST` | **`/chat/json`** | `8000` | **Relay Route:** Forwards query from Server 1 to Server 2's `/process`. |
| `POST` | **`/chat`** | `8000` | Full JSON response including SQL, rows, summary answer, and follow-ups. |
| `POST` | **`/chat/stream`** | `8000` | Server-Sent Events (SSE) live reasoning stream. |
| `POST` | **`/run-sql`** | `8000` | Direct validated SQL query execution. |
| `GET` | **`/schema/tables`**| `8000` | Database schema introspection (tables, columns, types, comments). |
| `GET` | **`/settings/providers`** | `8000` | List available LLM providers and models. |
| `GET` | **`/settings/keys`** | `8000` | List configured BYOK keys for a tenant. |
| `POST` | **`/settings/keys`** | `8000` | Save/update a customer BYOK API key. |
| `PATCH`| **`/settings/keys/toggle`**| `8000` | Enable or disable a BYOK API key. |
| `DELETE`| **`/settings/keys`**| `8000` | Delete a customer BYOK API key. |
| `POST` | **`/admin/reindex`**| `8000` | Trigger vector index re-synchronization. |

---

### Sample Postman Requests

#### 1. Test `/process` (Trimmed Response)
```http
POST http://127.0.0.1:8001/process
Content-Type: application/json

{
  "question": "How many devices are registered in the system?"
}
```
**Response:**
```json
{
  "sql": "SELECT COUNT(*) AS total_devices FROM devices;",
  "model_used": "groq-llama-3.3-70b-versatile",
  "attempts": 1
}
```

#### 2. Test `/chat/json` (Gateway Relay)
```http
POST http://localhost:8000/chat/json
Content-Type: application/json

{
  "question": "List all tables"
}
```
**Response:**
```json
{
  "sql": "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name;",
  "model_used": "schema-cache (no LLM used)",
  "attempts": 1
}
```

#### 3. Save a BYO API Key
```http
POST http://localhost:8000/settings/keys
Content-Type: application/json

{
  "provider": "groq",
  "api_key": "gsk_YourPersonalGroqKey",
  "model": "llama-3.3-70b-versatile",
  "customer_id": "org_demo"
}
```

---

## 📁 Repository Structure

```
chatbot_v2/
├── .env                    # Local environment config (gitignored)
├── .env.example            # Configuration template with guide
├── .gitignore
├── README.md               # Architecture documentation
├── requirements.txt        # Minimal Python dependencies
├── data/
│   ├── llm_keys.json       # Encrypted tenant BYOK API keys
│   └── llm_failures.jsonl  # Circuit breaker outage log
├── backend/                # Core FastAPI backend (18 files)
│   ├── main.py             # Main entry point (Server 1 + Server 2)
│   ├── auth.py             # JWT validation & tenant authentication
│   ├── data_source.py      # Database connection configuration
│   ├── hybrid_retriever.py # BM25 + ChromaDB semantic search
│   ├── insights.py         # Summary statistics & follow-up suggestions
│   ├── llm_config.py       # LLM provider configurations
│   ├── llm_key_store.py    # Key persistence & encryption
│   ├── llm_orchestrator.py # Fallback routing & circuit breaking
│   ├── llm_registry.py     # Provider registry metadata
│   ├── mcp_client.py       # MCP client (Database + Schema)
│   ├── model_router.py     # Dynamic model routing
│   ├── prompts.py          # PostgreSQL NL→SQL system prompts
│   ├── query_intelligence.py # Intent detection & skeleton generation
│   ├── query_intent.py     # Intent classification definitions
│   ├── schema_graph.py     # Foreign Key join pathfinding
│   ├── self_correction.py  # Zero-row diagnosis & auto-repair
│   └── sql_validator.py    # SQL security & org_id validation
├── embeddings/             # Embedding vector index
│   ├── build_index.py      # Schema indexing script
│   ├── retrieve.py         # Embedding retriever
│   └── schema_introspect.py# PostgreSQL schema introspector
├── mcp_servers/            # Standalone MCP servers
│   ├── database_server.py  # Database query execution server
│   └── schema_server.py    # Schema introspection server
└── migrations/
    └── 001_enable_rls.sql  # Row-level security setup
```

---

## 🚀 Quickstart & Local Setup

### 1. Prerequisites
- Python 3.10+
- PostgreSQL database instance

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
cp .env.example .env
```
Edit `.env` and configure your credentials:
```env
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/your_database
PRIMARY_LLM=groq
GROQ_API_KEY=gsk_your_groq_api_key
REQUIRE_AUTH=false
```

### 4. Build Schema Vector Index (Optional but Recommended)
```bash
python embeddings/build_index.py
```

### 5. Start the Backend API
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
*(Server 2 on port 8001 is automatically started in the background by the FastAPI lifespan handler).*
