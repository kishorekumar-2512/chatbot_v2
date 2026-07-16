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

    query_embedding = model.encode([question]).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=min(top_k, collection.count()),
    )

    table_names = results["metadatas"][0]
    distances   = results["distances"][0]  # ChromaDB returns L2 distance by default

    ddls = []
    tables_used = []
    similarity_scores = {}

    for meta, dist in zip(table_names, distances):
        table_name = meta["table_name"]
        ddls.append(meta["raw_ddl"])
        tables_used.append(table_name)
        # Convert L2 distance to an approximate 0-1 similarity score for display/confidence scoring
        similarity = max(0.0, 1.0 - (dist / 2.0))
        similarity_scores[table_name] = round(similarity, 4)

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
