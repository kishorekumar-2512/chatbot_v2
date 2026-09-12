"""
backend/hybrid_retriever.py

Layer 2: Multi-Strategy Retrieval
- BM25 keyword search combined with ChromaDB semantic search
- Reciprocal Rank Fusion to merge rankings
- Tiered similarity thresholds (high/medium/low confidence)
- Dynamic few-shot retrieval: finds similar past Q→SQL pairs from ChromaDB
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
        import os
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_OFFLINE"] = "1"
        _model = SentenceTransformer(EMBED_MODEL, local_files_only=True)
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
