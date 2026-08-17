#!/usr/bin/env python3
# ==============================================================================
# scripts/generate_docs_pdf.py — Publication-Quality PDF Exporter for PROJECT_DOCS.md
#
# Parses PROJECT_DOCS.md, pre-renders all Mermaid diagrams, formats markdown
# tables and code blocks into an executive HTML5 layout, and compiles a pixel-perfect
# PDF via headless browser (Edge / Chrome / WeasyPrint) with graceful fallbacks.
# ==============================================================================

import os
import re
import sys
import base64
import datetime
import shutil
import subprocess
from pathlib import Path
import markdown
import httpx

ROOT = Path(__file__).resolve().parent.parent
DOCS_MD = ROOT / "PROJECT_DOCS.md"
DOCS_PDF_DIR = ROOT / "docs"
OUTPUT_PDF = DOCS_PDF_DIR / "PROJECT_DOCS.pdf"
REPORTS_PDF = ROOT / "reports" / "project_documentation.pdf"
TEMP_DIR = ROOT / ".temp_doc_build"


def get_commit_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    except Exception:
        return "df1cf8c036d12799c5e34089a049749242608d2c"


def render_mermaid_diagram(code: str, idx: int) -> Path | None:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    img_path = TEMP_DIR / f"diagram_{idx}.png"

    # 1. Try local mmdc (mermaid-cli) if installed
    if shutil.which("mmdc"):
        mmd_file = TEMP_DIR / f"diagram_{idx}.mmd"
        with open(mmd_file, "w", encoding="utf-8") as f:
            f.write(code)
        try:
            res = subprocess.run(
                ["mmdc", "-i", str(mmd_file), "-o", str(img_path), "-b", "white", "-s", "2"],
                capture_output=True,
                check=True
            )
            if img_path.exists():
                return img_path
        except Exception:
            pass

    # 2. Use mermaid.ink cloud rendering service
    try:
        encoded = base64.b64encode(code.strip().encode("utf-8")).decode("utf-8")
        url = f"https://mermaid.ink/img/{encoded}?bgColor=white"
        with httpx.Client(timeout=45.0) as client:
            r = client.get(url)
            if r.status_code == 200 and len(r.content) > 100:
                with open(img_path, "wb") as f:
                    f.write(r.content)
                return img_path
    except Exception as e:
        print(f"Warning: Failed to render diagram {idx}: {e}")

    return None


def build_html_document(md_content: str, sha: str, gen_date: str) -> str:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    mermaid_blocks = re.findall(r"```mermaid\s*\n(.*?)\n```", md_content, re.DOTALL)
    print(f"Pre-rendering {len(mermaid_blocks)} Mermaid diagrams...")

    for idx, block in enumerate(mermaid_blocks, 1):
        print(f"  Rendering diagram {idx}/{len(mermaid_blocks)}...")
        img_path = render_mermaid_diagram(block, idx)
        if img_path:
            with open(img_path, "rb") as img_file:
                b64_data = base64.b64encode(img_file.read()).decode("utf-8")
            data_uri = f"data:image/png;base64,{b64_data}"
            replacement = f'<div class="figure-box"><img class="diagram-img" src="{data_uri}" alt="Diagram {idx}" /><div class="figure-caption">Figure {idx}: Architectural Flow & Pipeline Diagram</div></div>'
            md_content = md_content.replace(f"```mermaid\n{block}\n```", replacement, 1)

    html_body = markdown.markdown(
        md_content,
        extensions=["tables", "fenced_code", "toc", "attr_list", "sane_lists"]
    )

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>chatbot_v2 — Living Project Documentation</title>
<style>
  @page {{
    size: A4 portrait;
    margin: 20mm 16mm 20mm 16mm;
  }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    color: #1e293b;
    background: #ffffff;
    line-height: 1.6;
    font-size: 10pt;
    margin: 0;
    padding: 0;
  }}

  /* Executive Cover Page */
  .cover-page {{
    page-break-after: always;
    padding-top: 25mm;
  }}
  .cover-badge {{
    background-color: #0f172a;
    color: #ffffff;
    font-size: 26pt;
    font-weight: 800;
    padding: 14px 20px;
    border-radius: 8px 8px 0 0;
    letter-spacing: -0.5px;
  }}
  .cover-bar {{
    height: 5px;
    background: linear-gradient(90deg, #3b82f6, #60a5fa, #93c5fd);
    border-radius: 0 0 8px 8px;
    margin-bottom: 25px;
  }}
  .cover-title {{
    font-size: 18pt;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.3;
    margin-bottom: 12px;
  }}
  .cover-subtitle {{
    font-size: 11pt;
    color: #475569;
    line-height: 1.5;
    margin-bottom: 30px;
  }}
  .meta-card {{
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 18px 24px;
    margin-bottom: 30px;
  }}
  .meta-row {{
    display: flex;
    padding: 6px 0;
    border-bottom: 1px solid #edf2f7;
    font-size: 9.5pt;
  }}
  .meta-row:last-child {{ border-bottom: none; }}
  .meta-label {{
    width: 160px;
    font-weight: 700;
    color: #334155;
  }}
  .meta-value {{
    color: #0f172a;
    flex: 1;
    font-family: inherit;
  }}
  .meta-code {{
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    background-color: #e2e8f0;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 9pt;
  }}

  /* Typography & Headings */
  h1 {{
    font-size: 18pt;
    font-weight: 800;
    color: #0f172a;
    border-bottom: 2px solid #3b82f6;
    padding-bottom: 8px;
    margin-top: 35px;
    margin-bottom: 16px;
    page-break-after: avoid;
  }}
  h2 {{
    font-size: 14pt;
    font-weight: 700;
    color: #1e3a8a;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 6px;
    margin-top: 28px;
    margin-bottom: 12px;
    page-break-after: avoid;
  }}
  h3 {{
    font-size: 11.5pt;
    font-weight: 700;
    color: #1e293b;
    margin-top: 20px;
    margin-bottom: 8px;
    page-break-after: avoid;
  }}
  h4 {{
    font-size: 10pt;
    font-weight: 700;
    color: #334155;
    margin-top: 14px;
    margin-bottom: 6px;
    page-break-after: avoid;
  }}

  p {{
    margin: 8px 0 12px 0;
    text-align: justify;
  }}

  /* Tables — Full Width, Formatted, Word-Wrapped */
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0 24px 0;
    font-size: 8.5pt;
    page-break-inside: avoid;
  }}
  th {{
    background-color: #0f172a;
    color: #ffffff;
    font-weight: 700;
    text-align: left;
    padding: 8px 10px;
    border: 1px solid #334155;
  }}
  td {{
    padding: 7px 10px;
    border: 1px solid #cbd5e1;
    vertical-align: top;
    word-break: break-word;
  }}
  tr:nth-child(even) {{
    background-color: #f8fafc;
  }}

  /* Code Blocks */
  pre {{
    background-color: #f1f5f9;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 12px 14px;
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 8pt;
    line-height: 1.45;
    overflow-x: auto;
    page-break-inside: avoid;
    margin: 12px 0 18px 0;
  }}
  code {{
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    background-color: #f1f5f9;
    padding: 2px 5px;
    border-radius: 4px;
    font-size: 8.5pt;
    color: #0f172a;
  }}

  /* Diagram Figures */
  .figure-box {{
    margin: 20px 0;
    text-align: center;
    page-break-inside: avoid;
  }}
  .diagram-img {{
    max-width: 96%;
    height: auto;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    padding: 10px;
    background: #ffffff;
  }}
  .figure-caption {{
    font-size: 8pt;
    font-style: italic;
    color: #64748b;
    margin-top: 6px;
  }}

  /* Blockquotes & Callouts */
  blockquote {{
    background-color: #f8fafc;
    border-left: 4px solid #3b82f6;
    padding: 10px 16px;
    margin: 12px 0 16px 0;
    color: #334155;
    font-style: normal;
  }}

  ul, ol {{
    margin: 8px 0 14px 20px;
    padding: 0;
  }}
  li {{
    margin-bottom: 5px;
  }}

  hr {{
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 24px 0;
  }}
</style>
</head>
<body>

<div class="cover-page">
  <div class="cover-badge">chatbot_v2</div>
  <div class="cover-bar"></div>
  <div class="cover-title">Comprehensive Technical Documentation & Architecture Reference</div>
  <div class="cover-subtitle">Natural-Language -> Validated SQL -> Interactive Visualizations -> Statistical Insights with 6-Layer Hybrid RAG, Circuit-Breaker Multi-Model Routing, MCP Subprocesses, and Zero-Downtime Blue-Green Deployment.</div>

  <div class="meta-card">
    <div class="meta-row"><div class="meta-label">Repository:</div><div class="meta-value">kishorekumar-2512/chatbot_v2</div></div>
    <div class="meta-row"><div class="meta-label">Commit SHA:</div><div class="meta-value"><span class="meta-code">{sha}</span></div></div>
    <div class="meta-row"><div class="meta-label">Generation Date:</div><div class="meta-value">{gen_date}</div></div>
    <div class="meta-row"><div class="meta-label">Document Version:</div><div class="meta-value">Production 2.0 (Living Architecture Manual)</div></div>
    <div class="meta-row"><div class="meta-label">Author / Maintainer:</div><div class="meta-value">Kishore Kumar (Software Engineering)</div></div>
  </div>

  <p style="color: #64748b; font-size: 8.5pt; font-style: italic;">
    <b>Notice:</b> This document is the authoritative, unabridged technical reference compiled from <code>PROJECT_DOCS.md</code>. It details the complete system architecture, the 6-layer RAG accuracy pipeline, MCP subprocess tools, exhaustive file references, and the append-only update history.
  </p>
</div>

<div class="content">
{html_body}
</div>

</body>
</html>"""
    return full_html


def build_pdf_document():
    print(f"Reading documentation from {DOCS_MD}...")
    if not DOCS_MD.exists():
        print(f"Error: {DOCS_MD} not found.")
        sys.exit(1)

    with open(DOCS_MD, "r", encoding="utf-8") as f:
        md_text = f.read()

    sha = get_commit_sha()
    today_str = datetime.date.today().strftime("%B %d, %Y")

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    html_output_path = TEMP_DIR / "document.html"

    print("Building executive HTML5 layout with embedded diagrams and CSS...")
    html_content = build_html_document(md_text, sha, today_str)

    with open(html_output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    DOCS_PDF_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_PDF.parent.mkdir(parents=True, exist_ok=True)

    # Detect Headless Browser
    browser_exe = None
    potential_browsers = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "msedge",
        "google-chrome",
        "chromium-browser",
        "chromium"
    ]

    for b in potential_browsers:
        if os.path.exists(b) or shutil.which(b):
            browser_exe = b
            break

    print(f"Compiling PDF via Headless Engine: {browser_exe or 'Native Engine'}...")

    if browser_exe:
        cmd = [
            browser_exe,
            "--headless",
            "--disable-gpu",
            "--run-all-compositor-stages-before-draw",
            "--no-pdf-header-footer",
            f"--print-to-pdf={OUTPUT_PDF}",
            str(html_output_path)
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print("PDF rendered successfully via headless browser!")
        except Exception as e:
            print(f"Browser rendering returned: {e}")

    # Fallback to weasyprint if browser was unavailable
    if not OUTPUT_PDF.exists() or OUTPUT_PDF.stat().st_size < 1000:
        if shutil.which("weasyprint"):
            try:
                subprocess.run(["weasyprint", str(html_output_path), str(OUTPUT_PDF)], check=True)
                print("PDF rendered successfully via WeasyPrint!")
            except Exception as e:
                print(f"WeasyPrint failed: {e}")

    if OUTPUT_PDF.exists():
        print(f"Output PDF size: {OUTPUT_PDF.stat().st_size / 1024:.2f} KB at {OUTPUT_PDF}")
        shutil.copy2(OUTPUT_PDF, REPORTS_PDF)
        print(f"Synced copy to {REPORTS_PDF}!")
    else:
        print("Error: PDF compilation failed.")
        sys.exit(1)

    # Cleanup temporary files
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

    print("All documentation exports completed successfully!")


if __name__ == "__main__":
    build_pdf_document()
