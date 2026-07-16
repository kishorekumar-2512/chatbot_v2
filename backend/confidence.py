"""
backend/confidence.py

Calculates a confidence score for every successful SQL generation,
made of 4 weighted signals:

  1. Table relevance score (30%) — avg cosine similarity of matched tables
  2. Column accuracy score (30%) — 100% if zero validator errors,
                                    minus 20 points per error found
  3. Attempt score        (20%) — attempt 1 = 100, attempt 2 = 66, attempt 3 = 33
  4. Row sanity score     (20%) — 0 rows = 20, 1-1000 rows = 100, >10000 rows = 50

Overall = weighted average of the 4 signals.
Level   = "high" (>=80) / "medium" (>=55) / "low" (<55)
"""

from dataclasses import dataclass, asdict


WEIGHTS = {
    "table_relevance": 0.30,
    "column_accuracy": 0.30,
    "attempt_score":   0.20,
    "row_sanity":      0.20,
}


def _attempt_score(attempt_number: int) -> float:
    """attempt 1 = 100, attempt 2 = 66, attempt 3 = 33, anything beyond = 10."""
    return {1: 100.0, 2: 66.0, 3: 33.0}.get(attempt_number, 10.0)


def _row_sanity_score(row_count: int) -> float:
    if row_count == 0:
        return 20.0
    if row_count > 10000:
        return 50.0
    if 1 <= row_count <= 1000:
        return 100.0
    # Between 1000 and 10000 — linearly taper from 100 down to 50
    return 100.0 - ((row_count - 1000) / 9000.0) * 50.0


def _column_accuracy_score(validation_errors: list[str]) -> float:
    """100 if no errors, minus 20 per error, floor at 0."""
    score = 100.0 - (20.0 * len(validation_errors))
    return max(0.0, score)


def _table_relevance_score(similarity_scores: dict, tables_used: list[str]) -> float:
    """
    Average cosine similarity (0-1 from retrieval) of the tables that were
    actually matched, scaled to 0-100. If no similarity data is available
    (e.g. retrieval wasn't used), default to a neutral 75.
    """
    if not similarity_scores or not tables_used:
        return 75.0
    relevant = [similarity_scores[t] for t in tables_used if t in similarity_scores]
    if not relevant:
        return 75.0
    avg = sum(relevant) / len(relevant)
    return round(avg * 100, 2)


def calculate_confidence(
    similarity_scores: dict,
    tables_used: list[str],
    validation_errors: list[str],
    attempt_number: int,
    row_count: int,
) -> dict:
    """
    Returns a dict ready to drop straight into the API response:
    {
        "table_relevance": float,
        "column_accuracy": float,
        "attempt_score": float,
        "row_sanity": float,
        "overall": float,
        "level": "high" | "medium" | "low"
    }
    """
    table_relevance = _table_relevance_score(similarity_scores, tables_used)
    column_accuracy = _column_accuracy_score(validation_errors)
    attempt_score   = _attempt_score(attempt_number)
    row_sanity      = _row_sanity_score(row_count)

    overall = (
        table_relevance * WEIGHTS["table_relevance"]
        + column_accuracy * WEIGHTS["column_accuracy"]
        + attempt_score   * WEIGHTS["attempt_score"]
        + row_sanity      * WEIGHTS["row_sanity"]
    )
    overall = round(overall, 2)

    if overall >= 80:
        level = "high"
    elif overall >= 55:
        level = "medium"
    else:
        level = "low"

    return {
        "table_relevance": round(table_relevance, 2),
        "column_accuracy": round(column_accuracy, 2),
        "attempt_score": round(attempt_score, 2),
        "row_sanity": round(row_sanity, 2),
        "overall": overall,
        "level": level,
    }
