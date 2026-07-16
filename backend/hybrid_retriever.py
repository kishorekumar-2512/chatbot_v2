"""
backend/hybrid_retriever.py

Layer 2: Multi-Strategy Retrieval
- BM25 keyword search combined with ChromaDB semantic search
- Reciprocal Rank Fusion to merge rankings
- Tiered similarity thresholds (high/medium/low confidence)
- Dynamic few-shot retrieval: finds similar past Q→SQL pairs from ChromaDB
- Column value sampling: queries actual DB values so LLM uses correct strings
"""

import os
import json
import math
import time
from typing import Optional

import chromadb
from sentence_transformers import SentenceTransformer

CHROMA_DB_PATH   = os.getenv("CHROMA_DB_PATH", "./embeddings/chroma_store")
EMBED_MODEL      = "all-MiniLM-L6-v2"
COLLECTION_NAME  = "table_schemas"
EXAMPLES_COLL    = "sql_examples"
TOP_K            = int(os.getenv("RETRIEVAL_TOP_K", "8"))

# Weights for hybrid fusion
SEMANTIC_WEIGHT  = 0.65
BM25_WEIGHT      = 0.35

# Similarity thresholds
HIGH_THRESHOLD   = 0.60
MEDIUM_THRESHOLD = 0.35


# ── Lazy singletons ───────────────────────────────────────────────────────────
_model: Optional[SentenceTransformer] = None
_client: Optional[chromadb.PersistentClient] = None
_table_collection = None
_example_collection = None
_bm25_data: Optional[dict] = None  # {table_name: tokenized_description}


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def _get_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    return _client


def _get_table_collection():
    global _table_collection
    if _table_collection is None:
        _table_collection = _get_client().get_or_create_collection(COLLECTION_NAME)
    return _table_collection


def _get_example_collection():
    global _example_collection
    if _example_collection is None:
        _example_collection = _get_client().get_or_create_collection(EXAMPLES_COLL)
    return _example_collection


def _get_bm25_data() -> dict:
    """Load all table descriptions for BM25 scoring."""
    global _bm25_data
    if _bm25_data is None:
        coll = _get_table_collection()
        if coll.count() == 0:
            return {}
        results = coll.get(include=["documents", "metadatas"])
        _bm25_data = {
            meta["table_name"]: doc.lower().split()
            for meta, doc in zip(results["metadatas"], results["documents"])
        }
    return _bm25_data


# ── BM25 implementation (pure Python, no rank-bm25 dependency needed) ─────────
def _bm25_score(query_tokens: list[str], doc_tokens: list[str],
                avg_doc_len: float, k1: float = 1.5, b: float = 0.75) -> float:
    """Score a single document against query tokens using BM25."""
    doc_len = len(doc_tokens)
    score = 0.0
    freq_map: dict[str, int] = {}
    for t in doc_tokens:
        freq_map[t] = freq_map.get(t, 0) + 1

    for token in set(query_tokens):
        tf = freq_map.get(token, 0)
        if tf == 0:
            continue
        idf = math.log(1 + (1 - 0.5 + 0.5) / (0.5 + 0.5))  # simplified IDF
        tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / avg_doc_len))
        score += idf * tf_norm
    return score


def _bm25_scores(question: str, bm25_data: dict) -> dict[str, float]:
    """Return normalised BM25 scores for all tables."""
    tokens = question.lower().split()
    docs   = list(bm25_data.values())
    avg_len = sum(len(d) for d in docs) / max(len(docs), 1)

    raw_scores = {
        table: _bm25_score(tokens, doc_tokens, avg_len)
        for table, doc_tokens in bm25_data.items()
    }
    max_score = max(raw_scores.values()) if raw_scores else 1.0
    if max_score == 0:
        return {t: 0.0 for t in raw_scores}
    return {t: s / max_score for t, s in raw_scores.items()}


# ── Hybrid retrieval ──────────────────────────────────────────────────────────
def get_schema_for_tables(tables: list[str]) -> str:
    """
    Fetch DDL for an EXPLICIT list of table names directly from the ChromaDB
    collection (by ID, not similarity search). Used for follow-up questions
    that need to reuse tables from the previous turn even when the new
    question's own text wouldn't retrieve them on similarity/BM25 alone.
    """
    if not tables:
        return ""
    coll = _get_table_collection()
    if coll.count() == 0:
        return ""
    try:
        result = coll.get(ids=tables)
        ddls = {tid: meta.get("raw_ddl", f"Table {tid}") for tid, meta in zip(result["ids"], result["metadatas"])}
        return "\n".join(ddls[t] for t in tables if t in ddls)
    except Exception:
        return ""


def retrieve_tables(question: str, top_k: int = TOP_K) -> dict:
    """
    Main retrieval function. Returns:
    {
        "tables_used": list[str],         # ordered by combined score
        "similarity_scores": dict,        # table -> 0-1 score
        "schema_text": str,               # DDL for retrieved tables
        "tiers": {"high": [...], "medium": [...], "low": [...]}
    }
    """
    coll = _get_table_collection()
    if coll.count() == 0:
        return {"tables_used": [], "similarity_scores": {}, "schema_text": "", "tiers": {}}

    model   = _get_model()
    bm25_data = _get_bm25_data()

    # 1. Semantic search via ChromaDB
    query_embedding = model.encode([question]).tolist()
    n_results = min(top_k + 5, coll.count())
    chroma_results = coll.query(query_embeddings=query_embedding, n_results=n_results)

    sem_scores: dict[str, float] = {}
    table_ddls: dict[str, str]   = {}

    for table_name, distance, meta in zip(
        chroma_results["ids"][0],
        chroma_results["distances"][0],
        chroma_results["metadatas"][0],
    ):
        # ChromaDB returns L2 distance → convert to similarity
        sim = max(0.0, 1.0 - (distance / 2.0))
        sem_scores[table_name] = round(sim, 4)
        table_ddls[table_name] = meta.get("raw_ddl", f"Table {table_name}")

    # 2. BM25 keyword scores
    bm25 = _bm25_scores(question, bm25_data)

    # 3. Reciprocal Rank Fusion
    all_tables = set(sem_scores) | set(bm25)
    combined: dict[str, float] = {}
    for table in all_tables:
        s = sem_scores.get(table, 0.0) * SEMANTIC_WEIGHT
        b = bm25.get(table, 0.0) * BM25_WEIGHT
        combined[table] = round(s + b, 4)

    # 4. Tier classification
    high   = [t for t, s in combined.items() if s >= HIGH_THRESHOLD]
    medium = [t for t, s in combined.items() if MEDIUM_THRESHOLD <= s < HIGH_THRESHOLD]
    low    = [t for t, s in combined.items() if s < MEDIUM_THRESHOLD]

    # 5. Select final set
    selected = sorted(high, key=combined.get, reverse=True)
    remaining_slots = top_k - len(selected)
    if remaining_slots > 0:
        selected += sorted(medium, key=combined.get, reverse=True)[:remaining_slots]
    if len(selected) < 3:
        # Fallback: always have at least 3 tables
        extra = sorted(low, key=combined.get, reverse=True)[:3 - len(selected)]
        selected += extra

    # Cap at top_k
    selected = selected[:top_k]

    # Build schema text
    schema_lines = [table_ddls[t] for t in selected if t in table_ddls]
    schema_text  = "\n".join(schema_lines)

    return {
        "tables_used":       selected,
        "similarity_scores": {t: combined.get(t, 0.0) for t in selected},
        "schema_text":       schema_text,
        "tiers": {
            "high":   [t for t in selected if combined.get(t, 0) >= HIGH_THRESHOLD],
            "medium": [t for t in selected if MEDIUM_THRESHOLD <= combined.get(t, 0) < HIGH_THRESHOLD],
            "low":    [t for t in selected if combined.get(t, 0) < MEDIUM_THRESHOLD],
        }
    }


# ── Dynamic few-shot retrieval ────────────────────────────────────────────────
def get_similar_examples(question: str, top_k: int = 3) -> str:
    """
    Retrieves past successful Q→SQL pairs similar to this question.
    Returns formatted string to inject into prompt.
    """
    try:
        coll = _get_example_collection()
        if coll.count() == 0:
            return ""
        n = min(top_k, coll.count())
        results = coll.query(query_texts=[question], n_results=n)
        if not results["documents"][0]:
            return ""
        examples = "\nSimilar past queries that worked:\n"
        for past_q, meta in zip(results["documents"][0], results["metadatas"][0]):
            sql = meta.get("sql", "")
            rows = meta.get("row_count", "?")
            examples += f"\nQ: {past_q}\n```sql\n{sql}\n```  -- returned {rows} rows\n"
        return examples
    except Exception:
        return ""


def store_successful_example(question: str, sql: str, row_count: int):
    """
    Stores a successful Q→SQL pair in ChromaDB for future retrieval.
    Only stores if the query returned results (row_count > 0).
    """
    if row_count == 0:
        return
    try:
        coll = _get_example_collection()
        ex_id = f"ex_{abs(hash(question)) % 10**9}"
        # Upsert: replace if same question stored before
        try:
            coll.delete(ids=[ex_id])
        except Exception:
            pass
        coll.add(
            documents=[question],
            metadatas=[{"sql": sql, "row_count": row_count, "stored_at": time.time()}],
            ids=[ex_id],
        )
    except Exception:
        pass  # Never crash on example storage


# ── Column value sampling ─────────────────────────────────────────────────────
# Columns worth sampling for filter accuracy
SAMPLE_COLUMNS = {
    "managed_device":               ["platform", "device_type", "status"],
    "managed_user":                 ["domain"],
    "device_info":                  ["processor", "device_type"],
    "device_operating_system_info": ["os_name", "os_version", "os_architecture"],
    "alerts":                       ["severity", "alert_type", "status"],
    "device_antivirus":             ["protection_status", "licence_status"],
    "device_bitlocker":             ["encryption_status", "protection_status", "lock_status"],
    "device_firewall":              ["protection_status", "status"],
    "org_patch":                    ["severity", "patch_family"],
    "device_patch":                 ["install_status"],
    "license_details":              ["compliant_status", "license_type"],
    "agent_info":                   ["upgrade_status"],
    "software":                     ["platform", "software_type"],
    "device_warranty":              ["warranty_status", "warranty_type"],
    "managed_device_compliance_map":["compliant_status"],
}


async def sample_column_values(table: str, column: str, run_query_fn) -> list:
    """
    Sample actual distinct values from a column so LLM uses correct strings.
    run_query_fn is the MCP run_query function.
    """
    try:
        sql  = f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL LIMIT 12"
        rows = await run_query_fn(sql)
        return [str(r[column]) for r in rows if r.get(column) is not None]
    except Exception:
        return []


async def build_value_hints(tables: list[str], run_query_fn) -> str:
    """
    Build a string showing actual DB values for filter columns.
    Injected into prompt so LLM uses ILIKE with correct casing.

    Runs all column samples CONCURRENTLY (asyncio.gather) instead of one
    sequential await per column — with up to ~8 tables x 3 columns that was
    up to 24 sequential DB round trips before, now it's one round of parallel
    calls.
    """
    import asyncio

    jobs = []  # (table, col) pairs, in order
    for table in tables:
        if table in SAMPLE_COLUMNS:
            for col in SAMPLE_COLUMNS[table]:
                jobs.append((table, col))

    if not jobs:
        return ""

    results = await asyncio.gather(
        *(sample_column_values(t, c, run_query_fn) for t, c in jobs),
        return_exceptions=True,
    )

    hints = []
    for (table, col), values in zip(jobs, results):
        if isinstance(values, Exception) or not values:
            continue
        hints.append(f"  {table}.{col} actual values: {values}")

    if not hints:
        return ""
    return "\nActual column values from DB (use ILIKE with these):\n" + "\n".join(hints)
