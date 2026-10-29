"""MCP client backed by the official MCP Python SDK."""

from __future__ import annotations

import json
import logging
import os
import shlex
from contextlib import AsyncExitStack
from typing import Any

try:  # The MCP SDK is an optional extra: pip install researchclaw[mcp]
    from mcp import Client, StdioServerParameters
    from mcp.types import TextContent
except ImportError as _exc:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        "MCP support requires the 'mcp' extra: pip install researchclaw[mcp]"
    ) from _exc

logger = logging.getLogger(__name__)


class MCPClient:
    """Connect to an MCP server and invoke its tools.

    For subprocess servers pass a command line (for example
    ``"researchclaw mcp --start"``). For tests and in-process composition use
    :meth:`in_memory`.
    """

    def __init__(self, server: Any, transport: str = "stdio") -> None:
        self._target = None if isinstance(server, str) else server
        self.uri = server if isinstance(server, str) else "<in-memory>"
        self.transport = transport
        self._client: Client | None = None
        self._stack: AsyncExitStack | None = None
        self._connected = False
        self._tools_cache: list[dict[str, Any]] | None = None

    @classmethod
    def in_memory(cls, server: Any) -> MCPClient:
        """Wrap an in-process SDK ``MCPServer`` (no subprocess)."""
        return cls(server)

    # ── connection ────────────────────────────────────────────────

    async def connect(self) -> None:
        """Establish the MCP session (stdio subprocess or in-memory server)."""
        if self._connected:
            return
        if self._target is None:
            if self.transport != "stdio":
                raise NotImplementedError(
                    f"Transport {self.transport!r} is not implemented; use 'stdio'"
                )
            parts = shlex.split(self.uri, posix=os.name != "nt")
            if os.name == "nt":
                parts = [
                    part[1:-1]
                    if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'"
                    else part
                    for part in parts
                ]
            if not parts:
                raise ValueError("MCP server command is empty")
            target: Any = StdioServerParameters(
                command=parts[0],
                args=parts[1:],
                env=dict(os.environ),
            )
        else:
            target = self._target

        stack = AsyncExitStack()
        try:
            client = await stack.enter_async_context(Client(target))
        except Exception:
            await stack.aclose()
            raise
        self._stack = stack
        self._client = client
        self._connected = True
        logger.info("Connected to MCP server: %s", self.uri)

    async def disconnect(self) -> None:
        """Close the session and release transport resources."""
        if self._stack is not None:
            try:
                await self._stack.aclose()
            finally:
                self._stack = None
        self._client = None
        self._connected = False
        self._tools_cache = None
        logger.info("Disconnected from MCP server: %s", self.uri)

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── tool discovery ────────────────────────────────────────────

    async def list_tools(self) -> list[dict[str, Any]]:
        """List tools available on the remote MCP server."""
        if not self._connected or self._client is None:
            raise ConnectionError("Not connected to MCP server")
        if self._tools_cache is not None:
            return self._tools_cache

        result = await self._client.list_tools()
        tools = [
            tool.model_dump(by_alias=True, exclude_none=True)
            for tool in result.tools
        ]
        self._tools_cache = tools
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool and return its structured payload."""
        if not self._connected or self._client is None:
            raise ConnectionError("Not connected to MCP server")

        result = await self._client.call_tool(name, arguments)
        payload = result.structured_content
        if not isinstance(payload, dict):
            texts = [
                block.text
                for block in result.content
                if isinstance(block, TextContent)
            ]
            raw = "\n".join(texts)
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                parsed = raw
            payload = parsed if isinstance(parsed, dict) else {"content": parsed}
        payload = dict(payload)
        if result.is_error:
            payload.setdefault("success", False)
        return payload

    # ── resource access ───────────────────────────────────────────

    async def list_resources(self) -> list[dict[str, Any]]:
        """List resources available on the remote MCP server."""
        if not self._connected or self._client is None:
            raise ConnectionError("Not connected to MCP server")
        result = await self._client.list_resources()
        return [
            resource.model_dump(by_alias=True, exclude_none=True)
            for resource in result.resources
        ]

    async def read_resource(self, uri: str) -> str:
        """Read the first text resource returned for *uri*."""
        if not self._connected or self._client is None:
            raise ConnectionError("Not connected to MCP server")
        result = await self._client.read_resource(uri)
        for item in result.contents:
            text = getattr(item, "text", "")
            if text:
                return str(text)
        return ""
