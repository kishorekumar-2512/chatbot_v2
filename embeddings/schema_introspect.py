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
FKs + nullability + PKs + enums) so the index builder can detect exactly
which tables changed since the last run, instead of re-embedding all 234
every time.

v2: Enriched with column-level detail (nullable, PK/FK, defaults) and enum
value mapping (real Postgres enums + CHECK constraint pseudo-enums) for
improved RAG retrieval accuracy.
"""
import hashlib
import re
import psycopg2
import psycopg2.extras


# ── Maximum characters per embedding chunk ────────────────────────────────────
# all-MiniLM-L6-v2 has a 256 word-piece token limit.  Empirically, ~5000 chars
# of natural-language text stays comfortably within that.  We chunk at 5000 to
# keep each chunk fully representable by the model without silent truncation.
_MAX_CHUNK_CHARS = 5000


# ── Curated column-level descriptions and database lookup mappings ───────────
RICH_COLUMN_DESCRIPTIONS = {
    "device_certificate": {
        "status": "Active status of the certificate (e.g. True/False or active/revoked)",
        "issued_by": "The certificate authority or entity that issued the certificate (e.g. Let's Encrypt, DigiCert)",
        "issued_to": "The device or domain to which the certificate belongs",
        "serial_number": "Unique hardware or software serial identifier of the certificate",
    },
    "managed_device": {
        "device_name": "The hostname or user-friendly name of the managed machine",
        "zecure_org_id": "Organization tenant identifier to enforce strict data security boundaries",
        "status": "Active deployment status of the managed device (e.g. active, inactive, pending)",
    },
    "em_roles": {
        "role_type": "Role type category. One of [0 ('Super Admin'), 1 ('Admin'), 2 ('Technician')]",
    },
    "hardware_type": {
        "hardware_type": "Hardware type category code. One of [1 ('Operating System'), 2 ('BIOS'), 3 ('Processor'), 4 ('Logical Disk Partition'), 5 ('Keyboard'), 6 ('CD-ROM Drive'), 7 ('Hard Disk Drive'), 8 ('Sound Device'), 9 ('Video Controller'), 10 ('Network Adapter')]",
    },
    "asset_resource": {
        "asset_type": "Asset hardware type identifier. One of [1 ('Operating System'), 2 ('BIOS'), 3 ('Processor'), 4 ('Logical Disk Partition'), 5 ('Keyboard'), 6 ('CD-ROM Drive'), 7 ('Hard Disk Drive'), 8 ('Sound Device'), 9 ('Video Controller'), 10 ('Network Adapter'), 11 ('Pointing Device'), 12 ('Desktop Monitor'), 13 ('Mother Board'), 14 ('Battery'), 15 ('Printer'), 16 ('USB Hub'), 17 ('USB Controller'), 18 ('IDE Controller'), 19 ('PCMCIA Controller'), 20 ('Serial Port'), 21 ('Parallel Port'), 22 ('1394 Controller'), 23 ('Floppy Drive'), 24 ('Tape Drive'), 25 ('System Slot'), 26 ('Memory Slot'), 27 ('Physical Memory Array'), 28 ('TPM')]",
    },
    "patch_type_mapping": {
        "patch_type_id": "Patch category identifier. One of [1 ('Security - Security vulnerability fixes'), 2 ('Critical - Critical non-security fixes'), 3 ('Definition - Antivirus / signature updates'), 4 ('Feature - New feature additions'), 5 ('Upgrade - OS version upgrade'), 6 ('Non-Security'), 7 ('Driver'), 8 ('Rollup')]",
    },
    "software": {
        "software_category_id": "Software classification category. One of [1 ('Not Assigned'), 2 ('Development'), 3 ('UI Design'), 4 ('Productivity & Office Applications'), 5 ('Web Browsers'), 6 ('System Utilities'), 7 ('Security'), 8 ('Media & Graphics'), 9 ('Communication'), 10 ('Business'), 11 ('Miscellaneous')]",
    },
    "reports_type": {
        "category_id": "Report category identifier. One of [1 ('Security & Protection - TPM, Bitlocker, Antivirus, Firewall'), 2 ('Hardware Inventory - Hardware Age, Specs'), 3 ('Patch Management - Patch Summary, Missing Patches'), 4 ('Software Management - Software Inventory'), 5 ('General Overview')]",
    },
}


# ── Column-level metadata query ──────────────────────────────────────────────

def _fetch_column_metadata(cur, table: str) -> list[dict]:
    """Fetch rich per-column metadata from PostgreSQL system catalogs.

    Returns one dict per column with keys:
        column_name, data_type, udt_name, is_nullable, column_default,
        col_comment, is_primary_key
    """
    cur.execute("""
        SELECT
            c.column_name,
            c.data_type,
            c.udt_name,
            c.is_nullable,
            c.column_default,
            col_description(%(tbl)s::regclass, c.ordinal_position) AS col_comment,
            CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END AS is_primary_key
        FROM information_schema.columns c
        LEFT JOIN (
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema   = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema    = 'public'
              AND tc.table_name      = %(tbl)s
        ) pk ON pk.column_name = c.column_name
        WHERE c.table_schema = 'public'
          AND c.table_name   = %(tbl)s
        ORDER BY c.ordinal_position;
    """, {"tbl": table})
    return cur.fetchall()


# ── Legacy wrapper (keeps backward compat if anything imports it directly) ────

def _fetch_columns(cur, table: str) -> list[dict]:
    """Original 3-field column query, kept for any external callers."""
    cur.execute("""
        SELECT column_name, data_type,
               col_description(%s::regclass, ordinal_position) AS col_comment
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position;
    """, (table, table))
    return cur.fetchall()


# ── Table-level comment ──────────────────────────────────────────────────────

def _fetch_table_comment(cur, table: str) -> str | None:
    cur.execute("SELECT obj_description(%s::regclass, 'pg_class') AS c;", (table,))
    row = cur.fetchone()
    return row["c"] if row else None


# ── Foreign keys ─────────────────────────────────────────────────────────────

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


# ── Enum detection: real Postgres enums ──────────────────────────────────────

def _fetch_enum_values(cur, udt_name: str) -> list[str]:
    """Fetch all labels for a Postgres enum type, ordered by sort position."""
    cur.execute("""
        SELECT e.enumlabel
        FROM pg_enum e
        JOIN pg_type t ON e.enumtypid = t.oid
        WHERE t.typname = %s
        ORDER BY e.enumsortorder;
    """, (udt_name,))
    return [r["enumlabel"] for r in cur.fetchall()]


def _is_enum_type(cur, udt_name: str) -> bool:
    """Check whether a UDT name refers to a Postgres enum type."""
    cur.execute("""
        SELECT 1 FROM pg_type
        WHERE typname = %s AND typtype = 'e'
        LIMIT 1;
    """, (udt_name,))
    return cur.fetchone() is not None


# ── Enum detection: CHECK constraint pseudo-enums ────────────────────────────

def _fetch_check_enum_values(cur, table: str, column: str) -> list[str]:
    """Best-effort extraction of allowed values from CHECK constraints.

    Handles patterns like:
        CHECK ((status)::text = ANY ((ARRAY['active'::..., 'inactive'::...])::text[]))
        CHECK (status IN ('active', 'inactive'))
    Returns an empty list if the constraint is too complex to parse safely.
    """
    cur.execute("""
        SELECT pg_get_constraintdef(con.oid) AS constraint_def
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        WHERE con.contype = 'c'
          AND nsp.nspname = 'public'
          AND rel.relname = %s;
    """, (table,))

    for row in cur.fetchall():
        cdef = row["constraint_def"] or ""
        # Only process constraints that mention this specific column
        if column not in cdef:
            continue
        # Extract quoted string literals: 'value1', 'value2', ...
        values = re.findall(r"'([^']*)'(?:::)", cdef)
        if not values:
            # Fallback: simpler IN ('a', 'b') pattern without :: casts
            values = re.findall(r"'([^']*)'", cdef)
        if values:
            # Deduplicate while preserving order
            seen = set()
            unique = []
            for v in values:
                if v not in seen:
                    seen.add(v)
                    unique.append(v)
            return unique
    return []


# ── FK lookup helper ─────────────────────────────────────────────────────────

def _fk_hint(fks: list[dict]) -> str:
    if not fks:
        return ""
    rels = "; ".join(f"{fk['column']} -> {fk['references_table']}.{fk['references_column']}" for fk in fks)
    return f"Related to: {rels}."


def _fk_map(fks: list[dict]) -> dict[str, str]:
    """Build {column_name: 'table.column'} lookup from FK list."""
    return {fk["column"]: f"{fk['references_table']}.{fk['references_column']}" for fk in fks}


# ── Auto description (for tables with no manual or DB comment) ───────────────

def _auto_description(table: str, columns: list[dict], fks: list[dict]) -> str:
    col_names = [c["column_name"] for c in columns]
    commented = [(c["column_name"], c["col_comment"]) for c in columns if c.get("col_comment")]

    words = table.replace("_", " ")
    parts = [f"Table '{table}' stores {words} data."]

    if commented:
        parts.append("Documented columns: " + "; ".join(f"{n} - {c}" for n, c in commented[:6]) + ".")

    parts.append(f"Contains: {', '.join(col_names[:12])}{'...' if len(col_names) > 12 else ''}.")

    fk_h = _fk_hint(fks)
    if fk_h:
        parts.append(fk_h)

    # Cheap keyword expansion so BM25/semantic search still has something to
    # match against beyond the raw column list, without hand-writing it.
    keyword_hits = [w for w in words.split() if len(w) > 3]
    if keyword_hits:
        parts.append(f"Use for: {', '.join(keyword_hits)}.")

    return " ".join(parts)


# ── Enriched description builder ─────────────────────────────────────────────

def _build_enriched_description(
    table: str,
    table_comment: str | None,
    columns_meta: list[dict],
    fks: list[dict],
    enum_values: dict[str, list[str]],
    manual_override: str | None,
    column_overrides: dict[str, str] | None,
) -> tuple[str, str]:
    """Build a rich, natural-language embedding description for a table.

    Returns (description_text, source) where source is 'manual'/'db_comment'/'auto'.
    """
    fk_lookup = _fk_map(fks)

    # ── Header: table name + base description ────────────────────────────────
    if manual_override:
        header = manual_override.strip()
        source = "manual"
    elif table_comment:
        header = f"Table '{table}': {table_comment.strip()}"
        fk_h = _fk_hint(fks)
        if fk_h:
            header += f" {fk_h}"
        source = "db_comment"
    else:
        header = _auto_description(table, columns_meta, fks)
        source = "auto"

    # ── Column detail lines ──────────────────────────────────────────────────
    col_lines = []
    for c in columns_meta:
        col_name = c["column_name"]
        data_type = c.get("data_type", "unknown")
        udt_name = c.get("udt_name", "")
        nullable = c.get("is_nullable", "YES")
        default = c.get("column_default")
        is_pk = c.get("is_primary_key", False)
        comment = c.get("col_comment")

        # Apply column overrides
        if column_overrides and col_name in column_overrides:
            comment = column_overrides[col_name]

        display_type = udt_name if data_type == "USER-DEFINED" and udt_name else data_type

        # Build the annotation tags
        tags = []
        if is_pk:
            tags.append("PK")
        if col_name in fk_lookup:
            tags.append(f"FK -> {fk_lookup[col_name]}")
        if col_name in enum_values:
            tags.append("enum")
        if nullable == "NO":
            tags.append("NOT NULL")

        tag_str = ", ".join(tags)
        line = f"- {col_name} ({display_type}"
        if tag_str:
            line += f", {tag_str}"
        line += ")"

        # Default value (skip auto-generated sequences to reduce noise)
        if default and "nextval(" not in str(default):
            clean_default = str(default).strip()
            if len(clean_default) < 80:  # skip very long defaults
                line += f" [default: {clean_default}]"

        # Enum values
        enum_str = ""
        if col_name in enum_values and enum_values[col_name]:
            vals = enum_values[col_name]
            enum_str = f" One of [{', '.join(repr(v) for v in vals)}]."

        # Comment
        if comment:
            clean_comment = comment.strip().replace("\n", " ")
            line += f": {clean_comment}"
            if enum_str:
                line += f" --{enum_str}"
        elif enum_str:
            line += f":{enum_str}"

        col_lines.append(line)

    # ── Assemble full description ────────────────────────────────────────────
    parts = [header, "", "Columns:"] + col_lines

    fk_h = _fk_hint(fks)
    if fk_h:
        parts.append("")
        parts.append(fk_h)

    return "\n".join(parts), source


# ── Chunking ─────────────────────────────────────────────────────────────────

def _chunk_description(table: str, description: str, raw_ddl: str,
                       content_hash: str, source: str) -> list[dict]:
    """Split an enriched description into chunks if it exceeds _MAX_CHUNK_CHARS.

    Returns a list of table dicts.  The first entry uses the original table_name
    as its ID; subsequent chunks use '{table}_part{N}'.  Every chunk carries the
    full raw_ddl so retrieval always returns complete schema.
    """
    if len(description) <= _MAX_CHUNK_CHARS:
        return [{
            "table_name": table,
            "description": description,
            "raw_ddl": raw_ddl,
            "content_hash": content_hash,
            "source": source,
        }]

    # Split on column lines — find the "Columns:" header and split after it
    lines = description.split("\n")
    header_lines = []
    column_lines = []
    in_columns = False
    footer_lines = []
    past_columns = False

    for line in lines:
        if line.strip() == "Columns:":
            in_columns = True
            header_lines.append(line)
            continue
        if in_columns and line.startswith("- "):
            column_lines.append(line)
            continue
        if in_columns and not line.startswith("- ") and column_lines:
            # We've left the column section
            past_columns = True
            in_columns = False
            footer_lines.append(line)
            continue
        if past_columns:
            footer_lines.append(line)
        else:
            header_lines.append(line)

    header_text = "\n".join(header_lines)
    footer_text = "\n".join(footer_lines).strip()

    # Now distribute columns across chunks
    chunks = []
    current_cols = []
    current_len = len(header_text) + len("\nColumns:\n") + len(footer_text) + 50  # overhead

    for col_line in column_lines:
        line_len = len(col_line) + 1  # +1 for newline
        if current_len + line_len > _MAX_CHUNK_CHARS and current_cols:
            # Emit current chunk
            chunk_desc = header_text + "\nColumns:\n" + "\n".join(current_cols)
            if not chunks and footer_text:
                chunk_desc += "\n\n" + footer_text
            chunks.append(chunk_desc)
            current_cols = []
            current_len = len(header_text) + len("\nColumns:\n") + 50

        current_cols.append(col_line)
        current_len += line_len

    # Emit final chunk
    if current_cols:
        chunk_desc = header_text + "\nColumns:\n" + "\n".join(current_cols)
        if not chunks and footer_text:
            chunk_desc += "\n\n" + footer_text
        elif chunks and footer_text:
            chunk_desc += "\n\n" + footer_text
        chunks.append(chunk_desc)

    # Build result list
    results = []
    for i, chunk_desc in enumerate(chunks):
        chunk_name = table if i == 0 else f"{table}_part{i + 1}"
        chunk_hash = content_hash if i == 0 else f"{content_hash}_p{i + 1}"
        results.append({
            "table_name": chunk_name,
            "description": chunk_desc,
            "raw_ddl": raw_ddl,         # full DDL on every chunk
            "content_hash": chunk_hash,
            "source": source,
            "_base_table": table,        # so build_index knows the real table name
        })

    return results


# ── Main introspection entry point ───────────────────────────────────────────

def introspect_table(cur, table: str, manual_override: str | None = None,
                     column_overrides: dict[str, str] | None = None) -> dict:
    """
    Returns {table_name, description, raw_ddl, content_hash, source}.
    `source` is one of "manual" / "db_comment" / "auto" — surfaced so you can
    see at a glance which tables still don't have DB-level documentation.
    """
    columns_meta = _fetch_column_metadata(cur, table)
    table_comment = _fetch_table_comment(cur, table)
    fks = _fetch_foreign_keys(cur, table)

    # Merge column overrides into the comment field
    effective_col_overrides = column_overrides if column_overrides is not None else RICH_COLUMN_DESCRIPTIONS.get(table)
    if effective_col_overrides:
        for c in columns_meta:
            col_name = c["column_name"]
            if col_name in effective_col_overrides:
                c["col_comment"] = effective_col_overrides[col_name]

    # ── Detect enum values per column ────────────────────────────────────────
    enum_values: dict[str, list[str]] = {}
    for c in columns_meta:
        col_name = c["column_name"]
        udt_name = c.get("udt_name", "")

        # 1. Check for real Postgres enum type
        if udt_name and _is_enum_type(cur, udt_name):
            vals = _fetch_enum_values(cur, udt_name)
            if vals:
                enum_values[col_name] = vals
                continue

        # 2. Check for CHECK constraint pseudo-enum
        vals = _fetch_check_enum_values(cur, table, col_name)
        if vals:
            enum_values[col_name] = vals

    # ── Build raw_ddl (unchanged format for retrieval compatibility) ─────────
    col_defs_list = []
    for c in columns_meta:
        col_def = f"{c['column_name']} ({c['data_type']})"
        comment = c.get("col_comment")
        if comment:
            clean_comment = comment.strip().replace("\n", " ")
            col_def += f" -- {clean_comment}"
        col_defs_list.append(col_def)
    col_defs = ", ".join(col_defs_list)

    if table_comment:
        clean_table_comment = table_comment.strip().replace("\n", " ")
        raw_ddl = f"Table {table} ({col_defs}) -- Table Comment: {clean_table_comment}"
    else:
        raw_ddl = f"Table {table} ({col_defs})"

    # ── Content fingerprint ──────────────────────────────────────────────────
    # Includes nullable/PK/FK/enum info so hash changes when these change.
    fingerprint_parts = [
        col_defs,
        table_comment or "",
        "|".join(
            f"{c['column_name']}:{c.get('col_comment') or ''}:"
            f"{c.get('is_nullable', '')}:{c.get('is_primary_key', '')}"
            for c in columns_meta
        ),
        "|".join(f"{fk['column']}->{fk['references_table']}.{fk['references_column']}" for fk in fks),
        "|".join(f"{col}={','.join(vals)}" for col, vals in sorted(enum_values.items())),
    ]
    fingerprint_src = "|".join(fingerprint_parts)
    content_hash = hashlib.sha256(fingerprint_src.encode("utf-8")).hexdigest()[:16]

    # ── Build enriched description ───────────────────────────────────────────
    description, source = _build_enriched_description(
        table, table_comment, columns_meta, fks, enum_values,
        manual_override, column_overrides,
    )

    return {
        "table_name": table,
        "description": description,
        "raw_ddl": raw_ddl,
        "content_hash": content_hash,
        "source": source,
    }


def list_tables(cur) -> list[str]:
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """)
    return [r["table_name"] for r in cur.fetchall()]


def introspect_all(database_url: str, manual_overrides: dict[str, str],
                   column_overrides: dict[str, dict[str, str]] | None = None) -> list[dict]:
    """Introspect all tables and return a flat list of table dicts.

    Tables whose enriched description exceeds the embedding chunk limit are
    split into multiple entries (table, table_part2, ...).  Each entry carries
    the full raw_ddl so downstream retrieval always gets complete schema.
    """
    conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cur:
            tables = list_tables(cur)
            results = []
            for t in tables:
                entry = introspect_table(
                    cur, t,
                    manual_overrides.get(t),
                    column_overrides.get(t) if column_overrides else None,
                )
                # Chunk if too long for the embedding model
                chunks = _chunk_description(
                    entry["table_name"], entry["description"],
                    entry["raw_ddl"], entry["content_hash"], entry["source"],
                )
                results.extend(chunks)
            return results
    finally:
        conn.close()
