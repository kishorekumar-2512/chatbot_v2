"""
mcp_servers/database_server.py

MCP server exposing database operations as tools:
  - run_query(sql)         → execute a validated SELECT, return rows
  - get_schema(tables)     → return DDL text for given table names
  - list_tables()          → return all table names in the public schema

Run standalone for testing:
    python mcp_servers/database_server.py

In production this is launched as a subprocess by the MCP host (your
FastAPI backend) over stdio, per the MCP spec.
"""

import os
import json

import psycopg2
import psycopg2.extras
import psycopg2.pool
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

server = Server("database-mcp-server")

# Previously this opened (and left FastAPI to close) a brand-new TCP + auth
# connection on EVERY tool call. build_value_hints() alone could fire off a
# few dozen of these sequentially per question — each one paying the full
# connection setup cost. A small pool reused across calls removes that
# entirely for the life of the MCP server subprocess.
_pool = psycopg2.pool.ThreadedConnectionPool(1, 10, DATABASE_URL)


class _PooledConnection:
    """Context manager that borrows/returns a connection from the pool."""
    def __enter__(self):
        self.conn = _pool.getconn()
        self.conn.cursor_factory = psycopg2.extras.RealDictCursor
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            try:
                self.conn.rollback()
            except Exception:
                pass
        _pool.putconn(self.conn)


def _get_connection():
    return _PooledConnection()


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="run_query",
            description="Execute a read-only SQL SELECT query against the PostgreSQL database and return the resulting rows as JSON. Only SELECT statements are permitted.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "A valid PostgreSQL SELECT statement."}
                },
                "required": ["sql"],
            },
        ),
        Tool(
            name="get_schema",
            description="Return the DDL-like column definitions for one or more specific tables.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of table names to fetch schema for.",
                    }
                },
                "required": ["tables"],
            },
        ),
        Tool(
            name="list_tables",
            description="List all table names available in the public schema of the database.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "run_query":
        sql = arguments["sql"].strip()
        if not sql.upper().startswith("SELECT"):
            return [TextContent(type="text", text=json.dumps({"error": "Only SELECT statements are allowed."}))]
        try:
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    # Hard limit to 1000 rows to prevent OOM/crashing on massive production tables
                    rows = [dict(r) for r in cur.fetchmany(1000)]
                    has_more = cur.fetchone() is not None
                    
            response_data = {"rows": rows, "row_count": len(rows), "has_more": has_more}
            return [TextContent(type="text", text=json.dumps(response_data, default=str))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    elif name == "get_schema":
        tables = arguments.get("tables", [])
        try:
            ddls = []
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    for table in tables:
                        cur.execute("""
                            SELECT column_name, data_type FROM information_schema.columns
                            WHERE table_schema = 'public' AND table_name = %s
                            ORDER BY ordinal_position;
                        """, (table,))
                        cols = cur.fetchall()
                        col_str = ", ".join(f"{c['column_name']} {c['data_type']}" for c in cols)
                        ddls.append(f"Table {table} ({col_str})")
            return [TextContent(type="text", text=json.dumps({"schema": "\n".join(ddls)}))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    elif name == "list_tables":
        try:
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT table_name FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                        ORDER BY table_name;
                    """)
                    tables = [r["table_name"] for r in cur.fetchall()]
            return [TextContent(type="text", text=json.dumps({"tables": tables}))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
