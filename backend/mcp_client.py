"""
backend/mcp_client.py

MCP HOST. Manages MCP server subprocess connections.
Per the MCP spec, the host launches each MCP server as a subprocess and talks
to it over stdio using JSON-RPC.

Two servers are launched on startup and kept alive for the life of the FastAPI process:
  - database-mcp-server  (run_query, get_schema, list_tables)
  - schema-mcp-server     (search_tables, get_columns, get_relations)
"""

import os
import sys
import json
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RowList(list):
    def __init__(self, iterable, total_count=0, has_more=False):
        super().__init__(iterable)
        self.total_count = total_count
        self.has_more = has_more


class MCPHost:
    """
    Manages MCP server subprocess connections.
    Call `await host.start()` once at FastAPI startup, `await host.stop()` at shutdown.
    """

    def __init__(self):
        self._stack: AsyncExitStack | None = None
        self.database_session: ClientSession | None = None
        self.schema_session: ClientSession | None = None

    async def start(self):
        self._stack = AsyncExitStack()

        self.database_session = await self._launch(
            os.path.join(BASE_DIR, "mcp_servers", "database_server.py")
        )
        self.schema_session = await self._launch(
            os.path.join(BASE_DIR, "mcp_servers", "schema_server.py")
        )

    async def _launch(self, script_path: str) -> ClientSession:
        params = StdioServerParameters(command=sys.executable, args=[script_path], env=os.environ.copy())
        read, write = await self._stack.enter_async_context(stdio_client(params))
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        return session

    async def stop(self):
        if self._stack:
            await self._stack.aclose()

    # ── Convenience wrappers used by main.py ───────────────────────────────

    async def list_tables(self) -> list[str]:
        result = await self.database_session.call_tool("list_tables", {})
        data = json.loads(result.content[0].text)
        return data.get("tables", [])

    async def get_schema(self, tables: list[str]) -> str:
        result = await self.database_session.call_tool("get_schema", {"tables": tables})
        data = json.loads(result.content[0].text)
        return data.get("schema", "")

    async def run_query(self, sql: str) -> list[dict]:
        result = await self.database_session.call_tool("run_query", {"sql": sql})
        data = json.loads(result.content[0].text)
        if "error" in data:
            raise ValueError(data["error"])
        rows = data.get("rows", [])
        total_count = data.get("total_count", len(rows))
        has_more = data.get("has_more", False)
        return RowList(rows, total_count=total_count, has_more=has_more)

    async def search_tables(self, question: str, top_k: int = 8) -> dict:
        result = await self.schema_session.call_tool("search_tables", {"question": question, "top_k": top_k})
        return json.loads(result.content[0].text)

    async def get_columns(self, table: str) -> list[dict]:
        result = await self.schema_session.call_tool("get_columns", {"table": table})
        data = json.loads(result.content[0].text)
        return data.get("columns", [])

    async def get_relations(self, table: str) -> list[dict]:
        result = await self.schema_session.call_tool("get_relations", {"table": table})
        data = json.loads(result.content[0].text)
        return data.get("relations", [])


# Module-level singleton — created on FastAPI startup, reused across requests
host = MCPHost()
