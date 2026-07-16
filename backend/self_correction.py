"""
backend/self_correction.py

Layer 6: Self-Correction Loop
- SQL diff retry: shows LLM all previous failed attempts + errors, not just last one
- Zero-row diagnosis: when query returns 0 rows, diagnose why and suggest fix
- Result sanity check: verify answer actually addresses the question
- Auto-explain: generate human-readable explanation of results
"""

import re
import json
from typing import Optional


# ── Retry context builder ─────────────────────────────────────────────────────

def build_retry_context(failed_attempts: list[tuple[str, str]]) -> str:
    """
    Build a diff-style context showing all previous failures.
    failed_attempts: list of (sql, error_message) tuples
    """
    if not failed_attempts:
        return ""

    ctx = "\n⚠️  PREVIOUS FAILED ATTEMPTS — do NOT repeat these mistakes:\n"
    for i, (sql, error) in enumerate(failed_attempts, 1):
        ctx += f"\n--- Attempt {i} (FAILED) ---\n"
        ctx += f"SQL tried:\n{sql}\n"
        ctx += f"Error: {error}\n"

    ctx += "\nFix the specific error above. Write a DIFFERENT query that avoids these mistakes.\n"
    return ctx


# ── Zero-row diagnosis ────────────────────────────────────────────────────────
ZERO_ROW_DIAGNOSE_PROMPT = """
The following SQL query returned 0 rows from a PostgreSQL database.

SQL:
{sql}

Possible reasons for 0 rows (diagnose which applies):
1. Wrong ILIKE pattern — value may be stored differently (e.g. 'Intel Core i7' not 'Intel 7')
2. Wrong JOIN path — tables may not connect the way the query assumes  
3. Filter too strict — combining multiple WHERE conditions excludes all rows
4. Boolean column used as string — use = true / = false not = 'true'
5. Data genuinely doesn't exist for this filter combination
6. Wrong table — the data may be in a different table than assumed

Based on the SQL above, identify the most likely reason and rewrite the query to fix it.
Return ONLY the fixed SQL in a ```sql ... ``` block.
"""

async def diagnose_zero_rows(sql: str, generate_fn) -> Optional[str]:
    """
    When a query returns 0 rows, ask the LLM to diagnose and rewrite.
    generate_fn: the model router's generate function
    Returns fixed SQL string, or None if diagnosis fails.
    """
    prompt = ZERO_ROW_DIAGNOSE_PROMPT.format(sql=sql)
    try:
        raw, _ = await generate_fn(prompt, max_tokens=300)
        m = re.search(r"```sql\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
        if m:
            fixed_sql = m.group(1).strip()
            if re.match(r"^\s*SELECT", fixed_sql, re.IGNORECASE):
                return fixed_sql
    except Exception:
        pass
    return None


# ── Result sanity check ───────────────────────────────────────────────────────
SANITY_CHECK_PROMPT = """
A user asked: "{question}"

The SQL query returned {row_count} rows.
First few rows: {sample_rows}

Does this result CORRECTLY answer the user's question?
Reply with EXACTLY: YES or NO, then one sentence explaining why.
"""

async def sanity_check(question: str, sql: str, rows: list[dict],
                       generate_fn) -> tuple[bool, str]:
    """
    Quick LLM check: does the result actually answer the question?
    Returns (passed: bool, reason: str)
    """
    if not rows:
        return False, "Query returned 0 rows."

    sample = rows[:3]
    # Truncate long values
    safe_sample = [
        {k: (str(v)[:50] if v else v) for k, v in row.items()}
        for row in sample
    ]

    prompt = SANITY_CHECK_PROMPT.format(
        question=question,
        row_count=len(rows),
        sample_rows=json.dumps(safe_sample, default=str),
    )

    try:
        raw, _ = await generate_fn(prompt, max_tokens=100)
        raw = raw.strip()
        passed = raw.upper().startswith("YES")
        reason = raw[3:].strip() if len(raw) > 3 else raw
        return passed, reason
    except Exception:
        return True, "Sanity check skipped."


# ── Auto-explain results ───────────────────────────────────────────────────────
EXPLAIN_PROMPT = """
A user asked: "{question}"

The SQL returned {row_count} rows. Here are the first few:
{sample_rows}
{stats_block}
Write a clear 3-5 sentence business summary of what this data shows. Be specific:
mention actual numbers, notable outliers, and what stands out (a leader, a gap,
a concentration). If the stats above show a clear skew or trend, call it out.
Do NOT mention SQL, tables, or technical terms.
"""

async def generate_answer(question: str, rows: list[dict], generate_fn, quick_stats: list[str] | None = None) -> str:
    """
    Generate a natural language answer from query results.
    Better than the old "after the SQL block" extraction approach.

    `quick_stats` (optional): deterministic pandas-computed facts (sums,
    averages, top category, date range) from insights.compute_quick_stats().
    Grounding the prompt in these means the narrative reports real numbers
    instead of the model eyeballing trends from only the first 5 rows.
    """
    if not rows:
        return "The query returned no results. This could mean no data matches your criteria, or the filter values may not exactly match what's stored in the database."

    sample = rows[:5]
    safe_sample = [
        {k: (str(v)[:80] if v else v) for k, v in row.items()}
        for row in sample
    ]

    stats_block = ""
    if quick_stats:
        stats_block = "\nComputed statistics across ALL rows (use these for specifics, not just the sample above):\n" + \
            "\n".join(f"- {s}" for s in quick_stats) + "\n"

    prompt = EXPLAIN_PROMPT.format(
        question=question,
        row_count=len(rows),
        sample_rows=json.dumps(safe_sample, default=str),
        stats_block=stats_block,
    )

    try:
        answer, _ = await generate_fn(prompt, max_tokens=350)
        return answer.strip()
    except Exception:
        return f"Query returned {len(rows)} rows successfully."


# ── SQL quality checks ────────────────────────────────────────────────────────
def check_sql_quality(sql: str) -> list[str]:
    """
    Static quality checks beyond schema validation.
    Returns list of warnings (not errors — these don't block execution).
    """
    warnings = []
    sql_upper = sql.upper()

    # Warn if SELECT * used (may return too many columns)
    if "SELECT *" in sql_upper:
        warnings.append("Uses SELECT * — consider selecting specific columns")

    # Warn if no LIMIT on large potential result sets
    if "LIMIT" not in sql_upper and "COUNT" not in sql_upper:
        warnings.append("No LIMIT clause — may return large result set")

    # Warn if = used for common text columns (should use ILIKE)
    text_col_exact = re.findall(
        r"(platform|status|severity|priority|processor|device_type)\s*=\s*'[^']*'",
        sql, re.IGNORECASE
    )
    if text_col_exact:
        warnings.append(
            f"Exact match (=) used on text columns {text_col_exact} — "
            "consider ILIKE '%value%' for better results"
        )

    # Warn if boolean used as string
    bool_as_str = re.findall(
        r"(agent_status|is_active|is_resolved|is_encrypted|is_enabled)\s*=\s*'(true|false)'",
        sql, re.IGNORECASE
    )
    if bool_as_str:
        warnings.append(
            f"Boolean columns {[b[0] for b in bool_as_str]} compared as strings — "
            "use = true or = false (no quotes)"
        )

    return warnings


# ── Deterministic auto-repair (no LLM call) ─────────────────────────────────────
# A handful of Postgres execution errors are purely MECHANICAL — fixing them
# doesn't require "understanding" the question, just pattern-matching the
# error text. Retrying with the LLM for these wastes a full round-trip (and
# small local models often make the exact same mistake twice in a row anyway
# — telling them "don't do X" in an error message doesn't reliably work).
# Trying these fixes first is faster AND more reliable than another attempt.

def try_auto_repair(sql: str, error: str) -> str | None:
    """
    Returns a patched SQL string if a known mechanical fix applies, else None
    (falls back to the normal LLM retry path). The patched SQL should still
    be run through validate_sql() before execution — this only targets the
    specific error class, it doesn't re-verify the whole query.
    """
    error_lower = (error or "").lower()

    # SELECT DISTINCT + ORDER BY on a column not in the SELECT list.
    # Postgres requires ORDER BY expressions to appear in the SELECT list
    # when DISTINCT is used — a very common LLM mistake, and mechanically
    # fixable: just add the missing column(s) to the SELECT list.
    if "for select distinct, order by expressions must appear in select list" in error_lower:
        return _fix_distinct_order_by(sql)

    return None


def _fix_distinct_order_by(sql: str) -> str | None:
    m_select = re.search(r"SELECT\s+DISTINCT\s+(.*?)\s+FROM\s", sql, re.IGNORECASE | re.DOTALL)
    m_order = re.search(r"ORDER\s+BY\s+(.*?)(?:\bLIMIT\b|\bOFFSET\b|;|\Z)", sql, re.IGNORECASE | re.DOTALL)
    if not m_select or not m_order:
        return None

    select_list_raw = m_select.group(1)
    order_list_raw = m_order.group(1)

    select_cols = [c.strip() for c in select_list_raw.split(",")]
    select_cols_normalized = {
        re.sub(r"\s+AS\s+\w+$", "", c, flags=re.IGNORECASE).strip().lower() for c in select_cols
    }

    order_terms = [t.strip() for t in order_list_raw.split(",") if t.strip()]
    missing = []
    for term in order_terms:
        col_expr = re.sub(r"\s+(ASC|DESC)(\s+NULLS\s+(FIRST|LAST))?\s*$", "", term, flags=re.IGNORECASE).strip()
        if col_expr and col_expr.lower() not in select_cols_normalized:
            missing.append(col_expr)

    if not missing:
        return None  # couldn't identify the missing column — don't guess, let the LLM retry instead

    new_select_list = select_list_raw.rstrip() + ", " + ", ".join(missing)
    return sql[:m_select.start(1)] + new_select_list + sql[m_select.end(1):]
