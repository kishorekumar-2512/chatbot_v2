"""
mcp_servers/report_server.py

MCP server exposing report-generation operations as tools:
  - generate_pdf(question, sql, rows) → builds a PDF report, returns file path
  - make_chart(rows)                  → builds a Plotly chart, returns chart JSON
  - export_csv(rows)                  → builds a CSV file, returns file path

Run standalone for testing:
    python mcp_servers/report_server.py
"""

import os
import json
import csv

import pandas as pd
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("report-mcp-server")

REPORTS_DIR = os.getenv("REPORTS_DIR", "./reports")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="generate_pdf",
            description="Generate a PDF report containing the question, generated SQL, and a data table. Returns the file path of the created PDF.",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "sql": {"type": "string"},
                    "rows": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["question", "sql", "rows"],
            },
        ),
        Tool(
            name="make_chart",
            description="Build a Plotly bar chart from 2-column tabular data (label + numeric value). Returns the chart as Plotly JSON.",
            inputSchema={
                "type": "object",
                "properties": {
                    "rows": {"type": "array", "items": {"type": "object"}},
                    "title": {"type": "string"},
                },
                "required": ["rows"],
            },
        ),
        Tool(
            name="export_csv",
            description="Export tabular row data to a CSV file on disk. Returns the file path.",
            inputSchema={
                "type": "object",
                "properties": {"rows": {"type": "array", "items": {"type": "object"}}},
                "required": ["rows"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    os.makedirs(REPORTS_DIR, exist_ok=True)

    if name == "generate_pdf":
        from fpdf import FPDF

        question = arguments["question"]
        sql      = arguments["sql"]
        rows     = arguments["rows"]

        path = os.path.join(REPORTS_DIR, "report.pdf")
        pdf = FPDF()
        pdf.set_margins(15, 15, 15)
        
        # Determine orientation based on column count
        is_landscape = rows and len(rows[0]) > 4
        pdf.add_page(orientation="L" if is_landscape else "P")
        pdf.set_auto_page_break(auto=True, margin=15)
        usable_w = pdf.w - pdf.l_margin - pdf.r_margin

        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "Data Report", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(4)

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, "Question:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, question)
        pdf.ln(3)

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, "Generated SQL:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Courier", "", 9)
        pdf.set_fill_color(240, 240, 240)
        pdf.multi_cell(0, 5, sql, fill=True)
        pdf.ln(3)

        if rows:
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 8, "Data:", new_x="LMARGIN", new_y="NEXT")
            df = pd.DataFrame(rows)
            headers = list(df.columns)
            
            # Dynamic font size based on column count
            font_size = 9 if len(headers) <= 6 else (7 if len(headers) <= 10 else 5)
            
            # Calculate proportional widths based on content
            col_max_lens = {}
            for h in headers:
                # Find max length of header vs data strings (limit to first 200 rows to be safe)
                max_data_len = df[h].head(200).astype(str).str.len().max() if not df.empty else 0
                col_max_lens[h] = max(len(str(h)), min(max_data_len, 40)) # Cap extreme lengths
                
            total_len = sum(col_max_lens.values())
            col_widths = {h: max(10, (col_max_lens[h] / max(total_len, 1)) * usable_w) for h in headers}

            pdf.set_font("Helvetica", "B", font_size)
            pdf.set_fill_color(50, 50, 50)
            pdf.set_text_color(255, 255, 255)
            for h in headers:
                # Estimate how many characters fit in the column width (avg 1.5-2 width per char depending on font)
                max_chars = max(3, int(col_widths[h] / (font_size * 0.25)))
                pdf.cell(col_widths[h], 7, str(h)[:max_chars], border=1, fill=True)
            pdf.ln()
            
            pdf.set_font("Helvetica", "", font_size)
            pdf.set_text_color(0, 0, 0)
            for i, (_, row) in enumerate(df.iterrows()):
                if i >= 200:
                    break
                for h in headers:
                    max_chars = max(3, int(col_widths[h] / (font_size * 0.25)))
                    pdf.cell(col_widths[h], 6, str(row[h])[:max_chars], border=1)
                pdf.ln()

        pdf.output(path)
        return [TextContent(type="text", text=json.dumps({"pdf_path": path}))]

    elif name == "make_chart":
        rows  = arguments["rows"]
        title = arguments.get("title", "Chart")
        if not rows or len(rows[0]) != 2:
            return [TextContent(type="text", text=json.dumps({"error": "Chart requires exactly 2-column rows."}))]
        try:
            import plotly.express as px
            df = pd.DataFrame(rows)
            keys = list(df.columns)
            if not pd.api.types.is_numeric_dtype(df[keys[1]]):
                return [TextContent(type="text", text=json.dumps({"error": "Second column must be numeric."}))]
            fig = px.bar(df, x=keys[0], y=keys[1], title=title)
            return [TextContent(type="text", text=fig.to_json())]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    elif name == "export_csv":
        rows = arguments["rows"]
        path = os.path.join(REPORTS_DIR, "export.csv")
        if rows:
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
        return [TextContent(type="text", text=json.dumps({"csv_path": path}))]

    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
