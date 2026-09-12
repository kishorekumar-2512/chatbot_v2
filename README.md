# AI Database Text-to-SQL Backend Engine v2

> **Enterprise Natural Language to SQL Generation API**  
> Powered by a **6-Layer Hybrid Retrieval & Schema Graph Engine**, **Multi-Turn Context Continuity**, and **Strict Tenant (`org_id`) Isolation**.

---

## 📑 Table of Contents

- [Overview](#-overview)
- [System Architecture](#-system-architecture)
- [Accuracy Pipeline](#-accuracy-pipeline)
- [Multi-Turn Context Support](#-multi-turn-context-support)
- [Multi-Tenant Security & AST Validation](#-multi-tenant-security--ast-validation)
- [API Reference & Postman Guide](#-api-reference--postman-guide)
- [Repository Structure](#-repository-structure)
- [Quickstart & Local Setup](#-quickstart--local-setup)
- [Environment Configuration](#-environment-configuration)

---

## 🌟 Overview

This repository is a **standalone, high-accuracy Text-to-SQL backend API** running on a single server (port `8000`). It translates natural language questions into precise, read-only SQL queries scoped strictly to the requesting organization (`org_id`).

### Core Highlights:
- **Single-Server Architecture:** Runs cleanly on port 8000 without proxy relays or secondary daemon servers.
- **Pure Text-to-SQL Output:** Returns structured, clean output containing `sql`, `model_used`, `attempts`, and `tables_used`.
- **Strict Multi-Tenant Isolation:** Enforces tenant separation via `zecure_org_id = {org_id}` without administrative cross-tenant bypasses.
- **Multi-Turn Context:** Resolves conversational pronoun continuations (*"filter that to critical only"*, *"now show by month"*) using the prior turn's SQL and table references.
- **Multi-LLM Fallback:** Transparent failover chain across Groq &rarr; Google Gemini &rarr; Local Ollama / Qwen with in-memory circuit breakers.

---

## 🏗️ System Architecture

```mermaid
graph TD
    Client[Postman / API Client / Frontend] -->|POST /chat & GET /health (Port 8000)| Server[FastAPI Backend Engine]

    subgraph "Core Backend Services"
        Server --> Pipeline[Text-to-SQL Pipeline]
        Pipeline --> Retriever[Hybrid Retriever BM25 + ChromaDB]
        Pipeline --> Graph[Schema Graph Engine NetworkX]
        Pipeline --> Router[LLM Orchestrator & Circuit Breakers]
        Pipeline --> Validator[AST SQL & Org Security Validator]
    end
```

---

## 🔬 Accuracy Pipeline

Every natural language question flows through a dedicated pipeline to guarantee syntactically valid and schema-grounded SQL:

1. **L1 — Query Intelligence:** Classifies intent (aggregation, filter, ranking, CTEs) and extracts candidate entities.
2. **L2 — Hybrid Retrieval:** Combines BM25 sparse keyword matching and ChromaDB dense embeddings to select the most relevant tables.
3. **L3 — Schema Graph:** Computes the shortest foreign-key join paths between candidate tables to eliminate hallucinated joins.
4. **L4 — Context Assembly:** Injects few-shot examples, dynamic prompt budgeting, and previous-turn conversation context.
5. **L5 — Generation & AST Validation:** Generates SQL, strips thinking scratchpads, and verifies that every referenced table and column exists.
6. **L6 — Self-Correction:** Automatically corrects syntax errors and retries with diff-style error context.

---

## 💬 Multi-Turn Context Support

When a query is a continuation of a previous query, the client passes the previous turn's context in the request:

```json
{
  "question": "now filter that to windows only",
  "context": {
    "question": "Show all active devices",
    "sql": "SELECT DISTINCT md.id, md.device_name FROM managed_device md WHERE md.status = 1;",
    "tables_used": ["managed_device"]
  },
  "org_id": "1001"
}
```

The pipeline detects continuation phrases (`"that"`, `"now"`, `"filter further"`, etc.), reuses relevant schema tables from `context.tables_used`, and provides the previous query's SQL as context to guide incremental refinement.

---

## 🛡️ Multi-Tenant Security & AST Validation

- **Strict Organization Isolation (`zecure_org_id`):** Every query with an `org_id` is inspected by `validate_org_security()` to verify that all business tables containing `zecure_org_id` enforce `alias.zecure_org_id = {org_id}`.
- **Read-Only Enforcement:** Regex and AST parser blocks all non-SELECT commands (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, chained statements).
- **No Cross-Tenant Bypass:** There are no master admin keys or cross-tenant bypass flags; queries are always strictly bound to their organization.

---

## 📡 API Reference & Postman Guide

### Base URL:
`http://localhost:8000`

### Endpoints:

| Method | Endpoint | Description |
| :---: | :--- | :--- |
| `GET` | **`/health`** | Health check probe (LLM status and embedding readiness). |
| `POST` | **`/chat`** | Primary Text-to-SQL generation endpoint with multi-turn context support. |

---

### Request & Response Examples

#### 1. First Turn (`POST /chat`)

**Request:**
```http
POST http://localhost:8000/chat
Content-Type: application/json

{
  "question": "Show all active devices",
  "org_id": "1001"
}
```

**Response (200 OK):**
```json
{
  "sql": "SELECT DISTINCT emd.id, emd.device_name, emd.status FROM enrollment_managed_devices emd WHERE emd.status ILIKE '%active%' AND emd.zecure_org_id = '1001' ORDER BY emd.created_time DESC;",
  "model_used": "Groq (openai/gpt-oss-120b)",
  "attempts": 1,
  "tables_used": ["enrollment_managed_devices"]
}
```

#### 2. Follow-Up Turn (`POST /chat`)

**Request:**
```http
POST http://localhost:8000/chat
Content-Type: application/json

{
  "question": "now filter that to critical severity only",
  "context": {
    "question": "Show all active devices",
    "sql": "SELECT DISTINCT emd.id, emd.device_name, emd.status FROM enrollment_managed_devices emd WHERE emd.status ILIKE '%active%' AND emd.zecure_org_id = '1001';",
    "tables_used": ["enrollment_managed_devices"]
  },
  "org_id": "1001"
}
```

---

## 📂 Repository Structure

```
chatbot_v2/
├── backend/
│   ├── auth.py                 # JWT token decoding and org claim extraction
│   ├── hybrid_retriever.py     # BM25 + ChromaDB semantic retrieval
│   ├── llm_config.py           # Model configurations and circuit status
│   ├── llm_orchestrator.py     # LLM provider routing and failover
│   ├── llm_registry.py         # Provider registry specifications
│   ├── main.py                 # FastAPI application and /chat endpoint
│   ├── prompts.py              # System prompts and query rules
│   ├── query_intelligence.py   # Intent classification and entity extraction
│   ├── schema_graph.py         # FK graph traversal and join hints
│   ├── self_correction.py      # Error context formatting and SQL linting
│   └── sql_validator.py        # Syntax, read-only, and org security validation
├── embeddings/
│   ├── chroma_store/           # Precomputed schema vectors
│   └── retrieve.py             # Vector search interface
├── .env.example                # Sample environment configuration
├── requirements.txt            # Python dependencies
└── README.md                   # System documentation
```

---

## 🚀 Quickstart & Local Setup

### 1. Prerequisites
- Python 3.10+

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
cp .env.example .env
```
Edit `.env` and set your LLM API keys:
```env
PRIMARY_LLM=groq
GROQ_API_KEY=gsk_your_groq_api_key
REQUIRE_AUTH=false
```

### 4. Start the Server
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
