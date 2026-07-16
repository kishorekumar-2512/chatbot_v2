"""
backend/main.py — Maximum accuracy version.

6-layer accuracy pipeline:
  L1: Query Intelligence  — intent + entity extraction + SQL skeleton
  L2: Hybrid Retrieval    — BM25 + ChromaDB + anchor table injection  
  L3: Schema Graph        — FK-aware join path injection
  L4: Context Assembly    — column value sampling + dynamic few-shot examples
  L5: SQL Generation      — chain-of-thought prompt + circuit breaker LLMs
  L6: Self Correction     — retry with diff context + zero-row diagnosis + sanity check
"""

import os, re, time, json, asyncio
from contextlib import asynccontextmanager
from typing import Optional

import psycopg2, psycopg2.extras, psycopg2.pool
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from backend.model_router import router as model_router
from backend.confidence import calculate_confidence
from backend.sql_validator import extract_sql, validate_sql
from backend.mcp_client import host as mcp_host
from backend.schema_graph import get_join_hints, force_anchor_tables
from backend.query_intelligence import build_query_context

# ChromaDB/embeddings may not be available on Windows (needs C++ build tools).
# Gracefully degrade: the backend works without semantic retrieval (falls back to full schema).
try:
    from backend.hybrid_retriever import (
        retrieve_tables, get_similar_examples,
        store_successful_example, build_value_hints, get_schema_for_tables,
    )
    from embeddings.retrieve import is_index_ready
    _HAS_EMBEDDINGS = True
except ImportError:
    _HAS_EMBEDDINGS = False
    def is_index_ready(): return False
    def retrieve_tables(*a, **kw): return {"tables_used": [], "similarity_scores": {}, "schema_text": ""}
    def get_similar_examples(*a, **kw): return ""
    def store_successful_example(*a, **kw): pass
    def build_value_hints(*a, **kw): return ""
    def get_schema_for_tables(*a, **kw): return ""

from backend.llm_key_store import (
    save_key, get_key, get_all_keys, delete_key, toggle_key,
    validate_key, call_customer_llm, SUPPORTED_PROVIDERS,
)
from backend.self_correction import (
    build_retry_context, diagnose_zero_rows,
    sanity_check, generate_answer, check_sql_quality, try_auto_repair,
)
from backend.insights import compute_quick_stats, generate_followups
from backend.chart_builder import build_chart
from backend.auth import get_current_user, AuthenticatedUser

load_dotenv()

DATABASE_URL    = os.getenv("DATABASE_URL")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:8501")
MAX_ATTEMPTS    = 3

# ── DB pool for schema validator cache ────────────────────────────────────────
_pool = psycopg2.pool.ThreadedConnectionPool(1, 5, DATABASE_URL)
_known_tables: set = set()
_known_columns: dict = {}
_cache_at: float = 0.0
SCHEMA_TTL = 300


def refresh_validator_cache():
    global _known_tables, _known_columns, _cache_at
    now = time.time()
    if _known_tables and now - _cache_at < SCHEMA_TTL:
        return
    conn = _pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public' AND table_type='BASE TABLE'
            """)
            tables = [r["table_name"] for r in cur.fetchall()]
            col_map = {}
            for t in tables:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=%s
                    ORDER BY ordinal_position
                """, (t,))
                col_map[t] = [c["column_name"] for c in cur.fetchall()]
        _known_tables = set(tables)
        _known_columns = col_map
        _cache_at = now
    finally:
        _pool.putconn(conn)


# ── Periodic auto-reindex ─────────────────────────────────────────────────────
# Runs the same incremental sync as POST /admin/reindex, on a timer, so the
# embedding index stays current against a cloud DB without anyone needing to
# trigger it by hand. Failures here are caught and logged only — they must
# never crash the app or affect the normal chat pipeline ("continues normal").
REINDEX_INTERVAL_HOURS = float(os.getenv("REINDEX_INTERVAL_HOURS", "24"))  # 0 disables it
_scheduler_task = None


async def _periodic_reindex_loop():
    if REINDEX_INTERVAL_HOURS <= 0:
        print("[periodic reindex] disabled (REINDEX_INTERVAL_HOURS=0)")
        return
    print(f"[periodic reindex] enabled — running every {REINDEX_INTERVAL_HOURS}h")
    while True:
        try:
            await asyncio.sleep(REINDEX_INTERVAL_HOURS * 3600)
            print("[periodic reindex] starting scheduled incremental sync...")
            await asyncio.to_thread(_run_reindex, False)  # incremental — cheap, safe to run often
            print(f"[periodic reindex] done: {_reindex_status.get('last_result')}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            # Never let a scheduling/introspection failure take the app down —
            # log it and try again on the next interval.
            print(f"[periodic reindex] failed (will retry next interval): {e}")


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler_task
    refresh_validator_cache()
    fetch_rich_descriptions()
    await mcp_host.start()
    _scheduler_task = asyncio.create_task(_periodic_reindex_loop())
    yield
    if _scheduler_task:
        _scheduler_task.cancel()
    await mcp_host.stop()


# ── App + security ────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="AI Database Report Chatbot — Max Accuracy", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
FRONTEND_ORIGIN_REACT = os.getenv("FRONTEND_ORIGIN_REACT", "http://localhost:5173")
CLOUDFRONT_ORIGIN = os.getenv("CLOUDFRONT_ORIGIN", "")  # e.g. https://d1234abcd.cloudfront.net
_cors_origins = [FRONTEND_ORIGIN, FRONTEND_ORIGIN_REACT]
if CLOUDFRONT_ORIGIN:
    _cors_origins.append(CLOUDFRONT_ORIGIN)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

# ── Rich descriptions from PostgreSQL comments ───────────────────────────────
TABLE_DESCRIPTIONS: dict = {}

def fetch_rich_descriptions():
    """Fetch table comments from PostgreSQL pg_catalog."""
    global TABLE_DESCRIPTIONS
    conn = _pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT c.relname AS table_name,
                       d.description
                FROM pg_catalog.pg_description d
                JOIN pg_catalog.pg_class c ON d.objoid = c.oid
                JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
                WHERE n.nspname = 'public' AND d.objsubid = 0
                ORDER BY c.relname
            """)
            TABLE_DESCRIPTIONS = {row["table_name"]: row["description"] for row in cur.fetchall()}
    except Exception:
        TABLE_DESCRIPTIONS = {}
    finally:
        _pool.putconn(conn)


# ── Chain-of-Thought system prompt ────────────────────────────────────────────
COT_SYSTEM_PROMPT = """You are a senior PostgreSQL analyst for an IT management platform (intern_db) with 234 tables.
Core tables: managed_device, managed_user, customer, device_info, agent_info, software,
software_version_managed_device, license_details, org_patch, device_patch, alerts, zecure_group, policy.

Before writing SQL, think step by step inside <think> tags. Keep each step to
ONE short line — this is a quick planning scratchpad, not an essay:
<think>
TABLES: (which tables, from the schema provided)
JOINS: (join path — note bigint IDs and junction tables like managed_device_managed_users)
FILTER: (WHERE conditions; note any boolean true/false without quotes)
TYPE: (COUNT / LIST / AGGREGATE / TOP_N / TREND)
</think>

Then write the SQL in ```sql ... ``` block.
After the closing ```, write ONE clear business-language sentence (no SQL terms).

Hard rules — violation means the SQL is WRONG:
1. ONLY SELECT statements. Never INSERT/UPDATE/DELETE/DROP.
2. Always alias tables in JOINs (e.g. managed_device md).
3. For ALL text/string searches use ILIKE '%value%'. NEVER use = 'value' for text.
4. For boolean columns (agent_status, is_active, is_encrypted, is_enabled, is_administrator,
   is_disabled, is_locked_out, status (boolean in device_certificate), tpmowned, auto_renew,
   approved, is_mandatory, reboot_required, is_default)
   use = true or = false WITHOUT quotes.
5. Use NULLIF to avoid division by zero.
6. Use DISTINCT when joining 1-to-many to avoid row duplication (this schema has MANY
   junction tables like managed_device_managed_users, license_details_managed_device).
7. All primary keys are bigint named 'id' EXCEPT: license_details_managed_device,
   license_details_managed_users (composite keys), invoices (invoice_id), subscriptions
   (subscription_id), plans (plan_id), editions (edition_id), payments (payment_id).
8. platform and status columns are often INTEGER codes, not text — check schema data_type
   before using ILIKE on them; only use ILIKE on character varying / text columns.

Few-shot examples (real schema):

Q: which devices have Intel i7 processor
```sql
SELECT DISTINCT md.device_name, di.processor
FROM managed_device md
JOIN device_info di ON di.managed_device_id = md.id
WHERE di.processor ILIKE '%i7%';
```
Devices whose processor information contains Intel i7.

Q: show devices with inactive agents
```sql
SELECT md.device_name, ai.agent_version, ai.upgrade_status
FROM managed_device md
JOIN agent_info ai ON ai.managed_device_id = md.id
WHERE ai.agent_status = false;
```
Devices where the monitoring agent is currently inactive.

Q: how many customers are there
```sql
SELECT COUNT(DISTINCT id) AS total_customers FROM customer;
```
Total number of customer accounts in the system.

Q: top 10 most installed software
```sql
SELECT s.name, COUNT(svmd.id) AS install_count
FROM software s
JOIN software_version sv ON sv.software_id = s.id
JOIN software_version_managed_device svmd ON svmd.software_version_id = sv.id
GROUP BY s.name
ORDER BY install_count DESC
LIMIT 10;
```
The 10 most widely installed software titles across all devices.

Q: devices with missing critical patches
```sql
SELECT DISTINCT md.device_name, op.title, op.severity
FROM managed_device md
JOIN device_missing_patch dmp ON dmp.managed_device_id = md.id
JOIN org_patch op ON op.patch_id = dmp.patch_id
WHERE op.severity ILIKE '%critical%';
```
Devices that are missing one or more critical-severity patches.

Q: which users logged in today
```sql
SELECT DISTINCT mu.username, mu.email, ulh.logon_time
FROM managed_user mu
JOIN user_logon_history ulh ON ulh.managed_user_id = mu.id
WHERE ulh.logon_time::date = CURRENT_DATE
ORDER BY ulh.logon_time DESC;
```
Users who logged in today, with their most recent logon time.
7. Always add ORDER BY for readability.
8. If filtering on platform/status/severity/priority: ALWAYS use ILIKE.
9. If using SELECT DISTINCT, every column in ORDER BY MUST also appear in
   the SELECT list — Postgres will reject it otherwise. Either add the
   ORDER BY column to the SELECT list, or don't use DISTINCT.
"""

# Extra guidance only injected for questions that look like they need
# multi-step logic (breakdowns, per-group rankings, trends, comparisons).
# Kept separate from the base prompt so simple questions stay fast and lean —
# only complex ones pay the extra token cost.
ADVANCED_SQL_HINTS = """
This looks like a more advanced analytical question. Extra tools available:
- CTEs for multi-step logic: WITH step_name AS (SELECT ...) SELECT ... FROM step_name.
- Window functions for "top N per group": RANK() OVER (PARTITION BY group_col ORDER BY metric DESC),
  then filter the OUTER query on rank <= N (window functions can't go in WHERE directly).
- Date bucketing for trends: DATE_TRUNC('month', some_timestamp_col)::date AS month.
- For period comparisons, use two CTEs (one per period) and JOIN or subtract them, or use
  FILTER (WHERE ...) inside aggregates, e.g. COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE - 30).
- A CTE name is NOT a real table — only reference real schema tables inside each CTE's own body.

Q: top 3 devices with the most missing patches, broken down by severity
```sql
WITH ranked AS (
  SELECT md.device_name, op.severity, COUNT(*) AS missing_count,
         RANK() OVER (PARTITION BY op.severity ORDER BY COUNT(*) DESC) AS rnk
  FROM managed_device md
  JOIN device_missing_patch dmp ON dmp.managed_device_id = md.id
  JOIN org_patch op ON op.patch_id = dmp.patch_id
  GROUP BY md.device_name, op.severity
)
SELECT device_name, severity, missing_count
FROM ranked
WHERE rnk <= 3
ORDER BY severity, rnk;
```
The top 3 devices with the most missing patches for each severity level.

Q: show login trend by month for the last 6 months
```sql
SELECT DATE_TRUNC('month', ulh.logon_time)::date AS month, COUNT(*) AS logon_count
FROM user_logon_history ulh
WHERE ulh.logon_time >= CURRENT_DATE - INTERVAL '6 months'
GROUP BY month
ORDER BY month;
```
Monthly login counts over the last 6 months.
"""

_COMPLEXITY_SIGNALS = re.compile(
    r"\b(compare|comparison|trend|correlat|breakdown|break\s+down|by\s+each|per\s+\w+|"
    r"year\s+over\s+year|month\s+over\s+month|\byoy\b|\bmom\b|percentage\s+of|%\s*of|ratio|growth|"
    r"top\s+\d+\s+per|running\s+total|cumulative|\brank\b|over\s+time|\bversus\b|\bvs\.?\b)\b",
    re.IGNORECASE,
)


def is_complex_query(question: str) -> bool:
    """
    Heuristic: does this question need multi-step SQL (CTEs, window functions,
    date bucketing) rather than a single flat SELECT? Used to widen retrieval,
    raise the token budget, and inject ADVANCED_SQL_HINTS only when it's
    actually needed — keeps simple questions fast.
    """
    if _COMPLEXITY_SIGNALS.search(question):
        return True
    # Two+ "and"/"or" connectors often signal multiple conditions or entities
    if len(re.findall(r"\band\b|\bor\b", question, re.IGNORECASE)) >= 2:
        return True
    return False


# ── Multi-turn context ────────────────────────────────────────────────────────
# Detects when a question is a follow-up ("filter that to critical only",
# "now break it down by month", "what about last quarter") rather than a
# fresh, self-contained question. Only THEN is the previous question/SQL
# injected into the prompt — keeping simple standalone questions just as
# fast/lean as before, since most questions aren't follow-ups.
_CONTINUATION_RE = re.compile(
    r"\b(this|that|it|those|these|same|again|also|instead|now\s+show|now\s+break|"
    r"what\s+about|filter\s+(it\s+|this\s+)?(further|down|to)|narrow\s+(it\s+|this\s+)?down|"
    r"break\s+(it|this)\s+down|show\s+(the\s+)?same|just\s+the|only\s+the)\b",
    re.IGNORECASE,
)


def is_followup_question(question: str) -> bool:
    return bool(_CONTINUATION_RE.search(question))


def _error_signature(err: str) -> str:
    """
    Normalizes an error message so the SAME CLASS of mistake (e.g. "unknown
    table: 'foo'" vs "unknown table: 'bar'") is recognized as a repeat, even
    though the exact table/column name differs. Used to detect when the
    local model is stuck making the same kind of error twice — at that
    point another identical attempt is very unlikely to help; escalating to
    a bigger fallback model is more likely to actually fix it.
    """
    return re.sub(r"'[^']*'", "'X'", err or "")[:60].lower()


def build_conversation_context_block(context: "ConversationContext | None", question: str) -> str:
    """
    Returns a short prompt block resolving pronouns/continuations against
    the previous turn, or "" if this doesn't look like a follow-up (or there
    is no previous turn to reference).
    """
    if not context or not is_followup_question(question):
        return ""
    prev_sql = (context.sql or "")[:600]
    return f"""
CONVERSATION CONTEXT — this looks like a follow-up question:
Previous question: "{context.question}"
Previous SQL used:
{prev_sql}
Previous tables involved: {', '.join(context.tables_used) or '(none)'}

The current question likely refers back to the above (words like "that",
"it", "those", "now show", "what about"). Build on the same tables/filters
where it makes sense, adjusting only what the new question actually changes.
Do not blindly repeat the old SQL — adapt it to what's being asked now.
"""


# ── Meta / schema-introspection bypass ───────────────────────────────────────
# Questions like "list all tables", "what columns does X have", "show me the
# schema" aren't data questions — they're questions about the schema itself,
# which we already have fully cached in _known_tables / _known_columns. Two
# real bugs came from routing these into the normal NL→SQL pipeline instead:
#   1. The model correctly writes `SELECT table_name FROM information_schema
#      .tables`, but the validator only knows the ~234 *business* tables, so
#      it rejects `information_schema` as "unknown" and burns all 3 retries.
#   2. For "every table's columns", the model has no way to express that as
#      one query and hallucinates a chain of `SELECT * FROM a; SELECT * FROM
#      b; ...`, which either errors or silently returns the wrong table's rows.
# Answering these directly from the cache is both instant (no LLM call at
# all) and always correct, since it's just reading the schema we already have.

_META_ALL_COLUMNS_RE = re.compile(
    r"\b(all|every)\s+column(s)?\s+(of|for|in)\s+(every|all)\s+table|"
    r"\bfull\s+schema\b|\bentire\s+schema\b|\bwhole\s+schema\b", re.IGNORECASE
)
_META_LIST_TABLES_RE = re.compile(
    r"\blist\s+(all\s+|the\s+)?tables\b|\bshow\s+(me\s+)?(all\s+|the\s+)?tables\b|"
    r"\bwhat\s+tables\b|\bhow\s+many\s+tables\b|\ball\s+tables\b|"
    r"\btables?\s+(are\s+)?(there|available|exist)\b|\bshow\s+(me\s+)?the\s+schema\b",
    re.IGNORECASE
)
_META_DESCRIBE_TABLE_RE = re.compile(
    r"\bcolumns?\s+(of|in|for)\s+(the\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\b|"
    r"\bdescribe\s+(the\s+)?(table\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\b|"
    r"\bwhat\s+columns?\s+does\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+have\b|"
    r"\bstructure\s+of\s+(the\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\b",
    re.IGNORECASE
)


def _find_known_table(candidate: str) -> str | None:
    """Match a user-typed word against the real table names, case-insensitively,
    allowing loose singular/plural and underscore-vs-space variants."""
    if not candidate:
        return None
    cand = candidate.lower().strip()
    for t in _known_tables:
        if t.lower() == cand:
            return t
    norm = cand.replace(" ", "_")
    for t in _known_tables:
        tl = t.lower()
        if tl == norm or tl == norm + "s" or tl + "s" == norm or tl.rstrip("s") == norm.rstrip("s"):
            return t
    return None


def try_meta_query(question: str) -> dict | None:
    """
    Returns a fully-formed result dict (same shape as the normal pipeline's
    final output) if `question` is a schema/meta question we can answer
    straight from cache, else None (meaning: run the normal LLM pipeline).
    """
    q = question.strip()

    # NOTE: confidence must match calculate_confidence()'s real shape
    # (table_relevance / column_accuracy / attempt_score / row_sanity /
    # overall / level) — the frontend's render_meta() reads c.get('overall')
    # and c.get('table_relevance') etc, so a dict with different keys would
    # silently render as 0/100 everywhere.
    _DETERMINISTIC_CONFIDENCE = {
        "table_relevance": 100.0, "column_accuracy": 100.0,
        "attempt_score": 100.0, "row_sanity": 100.0,
        "overall": 100.0, "level": "high",
    }

    if _META_ALL_COLUMNS_RE.search(q):
        rows = [{"table_name": t, "column_count": len(_known_columns.get(t, []))} for t in sorted(_known_tables)]
        answer = (
            f"This database has **{len(_known_tables)} tables**. Here's each table with its column count "
            f"(open the SQL panel below for the exact introspection query, or ask about a specific table "
            f"to see its actual columns)."
        )
        return {
            "sql": "SELECT table_name, COUNT(*) AS column_count FROM information_schema.columns "
                   "WHERE table_schema='public' GROUP BY table_name ORDER BY table_name;",
            "rows": rows, "answer": answer, "chart_json": None,
            "model_used": "schema-cache (no LLM used)", "attempts": 1,
            "tables_used": [], "confidence": _DETERMINISTIC_CONFIDENCE,
            "sql_warnings": [], "intent": "META",
            "insights": [f"Tables: {len(_known_tables)}", f"Total columns across schema: {sum(len(c) for c in _known_columns.values())}"],
            "followups": ["List all tables", "What columns does customer have?"],
        }

    if _META_LIST_TABLES_RE.search(q):
        rows = [{"table_name": t} for t in sorted(_known_tables)]
        answer = f"This database has **{len(_known_tables)} tables**."
        return {
            "sql": "SELECT table_name FROM information_schema.tables "
                   "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name;",
            "rows": rows, "answer": answer, "chart_json": None,
            "model_used": "schema-cache (no LLM used)", "attempts": 1,
            "tables_used": [], "confidence": _DETERMINISTIC_CONFIDENCE,
            "sql_warnings": [], "intent": "META",
            "insights": [f"Tables: {len(_known_tables)}"],
            "followups": ["Show all columns of every table", "What columns does customer have?"],
        }

    m = _META_DESCRIBE_TABLE_RE.search(q)
    if m:
        stopwords = {"the", "table", "of", "in", "for", "column", "columns"}
        candidate = None
        for g in m.groups():
            if not g:
                continue
            gs = g.strip()
            if gs.lower() in stopwords:
                continue
            if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", gs):
                candidate = gs
                break
        table = _find_known_table(candidate) if candidate else None
        if table:
            cols = _known_columns.get(table, [])
            rows = [{"column_name": c} for c in cols]
            answer = f"The **{table}** table has **{len(cols)} columns**: {', '.join(cols)}."
            return {
                "sql": f"SELECT column_name FROM information_schema.columns "
                       f"WHERE table_schema='public' AND table_name='{table}' ORDER BY ordinal_position;",
                "rows": rows, "answer": answer, "chart_json": None,
                "model_used": "schema-cache (no LLM used)", "attempts": 1,
                "tables_used": [table], "confidence": _DETERMINISTIC_CONFIDENCE,
                "sql_warnings": [], "intent": "META",
                "insights": [f"Columns: {len(cols)}"],
                "followups": [f"Show me 5 rows from {table}", "List all tables"],
            }
        elif candidate:
            # They asked about a table-like name we don't recognize — say so
            # plainly instead of letting the LLM hallucinate a guess.
            close = [t for t in _known_tables if candidate.lower() in t.lower() or t.lower() in candidate.lower()]
            hint = f" Did you mean: {', '.join(sorted(close)[:5])}?" if close else ""
            return {
                "sql": "", "rows": [], "chart_json": None,
                "answer": f"I couldn't find a table called '{candidate}' in the schema.{hint}",
                "model_used": "schema-cache (no LLM used)", "attempts": 1,
                "tables_used": [], "confidence": {**_DETERMINISTIC_CONFIDENCE, "column_accuracy": 0.0, "overall": 60.0, "level": "medium"},
                "sql_warnings": [], "intent": "META",
                "insights": [], "followups": ["List all tables"],
            }

    return None


# ── Core pipeline ─────────────────────────────────────────────────────────────
async def generate_sql_with_retry(question: str, context: "ConversationContext | None" = None, org_id: str | None = None, all_orgs: bool = False) -> dict:
    """
    6-layer accuracy pipeline. Returns full result dict.
    """
    refresh_validator_cache()
    start_total = time.perf_counter()

    # ── L0: Meta/schema bypass — instant, deterministic, no LLM call ────────
    meta_result = try_meta_query(question)
    if meta_result is not None:
        meta_result["latency_ms"] = round((time.perf_counter() - start_total) * 1000, 1)
        return meta_result

    # ── L1: Query Intelligence ───────────────────────────────────────────────
    qctx = build_query_context(question, "", "")  # schema_text filled later

    # Complex questions (breakdowns, per-group rankings, trends, comparisons)
    # get more candidate tables and more room for CTE/window-function SQL.
    complex_q = is_complex_query(question)
    retrieval_top_k = int(os.getenv("RETRIEVAL_TOP_K", "8")) + (4 if complex_q else 0)
    gen_max_tokens = 1000 if complex_q else 700
    conv_context_block = build_conversation_context_block(context, question)

    # ── L2: Hybrid Retrieval ─────────────────────────────────────────────────
    if is_index_ready():
        retrieval = retrieve_tables(question, top_k=retrieval_top_k)
        tables_used       = retrieval["tables_used"]
        similarity_scores = retrieval["similarity_scores"]
        schema_text       = retrieval["schema_text"]
    else:
        # Fallback: full schema
        all_tables  = await mcp_host.list_tables()
        schema_text = await mcp_host.get_schema(all_tables)
        tables_used = all_tables
        similarity_scores = {}

    # Force anchor tables based on question keywords
    tables_used = force_anchor_tables(question, tables_used)

    # Follow-up questions ("filter that to critical only") often reuse the
    # previous turn's tables even when retrieval alone wouldn't surface them
    # (the follow-up text itself may not mention any table-like keywords).
    if context and is_followup_question(question) and context.tables_used:
        new_tables = [t for t in context.tables_used if t not in tables_used]
        if new_tables and is_index_ready():
            extra_schema = get_schema_for_tables(new_tables)
            if extra_schema:
                schema_text = schema_text + "\n" + extra_schema
                tables_used = tables_used + new_tables

    # ── L3: Schema Graph — compute join hints ────────────────────────────────
    join_hints = get_join_hints(tables_used)

    # ── L4: Context Assembly ─────────────────────────────────────────────────
    # Dynamic few-shot: retrieve similar past successful queries
    past_examples = get_similar_examples(question, top_k=3)

    # Column value sampling: actual DB values for filter columns
    value_hints = await build_value_hints(tables_used, mcp_host.run_query)

    # Rebuild query context now that we have schema and join hints
    qctx = build_query_context(question, schema_text, join_hints)

    # ── L5 + L6: Generation + Self-Correction loop ───────────────────────────
    failed_attempts: list[tuple[str, str]] = []
    model_used = "qwen"
    last_sql   = ""
    validation_errors: list[str] = []

    for attempt in range(1, MAX_ATTEMPTS + 1):

        # Build the full prompt
        retry_ctx = build_retry_context(failed_attempts)

        # all_orgs=True means an admin-key-verified cross-tenant request (see
        # _check_admin_key() in the route handler — this function never checks
        # the key itself, it trusts the caller already did). Otherwise, fall
        # back to normal single-org filtering, or no filtering if org_id
        # wasn't supplied at all.
        if all_orgs:
            org_hint = ("\nAUTHORIZED CROSS-ORGANIZATION QUERY: This request has been verified as an "
                        "administrative query. Do NOT filter by zecure_org_id — return data across all "
                        "organizations, unless the question itself asks to group or filter by organization.\n")
        elif org_id:
            org_hint = f"\nSECURITY RULE: ALWAYS filter by zecure_org_id = {org_id} on all tables that have this column.\n"
        else:
            org_hint = ""

        prompt = f"""{COT_SYSTEM_PROMPT}
{ADVANCED_SQL_HINTS if complex_q else ""}
{org_hint}
{conv_context_block}

{past_examples}

Relevant Schema ({len(tables_used)} tables selected):
{schema_text}

{join_hints}

{qctx['filter_hints']}
{value_hints}

Intent detected: {qctx['intent']} — {qctx['intent_hint']}

{qctx['skeleton']}

{retry_ctx}

Question: {question}
"""

        # If the last two attempts failed with the SAME CLASS of error, a
        # 3rd try on the same small local model is unlikely to help —
        # escalate straight to the bigger fallback model instead of wasting
        # another round-trip repeating the mistake.
        skip_tiers = None
        if len(failed_attempts) >= 2:
            if _error_signature(failed_attempts[-1][1]) == _error_signature(failed_attempts[-2][1]):
                skip_tiers = {"qwen"}

        # Try customer's own LLM key first (if configured)
        # NOTE: bumped from 500 -> 700 (1000 for complex questions). The
        # <think> step-by-step reasoning block eats a big chunk of the token
        # budget on its own, and at 500 it was frequently cutting the SQL
        # block off mid-query — a real contributor to both the retries
        # (slowness) and the wrong-answer rate (accuracy) reported after
        # this was added.
        customer_result = await call_customer_llm(prompt, max_tokens=gen_max_tokens)
        if customer_result:
            raw, model_used = customer_result
        else:
            try:
                raw, model_used = await model_router.generate(prompt, max_tokens=gen_max_tokens, skip_tiers=skip_tiers)
            except RuntimeError as e:
                raise ValueError(f"All models failed: {e}")

        # Strip <think> block before extracting SQL
        raw_no_think = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        sql = extract_sql(raw_no_think)
        last_sql = sql

        # SELECT guard (CTEs legitimately start with WITH, not SELECT)
        if not re.match(r"^\s*(SELECT|WITH)\b", sql, re.IGNORECASE):
            err = f"Non-SELECT SQL returned: {sql[:100]}"
            failed_attempts.append((sql, err))
            continue

        # Schema validation
        validation_errors = validate_sql(sql, _known_tables, _known_columns)
        if validation_errors:
            err = "Schema errors:\n" + "\n".join(f"  - {e}" for e in validation_errors)
            failed_attempts.append((sql, err))
            continue

        # SQL quality warnings (logged, don't block)
        warnings = check_sql_quality(sql)

        # Execute
        try:
            rows = await mcp_host.run_query(sql)
        except Exception as e:
            error_str = str(e)
            # Try a deterministic, LLM-free fix first for well-known
            # mechanical errors (e.g. SELECT DISTINCT + ORDER BY mismatch) —
            # faster and more reliable than hoping the model corrects itself
            # from error text, especially for a small local model.
            repaired_sql = try_auto_repair(sql, error_str)
            if repaired_sql:
                repair_errors = validate_sql(repaired_sql, _known_tables, _known_columns)
                if not repair_errors:
                    try:
                        rows = await mcp_host.run_query(repaired_sql)
                        sql = repaired_sql  # repair succeeded — use the patched query
                    except Exception as e2:
                        failed_attempts.append((sql, f"Execution error: {error_str}"))
                        continue
                else:
                    failed_attempts.append((sql, f"Execution error: {error_str}"))
                    continue
            else:
                failed_attempts.append((sql, f"Execution error: {error_str}"))
                continue

        # ── Zero-row diagnosis ───────────────────────────────────────────────
        if len(rows) == 0 and attempt < MAX_ATTEMPTS:
            fixed_sql = await diagnose_zero_rows(sql, model_router.generate)
            if fixed_sql and fixed_sql != sql:
                try:
                    fixed_rows = await mcp_host.run_query(fixed_sql)
                    if len(fixed_rows) > 0:
                        sql  = fixed_sql
                        rows = fixed_rows

                except Exception:
                    pass  # Keep original sql/rows

        # ── Richer, data-grounded answer + interactive follow-ups ────────────
        quick_stats = compute_quick_stats(rows)
        answer = await generate_answer(question, rows, model_router.generate, quick_stats=quick_stats)
        followups = generate_followups(question, rows, sql, qctx["intent"])

        # ── Store successful example for future retrieval ─────────────────────
        store_successful_example(question, sql, len(rows))

        # ── Confidence scoring ───────────────────────────────────────────────
        confidence = calculate_confidence(
            similarity_scores=similarity_scores,
            tables_used=tables_used,
            validation_errors=validation_errors,
            attempt_number=attempt,
            row_count=len(rows),
        )

        return {
            "sql":               sql,
            "rows":              rows,
            "answer":            answer,
            "model_used":        model_used,
            "attempts":          attempt,
            "tables_used":       tables_used,
            "confidence":        confidence,
            "sql_warnings":      warnings,
            "intent":            qctx["intent"],
            "insights":          quick_stats,
            "followups":         followups,
        }

    # All attempts exhausted
    raise ValueError(
        f"Could not generate working SQL after {MAX_ATTEMPTS} attempts.\n"
        f"Last SQL tried:\n{last_sql}\n"
        f"Last error: {failed_attempts[-1][1] if failed_attempts else 'unknown'}"
    )


# ── Streaming pipeline (powers /chat/stream — live progress + model thinking) ─
async def generate_sql_streaming(question: str, context: "ConversationContext | None" = None, org_id: str | None = None, all_orgs: bool = False):
    """
    Same 6-layer pipeline as generate_sql_with_retry, but implemented as an
    async generator that yields JSON-able event dicts as it goes:

      {"type": "status",  "stage": ..., "message": ...}   — progress updates
      {"type": "thinking_token", "text": ..., "model": ...} — live model tokens
      {"type": "final", "data": {...same shape as ChatResponse...}}
      {"type": "error", "message": ...}

    This is what lets the UI show what the model is actually generating
    (the <think> reasoning + SQL) as it's produced, instead of one static
    "generating…" message for the whole 3-5 minutes.
    """
    start_total = time.perf_counter()
    refresh_validator_cache()

    # ── L0: Meta/schema bypass — instant, deterministic, no LLM call ────────
    meta_result = try_meta_query(question)
    if meta_result is not None:
        yield {"type": "status", "stage": "meta", "message": "📚 Answering directly from schema cache (no model needed)..."}
        chart_json, chart_kind, single_stat = build_chart(meta_result["rows"], title=question, question=question)
        meta_result["chart_json"], meta_result["chart_kind"], meta_result["single_stat"] = chart_json, chart_kind, single_stat
        meta_result["latency_ms"] = round((time.perf_counter() - start_total) * 1000, 1)
        yield {"type": "final", "data": meta_result}
        return

    yield {"type": "status", "stage": "retrieval",
           "message": "🔍 Retrieving relevant tables (semantic + keyword search)..."}

    qctx = build_query_context(question, "", "")
    complex_q = is_complex_query(question)
    retrieval_top_k = int(os.getenv("RETRIEVAL_TOP_K", "8")) + (4 if complex_q else 0)
    gen_max_tokens = 1000 if complex_q else 700
    conv_context_block = build_conversation_context_block(context, question)

    if is_index_ready():
        retrieval = retrieve_tables(question, top_k=retrieval_top_k)
        tables_used       = retrieval["tables_used"]
        similarity_scores = retrieval["similarity_scores"]
        schema_text       = retrieval["schema_text"]
    else:
        all_tables  = await mcp_host.list_tables()
        schema_text = await mcp_host.get_schema(all_tables)
        tables_used = all_tables
        similarity_scores = {}

    tables_used = force_anchor_tables(question, tables_used)

    if context and is_followup_question(question) and context.tables_used:
        new_tables = [t for t in context.tables_used if t not in tables_used]
        if new_tables and is_index_ready():
            extra_schema = get_schema_for_tables(new_tables)
            if extra_schema:
                schema_text = schema_text + "\n" + extra_schema
                tables_used = tables_used + new_tables
    preview = ", ".join(tables_used[:8]) + ("…" if len(tables_used) > 8 else "")
    yield {"type": "status", "stage": "tables",
           "message": f"📋 Selected {len(tables_used)} relevant tables: {preview}"}

    join_hints = get_join_hints(tables_used)

    yield {"type": "status", "stage": "context",
           "message": "🔗 Computing join paths and sampling real column values..."}

    past_examples = get_similar_examples(question, top_k=3)
    value_hints = await build_value_hints(tables_used, mcp_host.run_query)
    qctx = build_query_context(question, schema_text, join_hints)

    failed_attempts: list[tuple[str, str]] = []
    model_used = "qwen"
    last_sql   = ""
    validation_errors: list[str] = []

    for attempt in range(1, MAX_ATTEMPTS + 1):
        retry_ctx = build_retry_context(failed_attempts)

        # all_orgs=True means an admin-key-verified cross-tenant request (see
        # _check_admin_key() in the route handler — this function never checks
        # the key itself, it trusts the caller already did). Otherwise, fall
        # back to normal single-org filtering, or no filtering if org_id
        # wasn't supplied at all.
        if all_orgs:
            org_hint = ("\nAUTHORIZED CROSS-ORGANIZATION QUERY: This request has been verified as an "
                        "administrative query. Do NOT filter by zecure_org_id — return data across all "
                        "organizations, unless the question itself asks to group or filter by organization.\n")
        elif org_id:
            org_hint = f"\nSECURITY RULE: ALWAYS filter by zecure_org_id = {org_id} on all tables that have this column.\n"
        else:
            org_hint = ""

        prompt = f"""{COT_SYSTEM_PROMPT}
{ADVANCED_SQL_HINTS if complex_q else ""}
{org_hint}
{conv_context_block}

{past_examples}

Relevant Schema ({len(tables_used)} tables selected):
{schema_text}

{join_hints}

{qctx['filter_hints']}
{value_hints}

Intent detected: {qctx['intent']} — {qctx['intent_hint']}

{qctx['skeleton']}

{retry_ctx}

Question: {question}
"""

        # If the last two attempts failed with the SAME CLASS of error,
        # escalate straight to the bigger fallback model instead of another
        # local attempt that's likely to repeat the same mistake.
        skip_tiers = None
        if len(failed_attempts) >= 2:
            if _error_signature(failed_attempts[-1][1]) == _error_signature(failed_attempts[-2][1]):
                skip_tiers = {"qwen"}
                yield {"type": "status", "stage": "escalate",
                       "message": "🔺 Same error twice — escalating to a stronger fallback model..."}

        yield {"type": "status", "stage": "generating",
               "message": f"🧠 Generating SQL — attempt {attempt}/{MAX_ATTEMPTS}..."}

        raw = ""
        customer_result = await call_customer_llm(prompt, max_tokens=gen_max_tokens)
        if customer_result:
            raw, model_used = customer_result
            yield {"type": "thinking_token", "text": raw, "model": model_used}
        else:
            try:
                async for chunk in model_router.generate_stream(prompt, max_tokens=gen_max_tokens, skip_tiers=skip_tiers):
                    if "token" in chunk:
                        raw += chunk["token"]
                        yield {"type": "thinking_token", "text": chunk["token"], "model": chunk.get("model", "qwen")}
                    elif chunk.get("model_failed"):
                        yield {"type": "status", "stage": "fallback",
                               "message": f"⚠️ {chunk['model_failed']} unavailable, switching model..."}
                    elif chunk.get("done"):
                        raw = chunk["full_text"]
                        model_used = chunk["model"]
            except RuntimeError as e:
                yield {"type": "error", "message": f"All models failed: {e}"}
                return

        raw_no_think = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        sql = extract_sql(raw_no_think)
        last_sql = sql

        if not re.match(r"^\s*(SELECT|WITH)\b", sql, re.IGNORECASE):
            err = f"Non-SELECT SQL returned: {sql[:100]}"
            failed_attempts.append((sql, err))
            yield {"type": "status", "stage": "retry",
                   "message": f"⚠️ Attempt {attempt} didn't produce valid SQL — retrying..."}
            continue

        validation_errors = validate_sql(sql, _known_tables, _known_columns)
        if validation_errors:
            failed_attempts.append((sql, "Schema errors:\n" + "\n".join(f"  - {e}" for e in validation_errors)))
            yield {"type": "status", "stage": "retry",
                   "message": f"⚠️ Attempt {attempt} had a schema error ({validation_errors[0][:80]}) — retrying..."}
            continue

        warnings = check_sql_quality(sql)

        yield {"type": "status", "stage": "executing", "message": "▶️ Running the query..."}
        try:
            rows = await mcp_host.run_query(sql)
        except Exception as e:
            error_str = str(e)
            repaired_sql = try_auto_repair(sql, error_str)
            repaired_ok = False
            if repaired_sql and not validate_sql(repaired_sql, _known_tables, _known_columns):
                try:
                    rows = await mcp_host.run_query(repaired_sql)
                    sql = repaired_sql
                    repaired_ok = True
                    yield {"type": "status", "stage": "auto_repair",
                           "message": "🔧 Auto-fixed a mechanical SQL error (no model call needed)..."}
                except Exception:
                    pass
            if not repaired_ok:
                failed_attempts.append((sql, f"Execution error: {error_str}"))
                yield {"type": "status", "stage": "retry",
                       "message": f"⚠️ Attempt {attempt} failed to execute — retrying..."}
                continue

        if len(rows) == 0 and attempt < MAX_ATTEMPTS:
            yield {"type": "status", "stage": "diagnosis",
                   "message": "🔎 Zero rows returned — diagnosing and trying a fix..."}
            fixed_sql = await diagnose_zero_rows(sql, model_router.generate)
            if fixed_sql and fixed_sql != sql:
                try:
                    fixed_rows = await mcp_host.run_query(fixed_sql)
                    if len(fixed_rows) > 0:
                        sql, rows = fixed_sql, fixed_rows
                except Exception:
                    pass

        yield {"type": "status", "stage": "answer", "message": "✍️ Writing the answer..."}
        quick_stats = compute_quick_stats(rows)
        answer = await generate_answer(question, rows, model_router.generate, quick_stats=quick_stats)
        followups = generate_followups(question, rows, sql, qctx["intent"])
        store_successful_example(question, sql, len(rows))

        confidence = calculate_confidence(
            similarity_scores=similarity_scores,
            tables_used=tables_used,
            validation_errors=validation_errors,
            attempt_number=attempt,
            row_count=len(rows),
        )

        # Smart auto-chart: picks type by result shape (line/area/bar/donut/
        # grouped-bar/single-stat) instead of the old "only 2 columns" rule.
        chart_json, chart_kind, single_stat = build_chart(rows, title=question, question=question)

        latency_ms = round((time.perf_counter() - start_total) * 1000, 1)

        yield {"type": "final", "data": {
            "sql":          sql,
            "rows":         rows,
            "answer":       answer,
            "chart_json":   chart_json,
            "chart_kind":   chart_kind,
            "single_stat":  single_stat,
            "model_used":   model_used,
            "attempts":     attempt,
            "tables_used":  tables_used,
            "confidence":   confidence,
            "sql_warnings": warnings,
            "intent":       qctx["intent"],
            "latency_ms":   latency_ms,
            "insights":     quick_stats,
            "followups":    followups,
        }}
        return

    yield {"type": "error",
           "message": f"Could not generate working SQL after {MAX_ATTEMPTS} attempts. "
                      f"Last error: {failed_attempts[-1][1] if failed_attempts else 'unknown'}"}


# ── Pydantic models ───────────────────────────────────────────────────────────
class LLMKeyRequest(BaseModel):
    provider: str
    api_key: str
    model: str
    customer_id: str = "default"

class LLMKeyToggle(BaseModel):
    provider: str
    enabled: bool
    customer_id: str = "default"

class ConversationContext(BaseModel):
    question: str
    sql: str
    tables_used: list[str] = []

class ChatRequest(BaseModel):
    question: str
    context: Optional[ConversationContext] = None
    org_id: Optional[str] = None
    # Requires a valid X-Admin-Key header on the request to actually take
    # effect (checked in the route handler, not here) — this is NOT a
    # per-user permission, it's a shared admin secret. See main.py's
    # _check_admin_key() and the security note in DEPLOYMENT.md.
    all_orgs: bool = False

class ChatResponse(BaseModel):
    sql: str
    rows: list[dict]
    answer: str
    chart_json: Optional[str] = None
    chart_kind: Optional[str] = None
    single_stat: Optional[dict] = None
    confidence: dict
    model_used: str
    cached: bool = False
    attempts: int
    latency_ms: float
    tables_used: list[str]
    intent: Optional[str] = None
    sql_warnings: list[str] = []
    insights: list[str] = []
    followups: list[str] = []

class ReportRequest(BaseModel):
    question: str
    sql: str
    rows: list[dict]
    chart_json: Optional[str] = None


# ── Routes ────────────────────────────────────────────────────────────────────
# ── LLM Key Management Routes ─────────────────────────────────────────────────

@app.get("/settings/providers")
def list_providers(user: AuthenticatedUser = Depends(get_current_user)):
    """List all supported LLM providers and their available models."""
    return {"providers": SUPPORTED_PROVIDERS}

@app.get("/settings/keys")
def list_keys(customer_id: str = "default", user: AuthenticatedUser = Depends(get_current_user)):
    """List all configured API keys for a customer (keys are masked)."""
    return {"keys": get_all_keys(customer_id)}

@app.post("/settings/keys")
async def add_key(req: LLMKeyRequest, user: AuthenticatedUser = Depends(get_current_user)):
    """Validate and save an API key for a provider."""
    validation = await validate_key(req.provider, req.api_key, req.model)
    if not validation["valid"]:
        raise HTTPException(400, f"Key validation failed: {validation.get('error', 'Unknown error')}")
    result = save_key(req.provider, req.api_key, req.model, req.customer_id)
    return result

@app.delete("/settings/keys/{provider}")
def remove_key(provider: str, customer_id: str = "default", user: AuthenticatedUser = Depends(get_current_user)):
    """Remove a saved API key."""
    return delete_key(provider, customer_id)

@app.patch("/settings/keys/toggle")
def toggle_provider(req: LLMKeyToggle, user: AuthenticatedUser = Depends(get_current_user)):
    """Enable or disable a provider without deleting the key."""
    return toggle_key(req.provider, req.enabled, req.customer_id)

@app.post("/settings/keys/validate")
async def check_key(req: LLMKeyRequest, user: AuthenticatedUser = Depends(get_current_user)):
    """Test an API key without saving it."""
    return await validate_key(req.provider, req.api_key, req.model)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "circuit_breaker": model_router.status(),
        "embedding_index_ready": is_index_ready(),
    }


@app.get("/schema")
def schema(user: AuthenticatedUser = Depends(get_current_user)):
    refresh_validator_cache()
    tables = sorted(list(_known_tables))
    lines  = [f"Table {t} ({', '.join(_known_columns.get(t, []))})" for t in tables]
    return {"schema": "\n".join(lines), "tables": tables, "table_count": len(tables)}


@app.get("/circuit-status")
def circuit_status():
    return model_router.status()


@app.post("/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
async def chat(request: Request, req: ChatRequest, x_admin_key: Optional[str] = Header(None), user: AuthenticatedUser = Depends(get_current_user)):
    start = time.perf_counter()
    if req.all_orgs:
        # Fail closed: an all_orgs request with a missing/wrong key is
        # rejected outright, never silently downgraded to "just your org"
        # or, worse, "no filter at all."
        _check_admin_key(x_admin_key)
    try:
        result = await generate_sql_with_retry(req.question, context=req.context, org_id=req.org_id, all_orgs=req.all_orgs)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Smart auto-chart: picks type by result shape instead of the old
    # "only 2 columns" rule.
    rows = result["rows"]
    chart_json, chart_kind, single_stat = build_chart(rows, title=req.question, question=req.question)

    latency_ms = round((time.perf_counter() - start) * 1000, 1)
    return ChatResponse(
        sql=result["sql"],
        rows=rows,
        answer=result["answer"],
        chart_json=chart_json,
        chart_kind=chart_kind,
        single_stat=single_stat,
        confidence=result["confidence"],
        model_used=result["model_used"],
        cached=False,
        attempts=result["attempts"],
        latency_ms=latency_ms,
        tables_used=result["tables_used"],
        intent=result.get("intent"),
        sql_warnings=result.get("sql_warnings", []),
        insights=result.get("insights", []),
        followups=result.get("followups", []),
    )


@app.post("/chat/stream")
@limiter.limit("10/minute")
async def chat_stream(request: Request, req: ChatRequest, x_admin_key: Optional[str] = Header(None), user: AuthenticatedUser = Depends(get_current_user)):
    """
    Server-Sent Events version of /chat. Streams progress updates and the
    model's live reasoning/SQL tokens as they're generated, then a final
    event with the same payload shape as ChatResponse.
    """
    if req.all_orgs:
        # Checked here, BEFORE the stream starts, so a bad key gets a clean
        # 401 response instead of an error buried inside an SSE stream.
        _check_admin_key(x_admin_key)

    async def event_gen():
        try:
            async for event in generate_sql_streaming(req.question, context=req.context, org_id=req.org_id, all_orgs=req.all_orgs):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/report/pdf")
@limiter.limit("10/minute")
async def generate_pdf(request: Request, req: ReportRequest, user: AuthenticatedUser = Depends(get_current_user)):
    try:
        pdf_path = await mcp_host.generate_pdf(req.question, req.sql, req.rows)
    except Exception as e:
        raise HTTPException(500, f"PDF failed: {e}")
    return FileResponse(pdf_path, media_type="application/pdf", filename="report.pdf")


# ── Feedback logging (👍/👎) ───────────────────────────────────────────────────
class FeedbackRequest(BaseModel):
    question: str
    sql: str
    rating: str  # "up" | "down"
    model_used: Optional[str] = None
    confidence: Optional[dict] = None

FEEDBACK_LOG_PATH = os.getenv("FEEDBACK_LOG_PATH", "./feedback_log.jsonl")

@app.post("/feedback")
@limiter.limit("30/minute")
async def submit_feedback(request: Request, req: FeedbackRequest, user: AuthenticatedUser = Depends(get_current_user)):
    """
    Append-only feedback log (JSONL). Cheap to add, gives real signal on
    where accuracy is actually failing instead of guessing from complaints.
    """
    if req.rating not in ("up", "down"):
        raise HTTPException(400, "rating must be 'up' or 'down'")
    entry = {
        "timestamp": time.time(),
        "question": req.question,
        "sql": req.sql,
        "rating": req.rating,
        "model_used": req.model_used,
        "confidence": req.confidence,
    }
    try:
        with open(FEEDBACK_LOG_PATH, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as e:
        raise HTTPException(500, f"Failed to log feedback: {e}")
    return {"status": "ok"}


# ── Editable / re-runnable SQL ────────────────────────────────────────────────
class RunSqlRequest(BaseModel):
    sql: str
    question: str = ""  # used for chart title + insights context, optional

@app.post("/run-sql")
@limiter.limit("15/minute")
async def run_sql(request: Request, req: RunSqlRequest, user: AuthenticatedUser = Depends(get_current_user)):
    """
    Lets the user edit the generated SQL in the UI and re-run it directly.
    Goes through the SAME validate_sql() security guards as the normal
    pipeline (SELECT/WITH only, no write/DDL keywords, no chained
    statements) — editing the SQL doesn't bypass any of that.
    """
    refresh_validator_cache()
    sql = req.sql.strip()

    errors = validate_sql(sql, _known_tables, _known_columns)
    if errors:
        raise HTTPException(400, "SQL rejected: " + "; ".join(errors))

    try:
        rows = await mcp_host.run_query(sql)
    except Exception as e:
        raise HTTPException(400, f"Execution error: {e}")

    quick_stats = compute_quick_stats(rows)
    chart_json, chart_kind, single_stat = build_chart(rows, title=req.question or "Query result", question=req.question)

    return {
        "sql": sql,
        "rows": rows,
        "insights": quick_stats,
        "chart_json": chart_json,
        "chart_kind": chart_kind,
        "single_stat": single_stat,
        "row_count": len(rows),
    }


@app.get("/schema/tables")
def schema_tables(user: AuthenticatedUser = Depends(get_current_user)):
    """Returns structured table list with columns for the schema explorer."""
    refresh_validator_cache()
    try:
        tables_info = []
        for table in sorted(_known_tables):
            columns = []
            if table in _known_columns:
                columns = [{"name": c, "type": ""} for c in _known_columns[table]]
            desc = TABLE_DESCRIPTIONS.get(table, "")
            tables_info.append({"name": table, "columns": columns, "description": desc})
        return {"tables": tables_info, "table_count": len(tables_info)}
    except Exception as e:
        return {"tables": [], "error": str(e)}


# ── Admin: incremental re-indexing ────────────────────────────────────────────
# For a cloud DB whose schema changes on its own schedule, the embedding
# index can't rely on someone remembering to run build_index.py by hand.
# This lets a CI/CD deploy step, a cron job, or a DB-change webhook trigger a
# re-sync over HTTP instead. Incremental by default — only re-embeds tables
# whose columns/comments/foreign keys actually changed (see
# embeddings/schema_introspect.py), so this is cheap enough to call
# frequently rather than needing careful scheduling.

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")  # unset = admin endpoints disabled
_reindex_status = {"running": False, "last_result": None, "last_error": None, "last_run_at": None}


def _check_admin_key(x_admin_key: Optional[str]):
    if not ADMIN_API_KEY:
        raise HTTPException(503, "Admin endpoints are disabled — set ADMIN_API_KEY to enable /admin/reindex.")
    if x_admin_key != ADMIN_API_KEY:
        raise HTTPException(401, "Invalid or missing X-Admin-Key header.")


def _run_reindex(full: bool):
    from embeddings.build_index import build_index
    _reindex_status["running"] = True
    try:
        summary = build_index(incremental=not full)
        _reindex_status["last_result"] = summary
        _reindex_status["last_error"] = None
    except Exception as e:
        _reindex_status["last_error"] = str(e)
    finally:
        _reindex_status["running"] = False
        _reindex_status["last_run_at"] = time.time()


@app.post("/admin/reindex")
async def admin_reindex(
    background_tasks: BackgroundTasks,
    full: bool = False,
    x_admin_key: Optional[str] = Header(None),
):
    """
    Triggers an embedding index sync. Runs in the background (this returns
    immediately) — poll GET /admin/reindex/status for progress/result.
    full=true forces a complete rebuild instead of the incremental default;
    only use this if you suspect the index itself is corrupted, since it
    re-embeds every table regardless of whether it changed.
    """
    _check_admin_key(x_admin_key)
    if _reindex_status["running"]:
        raise HTTPException(409, "A re-index is already running — check /admin/reindex/status.")
    background_tasks.add_task(_run_reindex, full)
    return {"status": "started", "mode": "full" if full else "incremental"}


@app.get("/admin/reindex/status")
def admin_reindex_status(x_admin_key: Optional[str] = Header(None)):
    _check_admin_key(x_admin_key)
    return _reindex_status
