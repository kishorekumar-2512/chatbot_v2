"""
embeddings/schema_introspect.py

Replaces "someone hand-writes a description for every table" with descriptions
synthesized from the database's OWN metadata — which is what makes this safe
to run automatically against a cloud DB that changes on its own schedule,
instead of requiring a person to notice and update a Python dict.

Priority order for a table's description:
  1. Manual override (RICH_DESCRIPTIONS in build_index.py) — if you've hand-
     written a great description, it still wins. This is additive, not a
     replacement.
  2. PostgreSQL COMMENT ON TABLE / COMMENT ON COLUMN, if your DB team
     documents schema meaning at the database level (the standard way to do
     this in Postgres) — genuinely richer than guessing from column names.
  3. Auto-synthesized from columns + foreign keys + the table name itself.

Also computes a stable content hash per table (columns + types + comments +
FKs) so the index builder can detect exactly which tables changed since the
last run, instead of re-embedding all 234 every time.
"""
import hashlib
import psycopg2
import psycopg2.extras


def _fetch_columns(cur, table: str) -> list[dict]:
    cur.execute("""
        SELECT column_name, data_type,
               col_description(%s::regclass, ordinal_position) AS col_comment
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position;
    """, (table, table))
    return cur.fetchall()


def _fetch_table_comment(cur, table: str) -> str | None:
    cur.execute("SELECT obj_description(%s::regclass, 'pg_class') AS c;", (table,))
    row = cur.fetchone()
    return row["c"] if row else None


def _fetch_foreign_keys(cur, table: str) -> list[dict]:
    """Returns [{column, references_table, references_column}, ...] — both
    outgoing FKs (this table -> others) for join/relationship hints."""
    cur.execute("""
        SELECT
            kcu.column_name AS column,
            ccu.table_name AS references_table,
            ccu.column_name AS references_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public' AND tc.table_name = %s;
    """, (table,))
    return cur.fetchall()


def introspect_table(cur, table: str, manual_override: str | None = None) -> dict:
    """
    Returns {table_name, description, raw_ddl, content_hash, source}.
    `source` is one of "manual" / "db_comment" / "auto" — surfaced so you can
    see at a glance which tables still don't have DB-level documentation.
    """
    columns = _fetch_columns(cur, table)
    table_comment = _fetch_table_comment(cur, table)
    fks = _fetch_foreign_keys(cur, table)

    col_defs = ", ".join(f"{c['column_name']} ({c['data_type']})" for c in columns)
    raw_ddl = f"Table {table} ({col_defs})"

    # Content fingerprint — anything in here changing means the description
    # (and the embedding built from it) is stale and needs regenerating.
    fingerprint_src = "|".join([
        col_defs,
        table_comment or "",
        "|".join(f"{c['column_name']}:{c['col_comment'] or ''}" for c in columns),
        "|".join(f"{fk['column']}->{fk['references_table']}.{fk['references_column']}" for fk in fks),
    ])
    content_hash = hashlib.sha256(fingerprint_src.encode("utf-8")).hexdigest()[:16]

    if manual_override:
        return {"table_name": table, "description": manual_override, "raw_ddl": raw_ddl,
                "content_hash": content_hash, "source": "manual"}

    if table_comment:
        # DB-documented — still enrich with FK relationship hints, which
        # COMMENT ON TABLE text usually won't restate.
        fk_hint = _fk_hint(fks)
        desc = f"Table '{table}': {table_comment.strip()}"
        if fk_hint:
            desc += f" {fk_hint}"
        return {"table_name": table, "description": desc, "raw_ddl": raw_ddl,
                "content_hash": content_hash, "source": "db_comment"}

    # Fully auto-synthesized fallback — still meaningfully better than just
    # listing columns, because it surfaces relationships and column-level
    # comments if any individual columns (but not the table) are documented.
    desc = _auto_description(table, columns, fks)
    return {"table_name": table, "description": desc, "raw_ddl": raw_ddl,
            "content_hash": content_hash, "source": "auto"}


def _fk_hint(fks: list[dict]) -> str:
    if not fks:
        return ""
    rels = "; ".join(f"{fk['column']} \u2192 {fk['references_table']}.{fk['references_column']}" for fk in fks)
    return f"Related to: {rels}."


def _auto_description(table: str, columns: list[dict], fks: list[dict]) -> str:
    col_names = [c["column_name"] for c in columns]
    commented = [(c["column_name"], c["col_comment"]) for c in columns if c["col_comment"]]

    words = table.replace("_", " ")
    parts = [f"Table '{table}' stores {words} data."]

    if commented:
        parts.append("Documented columns: " + "; ".join(f"{n} \u2014 {c}" for n, c in commented[:6]) + ".")

    parts.append(f"Contains: {', '.join(col_names[:12])}{'...' if len(col_names) > 12 else ''}.")

    fk_hint = _fk_hint(fks)
    if fk_hint:
        parts.append(fk_hint)

    # Cheap keyword expansion so BM25/semantic search still has something to
    # match against beyond the raw column list, without hand-writing it.
    keyword_hits = [w for w in words.split() if len(w) > 3]
    if keyword_hits:
        parts.append(f"Use for: {', '.join(keyword_hits)}.")

    return " ".join(parts)


def list_tables(cur) -> list[str]:
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """)
    return [r["table_name"] for r in cur.fetchall()]


def introspect_all(database_url: str, manual_overrides: dict[str, str]) -> list[dict]:
    conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cur:
            tables = list_tables(cur)
            return [introspect_table(cur, t, manual_overrides.get(t)) for t in tables]
    finally:
        conn.close()
