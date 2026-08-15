"""
Diagnostic script: tests LLM keys exactly the way the app reads and uses them.
Run: python diagnose_llm.py
"""
import os, sys, json, asyncio, hashlib
from pathlib import Path
from dotenv import dotenv_values, load_dotenv
import httpx

# ── Step 1: Show how the app reads keys ──────────────────────────────────────
print("=" * 70)
print("STEP 1: How the app reads your .env keys")
print("=" * 70)

env_path = Path(__file__).resolve().parent / ".env"
print(f"\n.env path: {env_path}")
print(f".env exists: {env_path.exists()}")

# Read via dotenv_values (same as llm_config.py)
file_values = dotenv_values(env_path)

# Also load into os.environ (same as main.py line 21)
load_dotenv()

groq_key_dotenv = file_values.get("GROQ_API_KEY", "")
groq_key_osenv = os.getenv("GROQ_API_KEY", "")
gemini_key_dotenv = file_values.get("GEMINI_API_KEY", "")
gemini_key_osenv = os.getenv("GEMINI_API_KEY", "")

print(f"\nGROQ_API_KEY (dotenv_values): '{groq_key_dotenv[:10]}...{groq_key_dotenv[-6:]}' (len={len(groq_key_dotenv)})")
print(f"GROQ_API_KEY (os.getenv):     '{groq_key_osenv[:10]}...{groq_key_osenv[-6:]}' (len={len(groq_key_osenv)})")
print(f"GROQ keys match: {groq_key_dotenv == groq_key_osenv}")
print(f"GROQ key has whitespace: {groq_key_dotenv != groq_key_dotenv.strip()}")
print(f"GROQ key repr: {repr(groq_key_dotenv[:15])}...{repr(groq_key_dotenv[-10:])}")

print(f"\nGEMINI_API_KEY (dotenv_values): '{gemini_key_dotenv[:10]}...{gemini_key_dotenv[-6:]}' (len={len(gemini_key_dotenv)})")
print(f"GEMINI_API_KEY (os.getenv):     '{gemini_key_osenv[:10]}...{gemini_key_osenv[-6:]}' (len={len(gemini_key_osenv)})")
print(f"GEMINI keys match: {gemini_key_dotenv == gemini_key_osenv}")
print(f"GEMINI key has whitespace: {gemini_key_dotenv != gemini_key_dotenv.strip()}")
print(f"GEMINI key repr: {repr(gemini_key_dotenv[:15])}...{repr(gemini_key_dotenv[-10:])}")

groq_model = file_values.get("GROQ_MODEL", "llama-3.3-70b-versatile")
gemini_model = file_values.get("GEMINI_MODEL", "gemini-2.0-flash")
print(f"\nGROQ_MODEL:  {groq_model}")
print(f"GEMINI_MODEL: {gemini_model}")

# ── Step 2: Check the BYO key store ──────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 2: BYO key store (data/llm_keys.json)")
print("=" * 70)

key_store_path = Path(__file__).resolve().parent / "data" / "llm_keys.json"
if key_store_path.exists():
    with open(key_store_path) as f:
        store = json.load(f)
    for tenant_id, entries in store.get("tenants", {}).items():
        for provider, entry in entries.items():
            print(f"\n  Tenant '{tenant_id}' -> {provider}:")
            print(f"    Model: {entry.get('model')}")
            print(f"    Enabled: {entry.get('enabled')}")
            print(f"    Version: {entry.get('version')}")
else:
    print("  No key store found")

# ── Step 3: Test Groq API directly ──────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 3: Testing Groq API (system key)")
print("=" * 70)


async def test_groq():
    key = groq_key_dotenv.strip()
    if not key:
        print("  SKIP: No Groq key configured")
        return
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": groq_model,
        "messages": [{"role": "user", "content": "Reply with: OK"}],
        "max_tokens": 10,
        "temperature": 0.1,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            print(f"  Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                print(f"  Response: {text}")
                print("  ✅ GROQ SYSTEM KEY WORKS!")
            else:
                print(f"  Response: {resp.text[:300]}")
                print("  ❌ GROQ SYSTEM KEY FAILED!")
    except Exception as e:
        print(f"  Error: {e}")
        print("  ❌ GROQ SYSTEM KEY FAILED!")


asyncio.run(test_groq())

# ── Step 4: Test Gemini API directly ─────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 4: Testing Gemini API (system key)")
print("=" * 70)


async def test_gemini():
    key = gemini_key_dotenv.strip()
    if not key:
        print("  SKIP: No Gemini key configured")
        return
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": "Reply with: OK"}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 10},
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, params={"key": key}, json=payload)
            print(f"  Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                print(f"  Response: {text}")
                print("  ✅ GEMINI SYSTEM KEY WORKS!")
            else:
                print(f"  Response: {resp.text[:300]}")
                print("  ❌ GEMINI SYSTEM KEY FAILED!")
    except Exception as e:
        print(f"  Error: {e}")
        print("  ❌ GEMINI SYSTEM KEY FAILED!")


asyncio.run(test_gemini())

# ── Step 5: Test Ollama ──────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 5: Testing Ollama (local)")
print("=" * 70)

ollama_url = file_values.get("OLLAMA_BASE_URL", "http://localhost:11434")
ollama_model = file_values.get("OLLAMA_MODEL", "qwen2.5-coder:7b")


async def test_ollama():
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{ollama_url}")
            print(f"  Ollama server: {resp.status_code} — {'Running' if resp.status_code == 200 else 'Error'}")
            if resp.status_code == 200:
                # Test generation
                resp2 = await client.post(
                    f"{ollama_url}/api/generate",
                    json={"model": ollama_model, "prompt": "Reply with: OK", "stream": False,
                          "options": {"num_predict": 10}},
                    timeout=30.0,
                )
                if resp2.status_code == 200:
                    print(f"  Response: {resp2.json().get('response', '')[:100]}")
                    print("  ✅ OLLAMA WORKS!")
                else:
                    print(f"  Error: {resp2.text[:200]}")
                    print("  ❌ OLLAMA GENERATION FAILED!")
    except httpx.ConnectError:
        print("  ❌ Ollama is NOT running at", ollama_url)
    except httpx.TimeoutException:
        print("  ❌ Ollama TIMED OUT")
    except Exception as e:
        print(f"  ❌ Error: {e}")


asyncio.run(test_ollama())

# ── Step 6: Check BYO Groq model issue ───────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 6: BYO key problem — model 'openai/gpt-oss-120b'")
print("=" * 70)

# The BYO key for tenant 2 uses model "openai/gpt-oss-120b" which returns 413
# Let's test the same key with the correct model
from backend.llm_key_store import _simple_decrypt

if key_store_path.exists():
    with open(key_store_path) as f:
        store = json.load(f)
    tenant_2 = store.get("tenants", {}).get("2", {})
    groq_byo = tenant_2.get("groq", {})
    if groq_byo:
        try:
            byo_key = _simple_decrypt(groq_byo["encrypted_key"])
            byo_model = groq_byo.get("model", "unknown")
            print(f"  BYO Groq key: {byo_key[:10]}...{byo_key[-6:]} (len={len(byo_key)})")
            print(f"  BYO model: {byo_model}")
            print(f"\n  Testing BYO key with model '{byo_model}'...")

            async def test_byo_groq():
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {byo_key}", "Content-Type": "application/json"}
                # First test with the configured model
                payload = {
                    "model": byo_model,
                    "messages": [{"role": "user", "content": "Reply with: OK"}],
                    "max_tokens": 10,
                }
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    print(f"  Status with '{byo_model}': {resp.status_code}")
                    if resp.status_code != 200:
                        print(f"  Error: {resp.text[:200]}")
                    # Now test with a known-good model
                    payload["model"] = "llama-3.3-70b-versatile"
                    resp2 = await client.post(url, headers=headers, json=payload)
                    print(f"\n  Status with 'llama-3.3-70b-versatile': {resp2.status_code}")
                    if resp2.status_code == 200:
                        print("  ✅ BYO key works with correct model!")
                        print("  ⚠️  The model 'openai/gpt-oss-120b' is the problem, not the key!")
                    else:
                        print(f"  Error: {resp2.text[:200]}")

            asyncio.run(test_byo_groq())
        except Exception as e:
            print(f"  Error decrypting BYO key: {e}")

# ── Step 7: Circuit Breaker Status ───────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 7: Circuit Breaker Analysis")
print("=" * 70)
print("""
  The circuit breaker in llm_orchestrator.py has a CRITICAL design issue:
  
  When an 'auth' or 'request' error occurs, it sets:
      state.blocked = True
  
  This is a PERMANENT block that NEVER auto-recovers.
  It persists for the entire lifetime of the server process.
  
  Even if your keys are valid NOW, if they failed ONCE since the last
  server restart, the breaker blocks all future attempts.
  
  This is likely WHY your keys work in a test file but fail in the app!
""")

print("=" * 70)
print("DIAGNOSIS COMPLETE")
print("=" * 70)
