"""
mcp_servers/schema_server.py

MCP server exposing schema-intelligence operations as tools:
  - search_tables(question)  → semantic search over table embeddings (ChromaDB)
  - get_columns(table)       → column names + types for one table
  - get_relations(table)     → heuristic foreign-key relationships for one table

Run standalone for testing:
    python mcp_servers/schema_server.py
"""

import os
import sys
import json

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Reuse the retrieval module built for semantic search
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    from embeddings.retrieve import retrieve_relevant_tables, is_index_ready
except ImportError:
    def is_index_ready(): return False
    def retrieve_relevant_tables(*a, **kw): return {"error": "Embeddings/ChromaDB module not installed on this system."}

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

server = Server("schema-mcp-server")


def _get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_tables",
            description="Semantically search for the most relevant tables given a natural-language question. Uses local sentence-transformer embeddings against a ChromaDB index. Returns the top-K matching tables with similarity scores.",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The user's natural-language question."},
                    "top_k": {"type": "integer", "description": "Number of tables to return.", "default": 8},
                },
                "required": ["question"],
            },
        ),
        Tool(
            name="get_columns",
            description="Return the column names and data types for a single table.",
            inputSchema={
                "type": "object",
                "properties": {"table": {"type": "string"}},
                "required": ["table"],
            },
        ),
        Tool(
            name="get_relations",
            description="Return heuristic foreign-key relationships for a table, based on columns ending in '_id'.",
            inputSchema={
                "type": "object",
                "properties": {"table": {"type": "string"}},
                "required": ["table"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "search_tables":
        if not is_index_ready():
            return [TextContent(type="text", text=json.dumps({
                "error": "ChromaDB index not built yet. Run `python embeddings/build_index.py` first."
            }))]
        question = arguments["question"]
        top_k = arguments.get("top_k", 8)
        result = retrieve_relevant_tables(question, top_k=top_k)
        return [TextContent(type="text", text=json.dumps(result))]

    elif name == "get_columns":
        table = arguments["table"]
        try:
            conn = _get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name, data_type FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    ORDER BY ordinal_position;
                """, (table,))
                cols = [dict(r) for r in cur.fetchall()]
            conn.close()
            return [TextContent(type="text", text=json.dumps({"table": table, "columns": cols}))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    elif name == "get_relations":
        table = arguments["table"]
        try:
            conn = _get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    ORDER BY ordinal_position;
                """, (table,))
                cols = [r["column_name"] for r in cur.fetchall()]
            conn.close()
            fk_cols = [c for c in cols if c.endswith("_id") and c != "id"]
            # Heuristic: foo_id likely references table "foo" (singular guess)
            relations = [{"column": c, "likely_references_table": c[:-3]} for c in fk_cols]
            return [TextContent(type="text", text=json.dumps({"table": table, "relations": relations}))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
