"""Tests for MCP tools, client, registry, and transports."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")

from researchclaw.mcp.client import MCPClient
from researchclaw.mcp.registry import MCPServerRegistry
from researchclaw.mcp.server import ResearchClawMCPServer
from researchclaw.mcp.tools import TOOL_DEFINITIONS, get_tool_schema, list_tool_names
from researchclaw.mcp.transport import SSETransport


# ══════════════════════════════════════════════════════════════════
# MCP Tools tests
# ══════════════════════════════════════════════════════════════════


class TestMCPTools:
    def test_tool_definitions_not_empty(self) -> None:
        assert len(TOOL_DEFINITIONS) >= 6

    def test_all_tools_have_required_fields(self) -> None:
        for tool in TOOL_DEFINITIONS:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"

    def test_get_tool_schema_exists(self) -> None:
        schema = get_tool_schema("run_pipeline")
        assert schema is not None
        assert schema["name"] == "run_pipeline"

    def test_get_tool_schema_missing(self) -> None:
        assert get_tool_schema("nonexistent") is None

    def test_list_tool_names(self) -> None:
        names = list_tool_names()
        assert names == [
            "run_pipeline",
            "get_pipeline_status",
            "get_experiment_results",
            "search_literature",
            "review_paper",
            "get_paper",
        ]

    def test_run_pipeline_requires_topic(self) -> None:
        schema = get_tool_schema("run_pipeline")
        assert schema is not None
        assert "topic" in schema["inputSchema"]["required"]

    def test_review_paper_accepts_either_source(self) -> None:
        schema = get_tool_schema("review_paper")
        assert schema is not None
        assert schema["inputSchema"]["anyOf"] == [
            {"required": ["paper_path"]},
            {"required": ["run_id"]},
        ]

    def test_get_paper_has_format_enum(self) -> None:
        schema = get_tool_schema("get_paper")
        assert schema is not None
        props = schema["inputSchema"]["properties"]
        assert "enum" in props["format"]


# ══════════════════════════════════════════════════════════════════
# MCP Server tests
# ══════════════════════════════════════════════════════════════════


class TestMCPServer:
    def test_get_tools(self, tmp_path) -> None:
        server = ResearchClawMCPServer(artifacts_dir=tmp_path)
        tools = server.get_tools()
        assert len(tools) >= 6
        names = [tool["name"] for tool in tools]
        assert "run_pipeline" in names

    def test_handle_unknown_tool(self, tmp_path) -> None:
        server = ResearchClawMCPServer(artifacts_dir=tmp_path)
        result = asyncio.run(server.handle_tool_call("nonexistent", {}))
        assert result["success"] is False
        assert result["error_code"] == "INVALID_TOOL"

    def test_stop_marks_not_running(self, tmp_path) -> None:
        server = ResearchClawMCPServer(artifacts_dir=tmp_path)
        assert not server.is_running
        asyncio.run(server.stop())
        assert not server.is_running


# ══════════════════════════════════════════════════════════════════
# MCP Client tests
# ══════════════════════════════════════════════════════════════════


class TestMCPClient:
    def test_init(self) -> None:
        client = MCPClient("researchclaw mcp --start")
        assert client.uri == "researchclaw mcp --start"
        assert not client.is_connected

    def test_unsupported_transport(self) -> None:
        client = MCPClient("researchclaw mcp --start", transport="sse")
        with pytest.raises(NotImplementedError):
            asyncio.run(client.connect())

    def test_in_memory_list_and_call(self, tmp_path) -> None:
        server = ResearchClawMCPServer(artifacts_dir=tmp_path)
        client = MCPClient.in_memory(server.mcp)

        async def _run() -> list:
            await client.connect()
            tools = await client.list_tools()
            result = await client.call_tool(
                "get_pipeline_status", {"run_id": "rc-20260101-000000-abcdef"}
            )
            await client.disconnect()
            assert result["error_code"] == "RUN_NOT_FOUND"
            return tools

        tools = asyncio.run(_run())
        assert len(tools) == 6
        assert not client.is_connected

    def test_tools_cached(self, tmp_path) -> None:
        server = ResearchClawMCPServer(artifacts_dir=tmp_path)
        client = MCPClient.in_memory(server.mcp)

        async def _run() -> tuple:
            await client.connect()
            first = await client.list_tools()
            second = await client.list_tools()
            await client.disconnect()
            return first, second

        first, second = asyncio.run(_run())
        assert first is second

    def test_not_connected(self) -> None:
        client = MCPClient("researchclaw mcp --start")
        with pytest.raises(ConnectionError):
            asyncio.run(client.list_tools())
        with pytest.raises(ConnectionError):
            asyncio.run(client.call_tool("get_paper", {}))


# ══════════════════════════════════════════════════════════════════
# MCP Server Registry tests
# ══════════════════════════════════════════════════════════════════


class TestMCPServerRegistry:
    def test_register_and_list(self, tmp_path) -> None:
        server = ResearchClawMCPServer(artifacts_dir=tmp_path)

        async def _run() -> list:
            reg = MCPServerRegistry()
            await reg.register("local", server.mcp)
            return reg.list_all()

        servers = asyncio.run(_run())
        assert len(servers) == 1
        assert servers[0]["name"] == "local"
        assert servers[0]["connected"] is True

    def test_unregister(self, tmp_path) -> None:
        server = ResearchClawMCPServer(artifacts_dir=tmp_path)

        async def _run() -> int:
            reg = MCPServerRegistry()
            await reg.register("local", server.mcp)
            await reg.unregister("local")
            return reg.count

        assert asyncio.run(_run()) == 0

    def test_get(self, tmp_path) -> None:
        server = ResearchClawMCPServer(artifacts_dir=tmp_path)

        async def _run() -> MCPClient | None:
            reg = MCPServerRegistry()
            await reg.register("local", server.mcp)
            return reg.get("local")

        client = asyncio.run(_run())
        assert client is not None
        assert client.is_connected

    def test_get_missing(self) -> None:
        reg = MCPServerRegistry()
        assert reg.get("nonexistent") is None

    def test_close_all(self, tmp_path) -> None:
        server_a = ResearchClawMCPServer(artifacts_dir=tmp_path)
        server_b = ResearchClawMCPServer(artifacts_dir=tmp_path)

        async def _run() -> int:
            reg = MCPServerRegistry()
            await reg.register("a", server_a.mcp)
            await reg.register("b", server_b.mcp)
            await reg.close_all()
            return reg.count

        assert asyncio.run(_run()) == 0


# ══════════════════════════════════════════════════════════════════
# Transport tests
# ══════════════════════════════════════════════════════════════════


class TestSSETransport:
    def test_start_stop(self) -> None:
        transport = SSETransport(port=9999)

        async def _run() -> None:
            await transport.start()
            assert transport._running is True
            await transport.close()
            assert transport._running is False

        asyncio.run(_run())

    def test_receive_not_implemented(self) -> None:
        transport = SSETransport()
        with pytest.raises(NotImplementedError):
            asyncio.run(transport.receive())
