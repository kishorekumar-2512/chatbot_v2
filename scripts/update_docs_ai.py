#!/usr/bin/env python3
# ==============================================================================
# scripts/update_docs_ai.py — Living Project Documentation AI Updater
#
# Analyzes git diff against the last-synced commit, calls an LLM (Claude/Gemini/Groq)
# with a developer-reasoning prompt to update PROJECT_DOCS.md in place, append
# to the Update Log, and update the <!-- docs-last-synced: <sha> --> comment.
# ==============================================================================

import os
import re
import sys
import json
import datetime
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_PATH = ROOT / "PROJECT_DOCS.md"


def get_current_head_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()


def extract_last_synced_sha(content: str) -> str | None:
    match = re.search(r"<!--\s*docs-last-synced:\s*([a-f0-9]+)\s*-->", content)
    return match.group(1) if match else None


def get_git_diff(last_sha: str | None) -> tuple[str, str]:
    if not last_sha:
        # Initial diff of last commit
        diff_stat = subprocess.check_output(["git", "diff", "HEAD~1..HEAD", "--stat"], cwd=ROOT).decode()
        diff_full = subprocess.check_output(["git", "diff", "HEAD~1..HEAD"], cwd=ROOT).decode()
    else:
        try:
            diff_stat = subprocess.check_output(["git", "diff", f"{last_sha}..HEAD", "--stat"], cwd=ROOT).decode()
            diff_full = subprocess.check_output(["git", "diff", f"{last_sha}..HEAD"], cwd=ROOT).decode()
        except subprocess.CalledProcessError:
            diff_stat = subprocess.check_output(["git", "diff", "HEAD~1..HEAD", "--stat"], cwd=ROOT).decode()
            diff_full = subprocess.check_output(["git", "diff", "HEAD~1..HEAD"], cwd=ROOT).decode()
    return diff_stat, diff_full


def call_ai_updater(docs_content: str, diff_stat: str, diff_full: str, new_sha: str) -> str | None:
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")

    # Truncate diff if extremely large to fit context window
    truncated_diff = diff_full[:50000] if len(diff_full) > 50000 else diff_full
    today_str = datetime.date.today().isoformat()

    prompt = f"""You are Antigravity, an expert software architect maintaining the living documentation file PROJECT_DOCS.md for chatbot_v2.

Here is the Git Diff of recent changes since the last documentation sync:
Diff Statistics:
{diff_stat}

Diff Content:
{truncated_diff}

Here is the current full PROJECT_DOCS.md:
{docs_content}

INSTRUCTIONS:
1. Reason like a senior software developer about WHAT changed and WHY it changed.
2. If any architectural diagrams, data flows, pipeline stages, or module responsibilities changed, update Sections 2 through 6 IN PLACE to accurately describe the CURRENT state.
3. Update the File-by-File Reference tables in Section 4 if any files were added, deleted, or modified.
4. Append a new dated entry to Section 7 (Update Log) under today's date ({today_str}). NEVER edit, shorten, or remove past log entries.
5. Update the first line comment to: <!-- docs-last-synced: {new_sha} -->
6. Return the ENTIRE updated PROJECT_DOCS.md markdown content. Do not include markdown code block backticks around the entire document—return the raw markdown text directly.
"""

    # 1. Try Anthropic Claude API if key present
    if anthropic_key:
        try:
            import httpx
            headers = {
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": 8000,
                "messages": [{"role": "user", "content": prompt}],
            }
            with httpx.Client(timeout=120.0) as client:
                r = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
                if r.status_code == 200:
                    return r.json()["content"][0]["text"].strip()
        except Exception as e:
            print(f"[Warning] Anthropic API failed: {e}, falling back...")

    # 2. Try Gemini API if key present
    if gemini_key:
        try:
            import httpx
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8000},
            }
            with httpx.Client(timeout=120.0) as client:
                r = client.post(url, params={"key": gemini_key}, json=payload)
                if r.status_code == 200:
                    cand = r.json().get("candidates", [{}])[0]
                    parts = cand.get("content", {}).get("parts", [])
                    return "".join(p.get("text", "") for p in parts).strip()
        except Exception as e:
            print(f"[Warning] Gemini API failed: {e}, falling back...")

    # 3. Try Groq API if key present
    if groq_key:
        try:
            import httpx
            headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
            payload = {
                "model": "openai/gpt-oss-120b",
                "messages": [
                    {"role": "system", "content": "You are a senior documentation engineer."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 8000,
                "temperature": 0.1,
            }
            with httpx.Client(timeout=120.0) as client:
                r = client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"].get("content", "").strip()
        except Exception as e:
            print(f"[Warning] Groq API failed: {e}")

    return None


def fallback_append_log(docs_content: str, diff_stat: str, new_sha: str) -> str:
    """Deterministic fallback if AI API keys are not configured in CI."""
    today = datetime.date.today().isoformat()
    lines = docs_content.splitlines()
    if lines and lines[0].startswith("<!-- docs-last-synced:"):
        lines[0] = f"<!-- docs-last-synced: {new_sha} -->"
    else:
        lines.insert(0, f"<!-- docs-last-synced: {new_sha} -->")

    updated_content = "\n".join(lines)
    stat_summary = "\n".join(f"  - {line.strip()}" for line in diff_stat.splitlines() if line.strip())

    entry = f"""
### [{today}] — Automated Sync: Commit {new_sha[:8]}
- Automated sync recorded changes from commit `{new_sha[:8]}`.
- Modified Files:
{stat_summary}
- *Reasoning:* Repository update detected; synced documentation commit watermark.
"""
    return updated_content.rstrip() + "\n" + entry + "\n"


def main():
    if not DOCS_PATH.exists():
        print(f"Error: {DOCS_PATH} not found.")
        sys.exit(1)

    with open(DOCS_PATH, "r", encoding="utf-8") as f:
        docs_content = f.read()

    last_sha = extract_last_synced_sha(docs_content)
    current_sha = get_current_head_sha()

    print(f"Last synced SHA: {last_sha}")
    print(f"Current HEAD SHA: {current_sha}")

    if last_sha == current_sha:
        print("Documentation is already up-to-date with HEAD commit. Nothing to do.")
        sys.exit(0)

    diff_stat, diff_full = get_git_diff(last_sha)
    if not diff_full.strip():
        print("No file differences detected. Updating watermark only.")
        updated_docs = re.sub(r"<!--\s*docs-last-synced:\s*([a-f0-9]+)\s*-->", f"<!-- docs-last-synced: {current_sha} -->", docs_content)
        with open(DOCS_PATH, "w", encoding="utf-8", newline="\n") as f:
            f.write(updated_docs)
        sys.exit(0)

    print(f"Analyzing diff ({len(diff_full)} chars)...")
    ai_result = call_ai_updater(docs_content, diff_stat, diff_full, current_sha)

    if ai_result and "## 7. Update Log" in ai_result:
        print("AI documentation update generated successfully!")
        final_content = ai_result
    else:
        print("AI update unavailable or malformed. Using structured deterministic log update...")
        final_content = fallback_append_log(docs_content, diff_stat, current_sha)

    with open(DOCS_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(final_content)

    print(f"PROJECT_DOCS.md successfully updated to commit {current_sha}!")


if __name__ == "__main__":
    main()
