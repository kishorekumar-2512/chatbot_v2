"""
backend/insights.py

Two small, deterministic (no LLM call) helpers that make results feel richer
and more interactive without adding latency or hallucination risk:

  - compute_quick_stats(rows): pandas-based summary stats (sums, averages,
    top category, date range) shown as a "quick stats" strip in the UI and
    also fed into the answer-writing prompt so the narrative is grounded in
    real numbers instead of the model guessing at trends from 5 sample rows.

  - generate_followups(...): a handful of contextual next-question
    suggestions based on the shape of the result (has a date column? was
    this a TOP_N query? is there an obvious breakdown dimension?), rendered
    as clickable chips in the UI.

Both are pure Python/pandas — fast, always accurate to the data, and safe to
call on every request.
"""
from __future__ import annotations

import pandas as pd


def compute_quick_stats(rows: list[dict]) -> list[str]:
    """Return a short list of human-readable stat strings, or [] if nothing useful."""
    if not rows:
        return []

    try:
        df = pd.DataFrame(rows)
    except Exception:
        return []

    stats: list[str] = []
    stats.append(f"Rows: {len(df):,}")

    # Numeric columns — surface sum/avg/max for up to 2 of them (skip when
    # there's only 1 row: total == avg == max, so the line adds no information)
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if len(df) > 1:
        for col in numeric_cols[:2]:
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if series.empty:
                continue
            total = series.sum()
            avg = series.mean()
            if total == int(total):
                total_str = f"{int(total):,}"
            else:
                total_str = f"{total:,.2f}"
            stats.append(f"{col}: total {total_str} · avg {avg:,.1f} · max {series.max():,.0f}")
    elif len(df) == 1:
        for col in numeric_cols[:2]:
            val = df.iloc[0][col]
            if pd.notna(val):
                try:
                    stats.append(f"{col}: {val:,}")
                except (ValueError, TypeError):
                    stats.append(f"{col}: {val}")

    # A likely "label" column (first non-numeric, low/medium cardinality) + a numeric
    # metric column — call out the top entry, e.g. "Top: Chrome (312)"
    label_cols = [c for c in df.columns if c not in numeric_cols]
    if label_cols and numeric_cols:
        label_col, metric_col = label_cols[0], numeric_cols[0]
        try:
            top_row = df.loc[pd.to_numeric(df[metric_col], errors="coerce").idxmax()]
            stats.append(f"Top {label_col.replace('_', ' ')}: {top_row[label_col]} ({top_row[metric_col]:,})")
        except Exception:
            pass

    # Date/timestamp-like column → date range
    for col in df.columns:
        if any(k in col.lower() for k in ("date", "time", "_at", "created", "updated")):
            try:
                parsed = pd.to_datetime(df[col], errors="coerce").dropna()
                if len(parsed) >= 2:
                    stats.append(f"{col.replace('_', ' ')} range: {parsed.min().date()} → {parsed.max().date()}")
                    break
            except Exception:
                continue

    # Categorical breakdown share, if there's a clearly categorical column
    # (low cardinality relative to row count, and it's not the label column
    # already summarized above)
    for col in label_cols[1:3]:
        try:
            nunique = df[col].nunique(dropna=True)
            if 1 < nunique <= min(15, max(2, len(df) // 2)):
                top_val = df[col].value_counts().idxmax()
                top_count = df[col].value_counts().max()
                pct = round(100 * top_count / len(df))
                stats.append(f"Most common {col.replace('_', ' ')}: '{top_val}' ({pct}% of rows)")
                break
        except Exception:
            continue

    return stats[:5]


def generate_followups(question: str, rows: list[dict], sql: str, intent: str | None) -> list[str]:
    """Return up to 4 short, clickable follow-up question suggestions."""
    if not rows:
        return []

    suggestions: list[str] = []
    try:
        df = pd.DataFrame(rows)
    except Exception:
        return []

    cols = list(df.columns)
    numeric_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    date_cols = [c for c in cols if any(k in c.lower() for k in ("date", "time", "_at"))]
    label_cols = [c for c in cols if c not in numeric_cols and c not in date_cols]
    sql_lower = (sql or "").lower()

    if intent == "TOP_N":
        suggestions.append("Show the next 10 results")
        suggestions.append("Show the bottom 10 instead")
    elif intent in ("COUNT", "AGGREGATE"):
        if "group by" not in sql_lower and label_cols:
            suggestions.append(f"Break this down by {label_cols[0].replace('_', ' ')}")
        suggestions.append("Compare this to last month")
    elif intent == "TREND":
        suggestions.append("Show this as a chart")
    elif intent == "LIST":
        if len(rows) >= 20:
            suggestions.append("Just show the top 10")

    if date_cols and "date_trunc" not in sql_lower and intent != "TREND":
        suggestions.append(f"Show the trend over {date_cols[0].replace('_', ' ')}")

    if numeric_cols and "avg(" not in sql_lower and "count(" not in sql_lower:
        suggestions.append(f"What's the average {numeric_cols[0].replace('_', ' ')}?")

    if label_cols and len(label_cols) > 1 and "group by" not in sql_lower:
        suggestions.append(f"Break this down by {label_cols[1].replace('_', ' ')} too")

    # De-dupe while preserving order, cap at 4
    seen = set()
    deduped = []
    for s in suggestions:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped[:4]
