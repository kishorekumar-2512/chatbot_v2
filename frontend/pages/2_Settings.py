"""
frontend/pages/2_Settings.py

LLM API Key Settings page.
Users can add their own API keys here.
If configured, their key takes priority over the built-in fallback chain.
"""

import os
import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Settings · LLM Keys", page_icon="⚙️", layout="wide")

st.title("⚙️ LLM Settings")
st.caption("Add your company's LLM API keys. When configured, your key is used instead of the default fallback chain.")

# ── Info banner ───────────────────────────────────────────────────────────────
st.info("""
**How it works:**
- If you add your own API key, it will be used for all queries (higher priority than defaults)
- If no key is added, or if your key fails, the system falls back to: **Qwen (local) → Groq → Gemini**
- Keys are stored encrypted on the server
- You can add multiple providers — the system will try them in priority order
""")

# ── Priority order ────────────────────────────────────────────────────────────
st.markdown("### Priority Order")
st.markdown("""
| Priority | Provider | When Used |
|---|---|---|
| 1st | **Your OpenAI key** | If added and enabled |
| 2nd | **Your Anthropic key** | If added and enabled |
| 3rd | **Your DeepSeek key** | If added and enabled |
| 4th | **Your Groq key** | If added and enabled |
| 5th | **Your Gemini key** | If added and enabled |
| 6th | **Your Ollama (local)** | If added and enabled |
| Fallback | **Built-in chain** | If none of your keys are set |
""")

st.divider()

# ── Load providers and existing keys ──────────────────────────────────────────
try:
    providers_resp = requests.get(f"{BACKEND_URL}/settings/providers", timeout=10)
    keys_resp      = requests.get(f"{BACKEND_URL}/settings/keys", timeout=10)
    providers      = providers_resp.json().get("providers", {}) if providers_resp.ok else {}
    saved_keys     = keys_resp.json().get("keys", {}) if keys_resp.ok else {}
except Exception as e:
    st.error(f"Cannot connect to backend: {e}")
    st.stop()

# ── Show configured keys ───────────────────────────────────────────────────────
st.markdown("### Configured API Keys")

if not saved_keys:
    st.caption("No API keys configured yet. Add one below.")
else:
    for provider_id, info in saved_keys.items():
        col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
        with col1:
            st.markdown(f"**{info['provider_name']}**  `{info['model']}`")
            st.caption(f"Key: `{info['key_preview']}`")
        with col2:
            status = "🟢 Enabled" if info["enabled"] else "🔴 Disabled"
            st.markdown(status)
        with col3:
            new_state = not info["enabled"]
            label = "Disable" if info["enabled"] else "Enable"
            if st.button(label, key=f"toggle_{provider_id}"):
                r = requests.patch(f"{BACKEND_URL}/settings/keys/toggle",
                    json={"provider": provider_id, "enabled": new_state})
                if r.ok:
                    st.success(f"{'Enabled' if new_state else 'Disabled'} {info['provider_name']}")
                    st.rerun()
        with col4:
            if st.button("🗑️ Remove", key=f"del_{provider_id}"):
                r = requests.delete(f"{BACKEND_URL}/settings/keys/{provider_id}")
                if r.ok:
                    st.success(f"Removed {info['provider_name']} key")
                    st.rerun()

st.divider()

# ── Add new key form ───────────────────────────────────────────────────────────
st.markdown("### Add / Update API Key")

PROVIDER_ICONS = {
    "openai":    "🤖",
    "anthropic": "🧠",
    "deepseek":  "🐋",
    "groq":      "⚡",
    "gemini":    "✨",
    "ollama":    "🦙",
}

PROVIDER_LINKS = {
    "openai":    "https://platform.openai.com/api-keys",
    "anthropic": "https://console.anthropic.com/keys",
    "deepseek":  "https://platform.deepseek.com/api_keys",
    "groq":      "https://console.groq.com (Free tier — no credit card)",
    "gemini":    "https://aistudio.google.com (Free tier — no credit card)",
    "ollama":    "No key needed — runs locally. Install from https://ollama.com",
}

col_left, col_right = st.columns([1, 1])

with col_left:
    provider = st.selectbox(
        "Provider",
        options=list(providers.keys()),
        format_func=lambda p: f"{PROVIDER_ICONS.get(p,'')} {providers[p]['name']}",
    )

    if provider:
        link = PROVIDER_LINKS.get(provider, "")
        st.caption(f"Get your key at: **{link}**")

        models = providers[provider]["models"]
        model = st.selectbox("Model", options=models)

        if provider == "ollama":
            api_key = st.text_input(
                "Ollama Base URL",
                value="http://localhost:11434",
                help="URL where Ollama is running",
            )
        else:
            api_key = st.text_input(
                "API Key",
                type="password",
                placeholder="sk-..." if provider in ("openai","anthropic","groq","deepseek") else "Enter API key",
                help="Your key is stored encrypted on the server",
            )

with col_right:
    st.markdown("&nbsp;")  # spacing
    if provider and api_key and model:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔍 Test Key", use_container_width=True):
                with st.spinner("Testing..."):
                    r = requests.post(
                        f"{BACKEND_URL}/settings/keys/validate",
                        json={"provider": provider, "api_key": api_key, "model": model},
                        timeout=15,
                    )
                    if r.ok:
                        result = r.json()
                        if result.get("valid"):
                            st.success("✅ Key is valid!")
                        else:
                            st.error(f"❌ {result.get('error', 'Key is invalid')}")
                    else:
                        st.error(f"Backend error: {r.text}")

        with c2:
            if st.button("💾 Save Key", use_container_width=True, type="primary"):
                with st.spinner("Validating and saving..."):
                    r = requests.post(
                        f"{BACKEND_URL}/settings/keys",
                        json={"provider": provider, "api_key": api_key, "model": model},
                        timeout=15,
                    )
                    if r.ok:
                        st.success(f"✅ {providers[provider]['name']} key saved!")
                        st.balloons()
                        st.rerun()
                    else:
                        err = r.json().get("detail", r.text)
                        st.error(f"❌ {err}")

st.divider()

# ── Current LLM status ────────────────────────────────────────────────────────
st.markdown("### Current System Status")
try:
    health = requests.get(f"{BACKEND_URL}/health", timeout=5)
    if health.ok:
        d = health.json()
        cb = d.get("circuit_breaker", {})

        col1, col2, col3 = st.columns(3)
        with col1:
            p = cb.get("primary", {})
            icon = "🔴" if p.get("circuit_open") else "🟢"
            st.metric("Qwen (Primary)", f"{icon} {'Open' if p.get('circuit_open') else 'OK'}",
                      f"{p.get('consecutive_failures',0)} failures")
        with col2:
            f1 = cb.get("fallback1", {})
            icon = "🔴" if f1.get("circuit_open") else "🟢"
            st.metric("Groq (Fallback 1)", f"{icon} {'Open' if f1.get('circuit_open') else 'OK'}",
                      f"{f1.get('consecutive_failures',0)} failures")
        with col3:
            f2 = cb.get("fallback2", {})
            icon = "🔴" if f2.get("circuit_open") else "🟢"
            st.metric("Gemini (Fallback 2)", f"{icon} {'Open' if f2.get('circuit_open') else 'OK'}",
                      f"{f2.get('consecutive_failures',0)} failures")
except Exception:
    st.caption("Could not fetch system status.")

st.divider()
st.caption("💡 Tip: If your company already pays for OpenAI or Claude, add that key here for the best SQL generation quality and speed.")
