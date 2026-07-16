# backend/Dockerfile
# Production image for the FastAPI backend. Builds from the project root:
#   docker build -f backend/Dockerfile -t chatbot-backend .
#
# Notes:
# - sentence-transformers/chromadb pull in torch — this image is intentionally
#   NOT slim on disk size in exchange for a straightforward, low-maintenance
#   build. Optimize later if image size becomes an actual problem.
# - No Ollama/Qwen here — this image assumes the cloud-default model priority
#   (Groq -> Gemini -> Qwen), where Qwen is optional and, if used at all, runs
#   on a separate GPU host (OLLAMA_BASE_URL points at it), not in this container.

FROM python:3.11-slim AS base

# System deps: psycopg2 needs libpq; mcp servers run as subprocesses so no extra runtime needed.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY mcp_servers/ ./mcp_servers/
COPY embeddings/ ./embeddings/

# chroma_store is a mount point (EFS in ECS, a named volume locally) — the
# app writes/reads its persistent vector index here across restarts.
RUN mkdir -p /app/embeddings/chroma_store /app/data /app/reports

ENV PYTHONUNBUFFERED=1 \
    CHROMA_DB_PATH=/app/embeddings/chroma_store \
    KEY_STORE_PATH=/app/data/llm_keys.json \
    REPORTS_DIR=/app/reports

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
