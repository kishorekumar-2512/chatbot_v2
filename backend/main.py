"""
backend/main.py — Single-server Text-to-SQL API with Multi-Turn Context & Org Isolation.

Pipeline:
  L1: Query Intelligence  — intent + entity extraction + SQL skeleton
  L2: Hybrid Retrieval    — BM25 + ChromaDB + anchor table injection  
  L3: Schema Graph        — FK-aware join path injection
  L4: Context Assembly    — column value sampling + dynamic few-shot examples + multi-turn context
  L5: SQL Generation      — chain-of-thought prompt + circuit breaker LLMs
  L6: Self Correction     — retry with diff context + sanity check
"""
import os, re
os.environ["USE_TF"] = "0"
os.environ["USE_TORCH"] = "1"
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException, Request, Depends
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from backend.sql_validator import extract_sql, validate_sql, validate_org_security
from backend.schema_graph import get_join_hints, force_anchor_tables, expand_related_tables, SCHEMA_GRAPH, ANCHOR_TABLES
from backend.query_intelligence import build_query_context, extract_entities
from backend.prompts import get_system_prompt

# ChromaDB/embeddings may not be available on Windows (needs C++ build tools).
# Gracefully degrade: the backend works without semantic retrieval (falls back to full schema).
try:
    from backend.hybrid_retriever import (
        retrieve_tables, get_similar_examples,
        store_successful_example, get_schema_for_tables,
    )
    from embeddings.retrieve import is_index_ready
    _HAS_EMBEDDINGS = True
except ImportError:
    _HAS_EMBEDDINGS = False
    def is_index_ready(): return False
    def retrieve_tables(*a, **kw): return {"tables_used": [], "similarity_scores": {}, "schema_text": ""}
    def get_similar_examples(*a, **kw): return ""
    def store_successful_example(*a, **kw): pass
    def get_schema_for_tables(*a, **kw): return ""

from backend.llm_orchestrator import AllProvidersFailed, orchestrator as llm_orchestrator
from backend.llm_config import system_llm_status, format_all_models_failed_error
from backend.self_correction import build_retry_context, check_sql_quality
from backend.auth import get_current_user, AuthenticatedUser, REQUIRE_AUTH

MAX_ATTEMPTS    = 3


async def _generate_llm(
    prompt: str,
    tenant_id: str | None,
    max_tokens: int = 400,
    excluded_providers: set[str] | None = None,
) -> tuple[str, str, str]:
    return await llm_orchestrator.generate(
        prompt,
        tenant_id=tenant_id,
        max_tokens=max_tokens,
        excluded_providers=excluded_providers,
    )

# ── Schema validator cache (derived from schema graph, no DB connection) ──────
def _get_all_known_tables() -> set:
    tables = set(SCHEMA_GRAPH.keys())
    for parents in SCHEMA_GRAPH.values():
        tables.update(parents.keys())
    tables.update(ANCHOR_TABLES.keys())
    return tables

_known_tables: set = _get_all_known_tables()
_known_columns: dict = {}


def refresh_validator_cache():
    global _known_tables
    if not _known_tables or "managed_device" not in _known_tables:
        _known_tables = _get_all_known_tables()


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    refresh_validator_cache()
    yield


# ── App + security ────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="AI Database Report Chatbot — Max Accuracy", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── SQL hints & complexity heuristics ─────────────────────────────────────────
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


# ── Pydantic models ───────────────────────────────────────────────────────────
class ConversationContext(BaseModel):
    question: str
    sql: str
    tables_used: list[str] = []


class ChatRequest(BaseModel):
    question: str
    context: Optional[ConversationContext] = None
    org_id: Optional[str] = None
    image_base64: Optional[str] = None


class ChatResponse(BaseModel):
    sql: str
    model_used: str
    attempts: int


def build_conversation_context_block(context: Optional[ConversationContext], question: str) -> str:
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


# ── Prompt size guard ─────────────────────────────────────────────────────────
_MAX_PROMPT_TOKENS = int(os.getenv("MAX_PROMPT_TOKENS", "3000"))


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English + SQL."""
    return len(text) // 4


def _trim_prompt_to_budget(prompt: str, schema_text: str, tables_used: list[str],
                           max_tokens: int, budget: int = _MAX_PROMPT_TOKENS) -> tuple[str, str, list[str]]:
    """
    If the prompt + max_tokens exceeds `budget`, progressively remove the
    last (least relevant) table DDLs from schema_text until it fits.
    Returns (trimmed_prompt, trimmed_schema, trimmed_tables).
    """
    total = _estimate_tokens(prompt) + max_tokens
    if total <= budget:
        return prompt, schema_text, tables_used

    ddl_blocks = [b.strip() for b in re.split(
        r"\n\s*(?=(?:CREATE\s+TABLE|Table\s+[^\s(]+\s*\(|--\s*(?:Table|table)\s*[:(]))",
        schema_text.strip(),
    ) if b.strip()]

    if len(ddl_blocks) <= 1:
        lines = schema_text.strip().split("\n")
        while len(lines) > 20 and _estimate_tokens(prompt) + max_tokens > budget:
            lines = lines[:-10]
            new_schema = "\n".join(lines)
            prompt = prompt.replace(schema_text, new_schema)
            schema_text = new_schema
        return prompt, schema_text, tables_used

    while ddl_blocks and _estimate_tokens(prompt) + max_tokens > budget:
        removed_block = ddl_blocks.pop()
        m = re.search(r"(?:CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?|Table\s+|--\s*Table\s*:\s*)([a-zA-Z0-9_]+)", removed_block, re.IGNORECASE)
        if m:
            removed_name = m.group(1).lower()
            tables_used = [t for t in tables_used if t.lower() != removed_name]

    trimmed_schema = "\n\n".join(ddl_blocks)
    prompt = prompt.replace(schema_text, trimmed_schema)
    prompt = re.sub(r"Relevant Schema \(\d+ tables selected\):",
                    f"Relevant Schema ({len(ddl_blocks)} tables selected):", prompt)
    return prompt, trimmed_schema, tables_used


# ── Core pipeline ─────────────────────────────────────────────────────────────
async def generate_sql_with_retry(
    question: str,
    context: Optional[ConversationContext] = None,
    org_id: str | None = None,
) -> dict:
    """
    Pure Text-to-SQL generation pipeline with multi-turn context support and strict org_id isolation.
    """
    refresh_validator_cache()

    # ── L1: Query Intelligence ───────────────────────────────────────────────
    qctx = build_query_context(question, "", "")  # schema_text filled later

    complex_q = is_complex_query(question)
    retrieval_top_k = int(os.getenv("RETRIEVAL_TOP_K", "8")) + (4 if complex_q else 0)
    gen_max_tokens = 1000 if complex_q else 700
    conv_context_block = build_conversation_context_block(context, question)

    # ── L2: Hybrid Retrieval ─────────────────────────────────────────────────
    retrieved_tables: list[str] = []
    index_ready = is_index_ready()
    if index_ready:
        retrieval = retrieve_tables(question, top_k=retrieval_top_k)
        tables_used       = retrieval["tables_used"]
        retrieved_tables  = list(tables_used)
        similarity_scores = retrieval["similarity_scores"]
        schema_text       = retrieval["schema_text"]
    else:
        all_tables = list(_known_tables)
        entity_tables = [
            table for table in extract_entities(question)["tables"]
            if table in all_tables
        ]
        tables_used = force_anchor_tables(question, entity_tables)
        tables_used = [table for table in tables_used if table in all_tables]
        tables_used = expand_related_tables(tables_used, max_tables=retrieval_top_k)
        if not tables_used:
            tables_used = all_tables[:min(3, len(all_tables))]
        schema_text = ""
        similarity_scores = {}

    # Force anchor tables based on question keywords
    tables_used = force_anchor_tables(question, tables_used)
    if complex_q:
        tables_used = expand_related_tables(tables_used, max_tables=retrieval_top_k)

    if index_ready:
        added_tables = [table for table in tables_used if table not in retrieved_tables]
        if added_tables:
            extra_schema = get_schema_for_tables(added_tables)
            if extra_schema:
                schema_text = schema_text + "\n" + extra_schema

    # Follow-up questions ("filter that to critical only") often reuse the
    # previous turn's tables even when retrieval alone wouldn't surface them
    # (the follow-up text itself may not mention any table-like keywords).
    if context and is_followup_question(question) and context.tables_used:
        new_tables = [t for t in context.tables_used if t not in tables_used]
        if new_tables and index_ready:
            extra_schema = get_schema_for_tables(new_tables)
            if extra_schema:
                schema_text = schema_text + "\n" + extra_schema
                tables_used = tables_used + new_tables
        elif new_tables and not index_ready:
            tables_used = tables_used + [t for t in new_tables if t in _known_tables]

    # ── L3: Schema Graph — compute join hints ────────────────────────────────
    join_hints = get_join_hints(tables_used)

    # ── L4: Context Assembly ─────────────────────────────────────────────────
    past_examples = get_similar_examples(question, top_k=3)
    value_hints = ""
    qctx = build_query_context(question, schema_text, join_hints)

    # ── L5 + L6: Generation + Self-Correction loop ───────────────────────────
    failed_attempts: list[tuple[str, str]] = []
    # A provider that returned SQL which fails validation has completed its API
    # call successfully, so the normal provider-error fallback cannot see the
    # failure. Exclude it on the next correction attempt to progress through
    # Groq -> Gemini -> Ollama rather than repeatedly asking the same model.
    rejected_providers: set[str] = set()
    model_used = "qwen"
    last_sql   = ""

    async def generate_for_request(prompt: str, max_tokens: int = 400) -> tuple[str, str, str]:
        return await _generate_llm(
            prompt,
            org_id,
            max_tokens,
            excluded_providers=rejected_providers,
        )

    for attempt in range(1, MAX_ATTEMPTS + 1):
        retry_ctx = build_retry_context(failed_attempts)

        if org_id:
            org_hint = f"""
MANDATORY REQUIREMENT:
The user specified org_id = {org_id}.
EVERY SQL query generated MUST strictly include `zecure_org_id = {org_id}` in the WHERE clause (e.g., `WHERE alias.zecure_org_id = {org_id}` or `AND zecure_org_id = {org_id}`).
For questions about tables or database schema (such as "how many tables are there"), write:
```sql
SELECT COUNT(DISTINCT table_name) AS total_table_count
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
  AND zecure_org_id = {org_id};
```
Always output pure SQL inside ```sql ... ``` code blocks. Do not output conversational explanations or excuses.
"""
        else:
            org_hint = ""

        system_prompt = get_system_prompt()
        prompt = f"""{system_prompt}
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

        # Trim prompt to fit within token budget
        prompt, schema_text, tables_used = _trim_prompt_to_budget(
            prompt, schema_text, tables_used, gen_max_tokens)

        try:
            raw, model_used, provider_used = await generate_for_request(prompt, max_tokens=gen_max_tokens)
        except AllProvidersFailed as e:
            raise ValueError(format_all_models_failed_error(e))

        # Strip <think> block before extracting SQL
        raw_no_think = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        sql = extract_sql(raw_no_think)
        last_sql = sql

        # SELECT guard (CTEs legitimately start with WITH, not SELECT)
        if not re.match(r"^\s*(SELECT|WITH)\b", sql, re.IGNORECASE):
            err = f"Non-SELECT SQL returned: {sql[:100]}"
            failed_attempts.append((sql, err))
            rejected_providers.add(provider_used)
            continue

        # Schema and security validation (org_id isolation strictly enforced)
        validation_errors = validate_sql(sql, _known_tables, _known_columns)
        if org_id:
            security_errors = validate_org_security(sql, org_id, _known_columns)
            validation_errors.extend(security_errors)
            
        if validation_errors:
            err = "Validation errors:\n" + "\n".join(f"  - {e}" for e in validation_errors)
            failed_attempts.append((sql, err))
            rejected_providers.add(provider_used)
            continue

        # SQL quality warnings (logged, don't block)
        check_sql_quality(sql)

        # SQL successfully generated and validated
        store_successful_example(question, sql, 1)

        return {
            "sql":               sql,
            "model_used":        model_used,
            "attempts":          attempt,
            "tables_used":       tables_used,
        }

    # All attempts exhausted
    raise ValueError(
        f"Could not generate working SQL after {MAX_ATTEMPTS} attempts.\n"
        f"Last SQL tried:\n{last_sql}\n"
        f"Last error: {failed_attempts[-1][1] if failed_attempts else 'unknown'}"
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "embedding_index_ready": is_index_ready(),
        "llm": system_llm_status(),
    }


@app.post("/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
async def chat(request: Request, req: ChatRequest, user: AuthenticatedUser = Depends(get_current_user)):
    # Secure org_id enforcement
    org_id = req.org_id
    
    # In auth mode, enforce verified JWT claims
    if REQUIRE_AUTH and user:
        org_id = user.org_id

    try:
        result = await generate_sql_with_retry(
            req.question,
            context=req.context,
            org_id=org_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return ChatResponse(
        sql=result["sql"],
        model_used=result["model_used"],
        attempts=result["attempts"],
    )
