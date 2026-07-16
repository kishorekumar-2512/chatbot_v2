"""
frontend/app.py — AI Database Report Chatbot UI.

Design tokens (see /mnt/skills/public/frontend-design guidance):
  Color   — void #0A0E14 · surface #131A24 · line #232C3A · ink #E8EEF5 ·
            ink-dim #8A97A8 · signal (high-conf/verified) #3DDC97 ·
            signal-warn (medium) #E8A33D · signal-danger (low/error) #E85D5D
  Type    — Space Grotesk (headers) · Inter (body) · JetBrains Mono (SQL,
            numbers, live model reasoning).
  Signature — the confidence score is one instrument-style gauge, not four
            generic progress bars.

This version adds: smart auto-charts (line/area/bar/donut/grouped-bar/
single-stat), animated stat counters, copy buttons, shimmer loading,
👍/👎 feedback, editable + re-runnable SQL, and multi-turn follow-up context.
"""

import json, os, re, uuid
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Matches "show this as a chart", "turn that into a graph", "visualize it",
# "chart this", etc. These aren't new data questions — they're a request to
# re-visualize data we ALREADY HAVE. Sending them through the full NL→SQL
# pipeline was the actual bug: with no real question to anchor on, the model
# would retrieve unrelated tables and hallucinate columns. This intercepts
# them client-side and just re-renders the previous result — no LLM call,
# instant, and can't hallucinate since it's reusing already-validated SQL.
_CHART_REQUEST_RE = re.compile(
    r"\b(show|make|turn|render|display|plot|visuali[sz]e|graph|chart)\b.*\b(this|it|that|these|those)\b.*\b(chart|graph|plot|visual)|"
    r"^(chart|graph|plot|visuali[sz]e)\s+(this|it|that)\b",
    re.IGNORECASE,
)

st.set_page_config(page_title="AI Database Report Chatbot", page_icon="◉", layout="wide")

# ── Design system ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --void: #0A0E14; --surface: #131A24; --line: #232C3A;
    --ink: #E8EEF5; --ink-dim: #8A97A8;
    --signal: #3DDC97; --signal-warn: #E8A33D; --signal-danger: #E85D5D;
}

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
h1, h2, h3, .app-title { font-family: 'Space Grotesk', sans-serif !important; letter-spacing: -0.01em; }
code, pre, .stCode, [data-testid="stMetricValue"] { font-family: 'JetBrains Mono', monospace !important; }

.app-title { font-size: 1.6rem; font-weight: 700; color: var(--ink); margin-bottom: 0; display:flex; align-items:center; gap:10px; }
.app-sub   { color: var(--ink-dim); font-size: 0.85rem; margin-top: 2px; }
.pulse-dot { width:8px; height:8px; border-radius:50%; background:var(--signal); display:inline-block;
             box-shadow: 0 0 0 0 rgba(61,220,151,.6); animation: pulse 2s infinite; }
@keyframes pulse {
  0%   { box-shadow: 0 0 0 0 rgba(61,220,151,.5); }
  70%  { box-shadow: 0 0 0 6px rgba(61,220,151,0); }
  100% { box-shadow: 0 0 0 0 rgba(61,220,151,0); }
}

/* Shimmer loading bar — sits under the live status message */
.shimmer-bar { position:relative; height:3px; border-radius:2px; overflow:hidden;
               background: var(--line); margin: 2px 0 10px 0; }
.shimmer-bar::after {
  content:''; position:absolute; top:0; left:-40%; width:40%; height:100%;
  background: linear-gradient(90deg, transparent, var(--signal), transparent);
  animation: shimmer 1.2s infinite;
}
@keyframes shimmer { 0% { left:-40%; } 100% { left:100%; } }

/* Buttons — quiet by default, accent on hover */
.stButton > button {
    background: var(--surface); color: var(--ink-dim); border: 1px solid var(--line);
    border-radius: 8px; font-size: 0.82rem; padding: 0.4rem 0.8rem; text-align: left;
    transition: all 0.15s ease;
}
.stButton > button:hover { border-color: var(--signal); color: var(--signal); background: var(--surface); }
.stButton > button:active { color: var(--void); background: var(--signal); }

.meta-badge { font-family:'JetBrains Mono',monospace; font-size:0.75rem; color:var(--ink-dim);
              background:var(--surface); border:1px solid var(--line); border-radius:6px;
              padding:3px 9px; display:inline-block; margin-right:6px; margin-bottom:6px; }

.stat-chip { font-family:'JetBrains Mono',monospace; font-size:0.78rem; color:var(--ink);
             background:rgba(61,220,151,0.08); border:1px solid rgba(61,220,151,0.35);
             border-radius:6px; padding:4px 10px; display:inline-block; margin-right:6px; margin-bottom:6px; }

section[data-testid="stSidebar"] h2 { font-size: 1rem; color: var(--ink); margin-top: 0.3rem; }
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="app-title"><span class="pulse-dot"></span> AI Database Report Chatbot</div>'
    '<div class="app-sub">6-layer accuracy pipeline · Qwen2.5-Coder → Groq → Gemini · ChromaDB + BM25 · Neon PostgreSQL</div>',
    unsafe_allow_html=True,
)
st.write("")

MODEL_LABELS = {
    "qwen":   ("🟢", "Qwen 2.5 Coder (local)"),
    "groq":   ("🟡", "Groq · Llama 3.3 70B"),
    "gemini": ("🔴", "Gemini 2.0 Flash"),
}
INTENT_EMOJI = {
    "COUNT": "🔢", "TOP_N": "🏆", "AGGREGATE": "➕", "TREND": "📈",
    "COMPARE": "⚖️", "EXISTS": "❓", "LIST": "📋", "META": "🗂",
}


# ── Small UI components ──────────────────────────────────────────────────────
def confidence_gauge(overall: float, level: str):
    """Signature element — instrument-style gauge instead of 4 progress bars."""
    color = {"high": "#3DDC97", "medium": "#E8A33D", "low": "#E85D5D"}.get(level, "#8A97A8")
    pct = max(0, min(100, overall))
    st.markdown(f"""
    <div style="margin:4px 0 10px 0">
      <div style="display:flex; align-items:baseline; gap:10px; margin-bottom:4px">
        <span style="font-family:'JetBrains Mono',monospace; font-size:1.4rem; font-weight:600; color:{color}">{pct:.0f}</span>
        <span style="font-family:'JetBrains Mono',monospace; font-size:0.75rem; color:var(--ink-dim)">/100 CONFIDENCE · {level.upper()}</span>
      </div>
      <div style="position:relative; height:6px; border-radius:3px;
                  background:linear-gradient(90deg, #E85D5D 0%, #E8A33D 50%, #3DDC97 100%); opacity:0.35">
      </div>
      <div style="position:relative; height:0">
        <div style="position:relative; left:{pct}%; transform:translate(-50%, -9px);
                    width:3px; height:12px; background:{color}; border-radius:2px"></div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def render_animated_stat(label: str, value: float):
    """Single-number results (e.g. 'how many customers') get an animated
    count-up instead of a chart — cheap, and reads as far more alive than a
    static number."""
    is_int = float(value).is_integer()
    target = int(value) if is_int else round(value, 2)
    uid = f"stat_{uuid.uuid4().hex[:8]}"
    components.html(f"""
    <div style="font-family:'Inter',sans-serif; text-align:center; padding:18px 0">
      <div id="{uid}" style="font-family:'JetBrains Mono',monospace; font-size:3rem; font-weight:600; color:#3DDC97">0</div>
      <div style="color:#8A97A8; font-size:0.85rem; margin-top:4px; text-transform:uppercase; letter-spacing:0.04em">{label}</div>
    </div>
    <script>
      (function() {{
        const el = document.getElementById("{uid}");
        const target = {target};
        const isInt = {str(is_int).lower()};
        const duration = 900;
        const start = performance.now();
        function frame(now) {{
          const p = Math.min(1, (now - start) / duration);
          const eased = 1 - Math.pow(1 - p, 3);
          const val = target * eased;
          el.textContent = isInt ? Math.round(val).toLocaleString() : val.toFixed(2);
          if (p < 1) requestAnimationFrame(frame);
        }}
        requestAnimationFrame(frame);
      }})();
    </script>
    """, height=110)


def render_copy_button(text: str, label: str = "Copy"):
    """Small clipboard-copy button for the answer text (SQL blocks already
    get a copy icon for free from st.code)."""
    uid = f"copy_{uuid.uuid4().hex[:8]}"
    # json.dumps doesn't escape "</", so a literal "</script>" inside `text`
    # (e.g. if the model's answer ever quoted such a string) would otherwise
    # prematurely close this component's <script> tag in the browser.
    safe_text = json.dumps(text).replace("</", "<\\/")
    components.html(f"""
    <button id="{uid}" style="font-family:'Inter',sans-serif; font-size:0.75rem; color:#8A97A8;
      background:#131A24; border:1px solid #232C3A; border-radius:6px; padding:3px 10px; cursor:pointer">
      📋 {label}
    </button>
    <script>
      document.getElementById("{uid}").addEventListener("click", function() {{
        navigator.clipboard.writeText({safe_text});
        this.textContent = "✓ Copied";
        setTimeout(() => this.innerHTML = "📋 {label}", 1500);
      }});
    </script>
    """, height=32)


def render_meta(data: dict):
    icon, label = MODEL_LABELS.get(data.get("model_used", "qwen"), ("⚪", data.get("model_used", "")))
    intent      = data.get("intent") or "LIST"
    intent_icon = INTENT_EMOJI.get(intent, "📋")
    warnings    = data.get("sql_warnings", [])
    c = data.get("confidence", {})

    st.markdown(
        f'<span class="meta-badge">{icon} {label}</span>'
        f'<span class="meta-badge">⏱ {data.get("latency_ms", 0):.0f} ms</span>'
        f'<span class="meta-badge">🔁 {data.get("attempts", 1)} attempt(s)</span>'
        f'<span class="meta-badge">📋 {len(data.get("tables_used", []))} tables</span>'
        f'<span class="meta-badge">{intent_icon} {intent}</span>',
        unsafe_allow_html=True,
    )

    confidence_gauge(c.get("overall", 0), c.get("level", "medium"))

    if warnings:
        st.warning("⚠️ SQL quality hints: " + " · ".join(warnings))
    if c.get("level") == "low" or data.get("attempts", 1) >= 3:
        st.warning(f"⚠️ Confidence {c.get('overall', 0):.0f}/100 ({c.get('level', '?')}) — review this result carefully.")

    with st.expander("📐 Confidence signal breakdown"):
        for sig_label, sig_key in [
            ("Table relevance", "table_relevance"), ("Column accuracy", "column_accuracy"),
            ("Attempt score", "attempt_score"), ("Row sanity", "row_sanity"),
        ]:
            val = c.get(sig_key, 0)
            st.markdown(f"""
            <div style="margin-bottom:6px">
              <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--ink-dim);margin-bottom:2px">
                <span>{sig_label}</span><span style="font-family:'JetBrains Mono',monospace">{val:.0f}</span>
              </div>
              <div style="background:rgba(138,151,168,.15);border-radius:6px;height:5px;overflow:hidden">
                <div style="background:var(--signal);height:100%;width:{val}%;border-radius:6px"></div>
              </div>
            </div>
            """, unsafe_allow_html=True)
        st.caption(f"Tables used: {', '.join(data.get('tables_used', [])) or '—'}")


def render_insights(insights: list[str]):
    if not insights:
        return
    st.markdown("".join(f'<span class="stat-chip">{s}</span>' for s in insights), unsafe_allow_html=True)


def render_followups(followups: list[str], key_prefix: str):
    if not followups:
        return
    st.caption("💡 Try next:")
    cols = st.columns(len(followups))
    for i, fu in enumerate(followups):
        with cols[i]:
            if st.button(f"› {fu}", key=f"{key_prefix}_fu_{i}", use_container_width=True):
                st.session_state["prefill"] = fu
                st.rerun()


def render_feedback(key_prefix: str, question: str, sql: str, model_used: str, confidence: dict):
    """👍/👎 feedback — logged server-side for finding where accuracy fails."""
    fb_key = f"{key_prefix}_feedback_sent"
    if st.session_state.get(fb_key):
        st.caption(f"✓ Feedback recorded: {st.session_state[fb_key]}")
        return
    c1, c2, _ = st.columns([1, 1, 6])
    with c1:
        if st.button("👍", key=f"{key_prefix}_up", help="This answer was helpful"):
            _send_feedback(question, sql, "up", model_used, confidence)
            st.session_state[fb_key] = "👍 helpful"
            st.rerun()
    with c2:
        if st.button("👎", key=f"{key_prefix}_down", help="This answer was wrong or unhelpful"):
            _send_feedback(question, sql, "down", model_used, confidence)
            st.session_state[fb_key] = "👎 not helpful"
            st.rerun()


def _send_feedback(question, sql, rating, model_used, confidence):
    try:
        requests.post(f"{BACKEND_URL}/feedback", json={
            "question": question, "sql": sql, "rating": rating,
            "model_used": model_used, "confidence": confidence,
        }, timeout=10)
    except Exception:
        pass  # feedback is best-effort, never block the UI on it


def render_result_body(rows: list[dict], chart_json, chart_kind, single_stat, question: str):
    """Shared renderer for chart/table — used for both the original result
    and re-run results, so editing SQL feels consistent."""
    if chart_kind == "single_stat" and single_stat:
        render_animated_stat(single_stat["label"], single_stat["value"])
    elif chart_json:
        import plotly.graph_objects as go
        st.plotly_chart(go.Figure(json.loads(chart_json)), use_container_width=True)

    total = len(rows)
    if total > 0:
        st.caption(f"📋 {total} row(s) returned")
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    elif chart_kind != "single_stat":
        st.info("ℹ️ Query returned 0 rows.")


def render_editable_sql(key_prefix: str, sql: str, question: str):
    """SQL is now editable and re-runnable, not just a read-only code block.
    Re-running goes through the same server-side security validation as the
    normal pipeline — editing doesn't bypass it."""
    edit_key = f"{key_prefix}_sql_edit"
    result_key = f"{key_prefix}_rerun_result"

    with st.expander("📝 Generated SQL (editable)", expanded=False):
        edited_sql = st.text_area("SQL", value=st.session_state.get(edit_key, sql),
                                   key=edit_key, height=140, label_visibility="collapsed")
        c1, c2 = st.columns([1, 5])
        with c1:
            run_clicked = st.button("▶ Run this SQL", key=f"{key_prefix}_run_sql")
        if run_clicked:
            with st.spinner("Running..."):
                try:
                    r = requests.post(f"{BACKEND_URL}/run-sql",
                                       json={"sql": edited_sql, "question": question}, timeout=60)
                    if r.ok:
                        st.session_state[result_key] = r.json()
                    else:
                        st.session_state[result_key] = {"error": r.json().get("detail", r.text)}
                except Exception as e:
                    st.session_state[result_key] = {"error": str(e)}

        result = st.session_state.get(result_key)
        if result:
            if result.get("error"):
                st.error(f"❌ {result['error']}")
            else:
                st.success(f"✅ {result['row_count']} row(s)")
                render_insights(result.get("insights", []))
                render_result_body(result["rows"], result.get("chart_json"),
                                    result.get("chart_kind"), result.get("single_stat"), question)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Status")
    if st.button("Check backend", use_container_width=True):
        try:
            r = requests.get(f"{BACKEND_URL}/health", timeout=10)
            if r.ok:
                d = r.json()
                st.success("✅ Backend online")
                st.caption(f"Index ready: {'✅' if d.get('embedding_index_ready') else '❌'}")
            else:
                st.error("❌ Backend error")
        except Exception as e:
            st.error(f"❌ {e}")

    st.divider()
    st.header("Circuit breaker")
    if st.button("Refresh status", use_container_width=True):
        try:
            r = requests.get(f"{BACKEND_URL}/circuit-status", timeout=10)
            if r.ok:
                for tier, s in r.json().items():
                    icon = "🔴" if s["circuit_open"] else "🟢"
                    st.markdown(f"{icon} **{s['name']}** — {s['consecutive_failures']} failures")
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.header("Schema")
    if st.button("Load schema", use_container_width=True):
        try:
            r = requests.get(f"{BACKEND_URL}/schema", timeout=60)
            if r.ok:
                d = r.json()
                st.caption(f"{d.get('table_count', '?')} tables")
                st.code(d["schema"][:3000] + "\n... (truncated)", language="sql")
            else:
                st.error("Failed")
        except Exception as e:
            st.error(str(e))

    st.divider()
    if st.session_state.get("last_context"):
        st.header("Conversation")
        lc = st.session_state["last_context"]
        st.caption(f"Following up on: *{lc['question'][:60]}{'…' if len(lc['question']) > 60 else ''}*")
        if st.button("↺ Start fresh topic", use_container_width=True):
            st.session_state["last_context"] = None
            st.rerun()
        st.divider()

    st.markdown("**Example queries**")
    examples = [
        "How many customers are there in total?",
        "Show devices with unresolved critical alerts",
        "Top 10 most installed software",
        "Which users haven't logged in for 30 days?",
        "Show failed patches by severity",
        "Devices with free disk space less than 10GB",
        "Show login trend by month for the last 6 months",
        "Top 3 devices with the most missing patches, broken down by severity",
        "List all tables",
    ]
    for i, ex in enumerate(examples):
        if st.button(ex, key=f"example_{i}", use_container_width=True):
            st.session_state["prefill"] = ex

# ── Session state ─────────────────────────────────────────────────────────────
if "messages"     not in st.session_state: st.session_state.messages     = []
if "last_result"  not in st.session_state: st.session_state.last_result  = None
if "last_context" not in st.session_state: st.session_state.last_context = None

# Render history
for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        is_result_card = msg["role"] == "assistant" and ("sql" in msg or msg.get("data") is not None)
        if is_result_card:
            with st.container(border=True):
                if msg.get("meta"):
                    render_meta(msg["meta"])
                else:
                    st.markdown('<span class="meta-badge">🔁 Re-rendered from previous query — no model call</span>', unsafe_allow_html=True)
                col_a, col_b = st.columns([10, 1])
                with col_a:
                    st.markdown(msg["content"])
                with col_b:
                    render_copy_button(msg["content"], "")
                render_insights(msg.get("insights", []))
                render_result_body(msg.get("data", []), msg.get("chart_json"),
                                    msg.get("chart_kind"), msg.get("single_stat"), msg.get("question", ""))
                render_editable_sql(f"m{idx}", msg.get("sql", ""), msg.get("question", ""))
                if msg.get("meta"):
                    render_feedback(f"m{idx}", msg.get("question", ""), msg.get("sql", ""),
                                     msg["meta"].get("model_used", ""), msg["meta"].get("confidence", {}))
                render_followups(msg.get("followups", []), key_prefix=f"m{idx}")
        else:
            st.markdown(msg["content"])

# ── Input ─────────────────────────────────────────────────────────────────────
prefill  = st.session_state.pop("prefill", "")
question = st.chat_input("Ask about your data…") or prefill

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # "Show this as a chart" / "visualize it" / "chart that" etc. aren't new
    # data questions — they're a request to re-visualize data we already
    # have. Sending them through the full NL→SQL pipeline was a real bug:
    # with nothing concrete to anchor on, the model would grab unrelated
    # tables and hallucinate columns. Intercept client-side instead: re-run
    # the previous (already-validated) SQL through /run-sql and just
    # re-render — no LLM call, instant, can't hallucinate.
    if _CHART_REQUEST_RE.search(question) and st.session_state.get("last_result"):
        prev = st.session_state["last_result"]
        with st.chat_message("assistant"):
            with st.container(border=True):
                st.markdown('<span class="meta-badge">🔁 Re-rendered from previous query — no model call</span>', unsafe_allow_html=True)
                try:
                    r = requests.post(f"{BACKEND_URL}/run-sql",
                                       json={"sql": prev["sql"], "question": prev["question"]}, timeout=60)
                    if r.ok:
                        rr = r.json()
                        st.markdown(f"Here's **{prev['question']}** as a visual:")
                        render_insights(rr.get("insights", []))
                        render_result_body(rr["rows"], rr.get("chart_json"), rr.get("chart_kind"),
                                            rr.get("single_stat"), prev["question"])
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"Here's **{prev['question']}** as a visual:",
                            "question": prev["question"], "sql": prev["sql"],
                            "data": rr["rows"], "chart_json": rr.get("chart_json"),
                            "chart_kind": rr.get("chart_kind"), "single_stat": rr.get("single_stat"),
                            "insights": rr.get("insights", []), "followups": [],
                            "meta": None,  # no model/confidence to show — this wasn't a fresh query
                        })
                    else:
                        st.error(f"❌ {r.json().get('detail', r.text)}")
                except Exception as e:
                    st.error(f"❌ {e}")
        st.stop()

    with st.chat_message("assistant"):
        result_card = st.container(border=True)
        status_box = result_card.empty()
        shimmer_box = result_card.empty()
        status_box.info("🔍 Starting…")
        shimmer_box.markdown('<div class="shimmer-bar"></div>', unsafe_allow_html=True)

        thinking_header = result_card.empty()
        thinking_box = result_card.empty()
        thinking_text = ""

        final_data = None
        error_msg = None

        def render_thinking(full_text: str):
            think_part, rest_part = full_text, ""
            if "</think>" in full_text:
                think_part, rest_part = full_text.split("</think>", 1)
                think_part = think_part.replace("<think>", "")
            elif "<think>" in full_text:
                think_part = full_text.replace("<think>", "")

            thinking_header.markdown('<span class="pulse-dot"></span> **Model is thinking…**', unsafe_allow_html=True)
            body = think_part.strip()
            if rest_part.strip():
                body += "\n\n---\n" + rest_part.strip()
            thinking_box.code(body[-4000:], language="text")

        # Multi-turn context: always send the last turn's {question, sql,
        # tables_used} — the backend only actually USES it when the current
        # question looks like a follow-up ("filter that...", "now show...").
        payload = {"question": question}
        if st.session_state.get("last_context"):
            payload["context"] = st.session_state["last_context"]

        try:
            resp = requests.post(f"{BACKEND_URL}/chat/stream", json=payload, stream=True, timeout=300)
            if not resp.ok:
                status_box.empty(); shimmer_box.empty()
                result_card.error(f"❌ Backend returned {resp.status_code}: {resp.text[:300]}")
                st.session_state.messages.append({"role": "assistant", "content": f"❌ Request failed ({resp.status_code})"})
            else:
                for line in resp.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[len("data: "):])
                    except json.JSONDecodeError:
                        continue

                    etype = event.get("type")
                    if etype == "status":
                        status_box.info(event.get("message", ""))
                    elif etype == "thinking_token":
                        thinking_text += event.get("text", "")
                        render_thinking(thinking_text)
                    elif etype == "final":
                        final_data = event["data"]
                    elif etype == "error":
                        error_msg = event.get("message", "Unknown error")

                status_box.empty(); shimmer_box.empty()
                thinking_header.empty(); thinking_box.empty()

                if error_msg:
                    result_card.error(f"❌ {error_msg}")
                    result_card.caption("💡 Try rephrasing more specifically.")
                    st.session_state.messages.append({"role": "assistant", "content": f"❌ {error_msg}"})
                elif final_data:
                    data = final_data
                    msg_idx = len(st.session_state.messages)  # this message's future index
                    with result_card:
                        if thinking_text.strip():
                            with st.expander("🧠 Model reasoning (this attempt)", expanded=False):
                                st.code(thinking_text.strip()[-6000:], language="text")

                        render_meta(data)
                        col_a, col_b = st.columns([10, 1])
                        with col_a:
                            st.markdown(data["answer"])
                        with col_b:
                            render_copy_button(data["answer"], "")
                        render_insights(data.get("insights", []))
                        render_result_body(data["rows"], data.get("chart_json"),
                                            data.get("chart_kind"), data.get("single_stat"), question)
                        render_editable_sql(f"m{msg_idx}", data["sql"], question)
                        render_feedback(f"m{msg_idx}", question, data["sql"],
                                         data["model_used"], data["confidence"])
                        render_followups(data.get("followups", []), key_prefix=f"m{msg_idx}")

                    st.session_state.last_result = {
                        "question": question, "sql": data["sql"],
                        "rows": data["rows"], "chart_json": data.get("chart_json"),
                    }
                    st.session_state.last_context = {
                        "question": question, "sql": data["sql"],
                        "tables_used": data.get("tables_used", []),
                    }
                    st.session_state.messages.append({
                        "role": "assistant", "content": data["answer"], "question": question,
                        "data": data["rows"], "chart_json": data.get("chart_json"),
                        "chart_kind": data.get("chart_kind"), "single_stat": data.get("single_stat"),
                        "sql": data["sql"],
                        "insights": data.get("insights", []),
                        "followups": data.get("followups", []),
                        "meta": {
                            "model_used": data["model_used"],
                            "latency_ms": data["latency_ms"],
                            "attempts": data["attempts"],
                            "tables_used": data["tables_used"],
                            "confidence": data["confidence"],
                            "intent": data.get("intent"),
                            "sql_warnings": data.get("sql_warnings", []),
                        },
                    })
                else:
                    result_card.error("❌ Stream ended without a result.")

        except requests.exceptions.ReadTimeout:
            status_box.empty(); shimmer_box.empty()
            result_card.error("⏰ Timed out after 5 minutes.")
        except requests.exceptions.ConnectionError:
            status_box.empty(); shimmer_box.empty()
            result_card.error("❌ Cannot reach backend. Is uvicorn running on port 8000?")
        except Exception as e:
            status_box.empty(); shimmer_box.empty()
            result_card.error(f"Unexpected error: {e}")

# ── PDF export ────────────────────────────────────────────────────────────────
if st.session_state.last_result:
    st.divider()
    _, col = st.columns([4, 1])
    with col:
        if st.button("📄 Download PDF", use_container_width=True):
            res = st.session_state.last_result
            with st.spinner("Generating PDF…"):
                try:
                    r = requests.post(
                        f"{BACKEND_URL}/report/pdf",
                        json={"question": res["question"], "sql": res["sql"],
                              "rows": res["rows"], "chart_json": res.get("chart_json")},
                        timeout=60,
                    )
                    if r.ok:
                        st.download_button("⬇️ Save PDF", data=r.content,
                                           file_name="report.pdf", mime="application/pdf")
                    else:
                        st.error(f"PDF failed: {r.text}")
                except Exception as e:
                    st.error(str(e))
