"""
embeddings/retrieve.py

Query-time semantic retrieval. Given a natural-language question, finds the
top-K most relevant tables using cosine similarity against the ChromaDB
index built by build_index.py.

This is what lets the system scale past hundreds of tables — instead of
injecting the FULL schema into every LLM prompt (which blows the context
window and slows generation), we only inject the tables that are actually
relevant to the question.

At your current scale (9 tables) this still runs and works correctly, it's
just less load-bearing — the value compounds as table count grows.
"""

import os
import functools

import chromadb
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

CHROMA_DB_PATH  = os.getenv("CHROMA_DB_PATH", "./embeddings/chroma_store")
EMBED_MODEL     = "all-MiniLM-L6-v2"
COLLECTION_NAME = "table_schemas"
TOP_K           = int(os.getenv("RETRIEVAL_TOP_K", "8"))


@functools.lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Load the embedding model once per process (lazy singleton)."""
    return SentenceTransformer(EMBED_MODEL)


@functools.lru_cache(maxsize=1)
def _get_collection():
    """Connect to the persistent ChromaDB collection once per process."""
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    try:
        return client.get_collection(COLLECTION_NAME)
    except Exception as e:
        raise RuntimeError(
            f"ChromaDB collection '{COLLECTION_NAME}' not found at '{CHROMA_DB_PATH}'. "
            f"Run `python embeddings/build_index.py` first. Original error: {e}"
        )


@functools.lru_cache(maxsize=1)
def _get_bm25_index():
    """Load all tables from Chroma and build an in-memory BM25 index."""
    collection = _get_collection()
    all_data = collection.get()
    
    docs = all_data.get("documents", [])
    metas = all_data.get("metadatas", [])
    
    # Tokenize corpus for BM25
    tokenized_corpus = [doc.lower().split() for doc in docs]
    bm25 = BM25Okapi(tokenized_corpus)
    return bm25, metas


def retrieve_relevant_tables(question: str, top_k: int = TOP_K) -> dict:
    """
    Returns:
        {
            "schema_text": str,           # DDL for only the relevant tables
            "tables_used": list[str],     # table names, for the API response
            "similarity_scores": dict,    # table_name -> cosine similarity (0-1)
        }
    """
    model      = _get_model()
    collection = _get_collection()

    # 1. Dense Retrieval (ChromaDB Vector Search)
    query_embedding = model.encode([question]).tolist()
    dense_results = collection.query(
        query_embeddings=query_embedding,
        n_results=collection.count(), # Get all to rank them
    )
    dense_metas = dense_results["metadatas"][0]
    
    dense_ranks = {meta["table_name"]: rank for rank, meta in enumerate(dense_metas)}

    # 2. Sparse Retrieval (BM25 Keyword Search)
    bm25, sparse_metas = _get_bm25_index()
    tokenized_query = question.lower().split()
    sparse_scores = bm25.get_scores(tokenized_query)
    
    # Sort sparse results by score descending
    sparse_ranked = sorted(zip(sparse_metas, sparse_scores), key=lambda x: x[1], reverse=True)
    sparse_ranks = {meta["table_name"]: rank for rank, (meta, score) in enumerate(sparse_ranked)}

    # 3. Reciprocal Rank Fusion (RRF)
    k = 60
    rrf_scores = {}
    table_meta_map = {meta["table_name"]: meta for meta in sparse_metas}
    
    for table_name in table_meta_map.keys():
        dense_rank = dense_ranks.get(table_name, len(dense_ranks))
        sparse_rank = sparse_ranks.get(table_name, len(sparse_ranks))
        rrf_score = (1.0 / (k + dense_rank)) + (1.0 / (k + sparse_rank))
        rrf_scores[table_name] = rrf_score

    # Sort by RRF score descending and take top_k
    top_tables = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

    ddls = []
    tables_used = []
    similarity_scores = {}

    # Normalize RRF scores roughly to 0-1 for display
    max_possible_rrf = (1.0 / k) + (1.0 / k)
    
    for table_name, rrf_score in top_tables:
        meta = table_meta_map[table_name]
        ddls.append(meta["raw_ddl"])
        tables_used.append(table_name)
        
        normalized_score = min(1.0, rrf_score / max_possible_rrf)
        similarity_scores[table_name] = round(normalized_score, 4)

    return {
        "schema_text": "\n".join(ddls),
        "tables_used": tables_used,
        "similarity_scores": similarity_scores,
    }


def is_index_ready() -> bool:
    """Check if the ChromaDB index exists and has data, without raising."""
    try:
        collection = _get_collection()
        return collection.count() > 0
    except Exception:
        return False
