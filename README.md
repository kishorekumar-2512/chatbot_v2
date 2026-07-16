# AI Database Report Chatbot — v2 (Upgraded)

Adds: semantic table retrieval, circuit-breaker model fallback, confidence
scoring, MCP server architecture, and security hardening on top of the
original NL-to-SQL chatbot.

## What's new vs v1

| Feature | v1 | v2 |
|---|---|---|
| Schema in prompt | Full schema always | Top-8 relevant tables (ChromaDB semantic search) |
| Model | Qwen only | Qwen → Groq → Gemini circuit breaker |
| Confidence | None | 4-signal weighted score shown in UI |
| Architecture | Direct function calls | MCP host + 3 MCP servers |
| Security | Open CORS | Rate limited (10/min/IP) + restricted CORS |

## 1. Install dependencies

```bash
pip install -r requirements.txt
```

`sentence-transformers` will download the `all-MiniLM-L6-v2` model (~80MB) on
first run, then it's fully offline. `mcp` requires Python 3.10+.

## 2. Pull the primary model

```bash
ollama pull qwen2.5-coder:7b
```

This is a larger model than the old `qwen2.5:3b` — better SQL accuracy, more
RAM/VRAM needed. If your machine can't run 7B comfortably, set
`OLLAMA_MODEL=qwen2.5:3b` in `.env` and the rest of the system still works.

## 3. Get free fallback API keys (optional but recommended)

- **Groq** (fallback 1): https://console.groq.com → API Keys → create key
- **Gemini** (fallback 2): https://aistudio.google.com → Get API Key

Both are free tier, no credit card. If you skip these, the circuit breaker
will just fail over to "all models failed" once Qwen's circuit opens — still
safe, just less resilient.

## 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your `DATABASE_URL`, and optionally `GROQ_API_KEY` /
`GEMINI_API_KEY`.

## 5. Build the semantic embedding index

**Run this once**, and again any time your schema changes:

```bash
python embeddings/build_index.py
```

This reads your live Neon schema, embeds each table description locally with
sentence-transformers, and stores vectors in `./embeddings/chroma_store`.

## 6. Run the app

```bash
# Terminal 1
ollama serve

# Terminal 2
uvicorn backend.main:app --reload --port 8000

# Terminal 3
streamlit run frontend/app.py
```

FastAPI's `lifespan` will automatically launch the 3 MCP servers as
subprocesses when uvicorn starts, and shut them down cleanly on exit — you
don't need to run them separately.

Open http://localhost:8501.

## Notes on the circuit breaker

- Qwen (primary) gets 3 consecutive failures before the circuit "opens" and
  routing moves to Groq.
- Groq gets 3 consecutive failures before moving to Gemini.
- Every 5 minutes, the router attempts one recovery call back to Qwen. If it
  succeeds, Qwen becomes primary again.
- Check `/circuit-status` or the sidebar "Refresh Status" button to see live
  breaker state per tier.

## Notes on confidence scoring

Shown as 4 progress bars per answer:
- **Table relevance** — how well the question matched the tables used (from ChromaDB cosine similarity)
- **Column accuracy** — 100 if the SQL validator found zero errors on the winning attempt
- **Attempt score** — penalizes needing 2nd/3rd retries
- **Row sanity** — flags suspicious 0-row or >10k-row results

Overall ≥80 = high, ≥55 = medium, <55 = low. Low confidence or 3-attempt
answers show a warning banner in the UI — treat those results with extra
scrutiny.
