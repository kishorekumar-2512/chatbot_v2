"""
backend/sql_validator.py

SQL validation logic — preserved from the existing system as requested.
Checks that referenced tables and columns actually exist before execution.
"""

import re

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|CREATE|ATTACH|"
    r"COPY|CALL|EXECUTE|VACUUM|MERGE|REINDEX|CLUSTER|LOCK)\b", re.IGNORECASE
)


def extract_sql(text: str) -> str:
    """Pull the SQL SELECT statement out of LLM output."""
    m = re.search(r"```sql\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"(SELECT\s.+?;)", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text.strip()


def validate_sql(sql: str, known_tables: set, known_columns: dict) -> list[str]:
    """
    Returns a list of human-readable error strings (empty list = valid).
    Checks:
      - statement is a SELECT (optionally preceded by a WITH ... CTE block)
      - every FROM/JOIN table exists in known_tables (CTE names excluded)
      - every table.column reference exists in known_columns
    """
    errors = []

    if not re.match(r"^\s*(SELECT|WITH)\b", sql, re.IGNORECASE):
        errors.append("Query must be a SELECT statement.")
        return errors

    # Security: reject any write/DDL keyword ANYWHERE in the statement, not
    # just checking the first word. Postgres allows data-modifying CTEs like
    # `WITH t AS (DELETE FROM x RETURNING *) SELECT * FROM t`, so a
    # start-of-string check alone is not a real safety boundary once WITH
    # is permitted through.
    if _FORBIDDEN_KEYWORDS.search(sql):
        errors.append("Query contains a write/DDL keyword (INSERT/UPDATE/DELETE/DROP/etc.) — only read-only SELECT queries are allowed.")
        return errors

    # Security: reject multiple chained statements. psycopg2's execute() will
    # run every ';'-separated statement in one call — previously a
    # hallucinated `SELECT * FROM a; SELECT * FROM b;` would silently run
    # both instead of being rejected as invalid.
    if ";" in sql.strip().rstrip(";"):
        errors.append("Multiple SQL statements are not allowed — write exactly one SELECT query.")
        return errors

    if not known_tables:
        return errors  # nothing to validate against yet

    # CTE names declared via `WITH x AS (...)` or `, y AS (...)` are local to
    # this query, not real tables — without this, every complex query using
    # a CTE (needed for window functions / multi-step logic) would get
    # rejected as referencing an "unknown table".
    cte_matches = re.findall(
        r'\bWITH\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(|,\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(',
        sql, re.IGNORECASE
    )
    cte_names = {g.lower() for pair in cte_matches for g in pair if g}

    table_refs = re.findall(
        r'(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*))?',
        sql, re.IGNORECASE
    )
    alias_map = {}
    for real, alias in table_refs:
        real_lower = real.lower()
        if real_lower in cte_names:
            # Local CTE reference — not a schema table, skip the unknown-table check.
            if alias:
                alias_map[alias.lower()] = real_lower
            alias_map[real_lower] = real_lower
            continue
        if real_lower.startswith("information_schema"):
            # System schema reference — allow meta-queries without strict validation.
            if alias:
                alias_map[alias.lower()] = real_lower
            alias_map[real_lower] = real_lower
            continue
        if real_lower not in known_tables:
            # NOTE: previously this dumped all 234 known table names into the
            # error string, which then gets echoed back into the retry prompt
            # via build_retry_context() — bloating every retry attempt by
            # thousands of tokens and making the num_ctx truncation problem
            # much worse. Keep it short instead.
            errors.append(f"Unknown table: '{real}'. It does not exist in the schema — use one of the tables listed above.")
        else:
            if alias:
                alias_map[alias.lower()] = real_lower
            alias_map[real_lower] = real_lower

    col_refs = re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)', sql)
    for tbl_or_alias, col in col_refs:
        tbl = alias_map.get(tbl_or_alias.lower(), tbl_or_alias.lower())
        if tbl.startswith("information_schema"):
            continue
        if tbl in known_columns:
            valid_cols = [c.lower() for c in known_columns[tbl]]
            if col.lower() not in valid_cols:
                errors.append(
                    f"Column '{col}' not found in table '{tbl}'. "
                    f"Available: {', '.join(known_columns[tbl])}"
                )

    return errors
