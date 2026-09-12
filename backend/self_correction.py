"""
backend/self_correction.py

Layer 6: Self-Correction Loop
- SQL diff retry: shows LLM all previous failed attempts + errors, not just last one
- SQL quality checks: static warnings on SELECT *, LIMIT, text comparisons, and boolean comparisons
"""

import re


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


# ── SQL quality checks ────────────────────────────────────────────────────────

def check_sql_quality(sql: str) -> list[str]:
    """
    Static quality checks beyond schema validation.
    Returns list of warnings (not errors — these don't block SQL generation).
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
