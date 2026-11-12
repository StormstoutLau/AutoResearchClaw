"""G4-M2 (P-103): dynamic registration, listChanged seam and GET /api/tools (A4-10)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from researchclaw.mcp.registry_adapter import (
    register_from_registry,
    refresh_from_registry,
)
from researchclaw.tools.registry import RegistryError, load_registry

pytest.importorskip("mcp")
from mcp.server import MCPServer  # noqa: E402


def _make_registry(tmp_path: Path, extra_tools: list[dict] | None = None) -> Path:
    payload = {
        "version": 1,
        "tools": [
            {
                "name": "probe_a",
                "version": "1.0",
                "description": "Probe A",
                "inputSchema": {"type": "object", "properties": {
                    "topic": {"type": "string", "description": "t"}},
                    "required": ["topic"]},
                "outputSchema": {"type": "object"},
                "scope": "global",
                "risk": "low",
                "approval": "never",
                "sandbox_profile": "default",
                "handler": "tests.test_mcp_dynamic_tools:HANDLER_OK",
            },
            {
                "name": "probe_b",
                "version": "1.0",
                "description": "Probe B",
                "inputSchema": {"type": "object", "properties": {
                    "run_id": {"type": "string", "description": "rid"}},
                    "required": ["run_id"],
                    "anyOf": [{"required": ["run_id"]}]},
                "scope": "run",
                "risk": "low",
                "approval": "never",
                "sandbox_profile": "default",
                "handler": "tests.test_mcp_dynamic_tools:HANDLER_OK",
            },
        ],
        "sandbox_profiles": {
            "default": {"network": "none", "cpu": 2, "memory": "4g",
                        "pids": 512, "disk": "10g", "ttl_sec": 1800},
        },
    }
    if extra_tools:
        payload["tools"].extend(extra_tools)
    path = tmp_path / "registry.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return path


async def HANDLER_OK(**kwargs):  # noqa: ANN001, ANN003
    return {"ok": True, "args": kwargs}


def _dispatcher(calls: list):
    async def _dispatch(name: str, args: dict):
        calls.append((name, args))
        return {"dispatched": name}
    return _dispatch


# ── T-1/T-2/T-4: dynamic registration ────────────────────────────


def test_register_from_registry_lists_tools(tmp_path: Path) -> None:
    import asyncio

    server = MCPServer(name="t", version="0")
    registry = load_registry(_make_registry(tmp_path), strict_handlers=True)
    registered = register_from_registry(server, registry,
                                        _dispatcher([]))
    assert set(registered) == {"probe_a", "probe_b"}
    listed = {t.name for t in asyncio.run(server.list_tools())}
    assert set(listed) >= {"probe_a", "probe_b"}


def test_injected_schema_matches_registry(tmp_path: Path) -> None:
    # A4-10 first half: list_tools() inputSchema == registry schema (deep).
    import asyncio

    from researchclaw.tools.registry import unfreeze

    server = MCPServer(name="t", version="0")
    registry = load_registry(_make_registry(tmp_path), strict_handlers=True)
    register_from_registry(server, registry, _dispatcher([]))
    for spec in registry.tools:
        tool = server._tool_manager.get_tool(spec.name)
        assert tool is not None
        assert json.loads(json.dumps(tool.parameters)) == json.loads(
            json.dumps(unfreeze(spec.input_schema)))
        assert spec.name in {t.name for t in asyncio.run(server.list_tools())}


def test_no_hardcoded_tool_names_in_adapter() -> None:
    # T-4: adapter must not contain any tool-name literals.
    source = (Path(__file__).resolve().parents[1]
              / "researchclaw" / "mcp" / "registry_adapter.py").read_text(encoding="utf-8")
    for forbidden in ("run_pipeline", "get_paper", "probe_a", "probe_b"):
        assert forbidden not in source, forbidden


# ── T-3: new tool without code change ────────────────────────────


def test_new_registry_entry_appears_without_code_change(tmp_path: Path) -> None:
    import asyncio

    server = MCPServer(name="t", version="0")
    path = _make_registry(tmp_path)
    registry = load_registry(path, strict_handlers=True)
    register_from_registry(server, registry, _dispatcher([]))
    before = {t.name for t in asyncio.run(server.list_tools())}
    assert "probe_new" not in before

    extra = [{
        "name": "probe_new",
        "version": "1.0",
        "description": "Added via registry only",
        "inputSchema": {"type": "object", "properties": {}},
        "scope": "global",
        "risk": "low",
        "approval": "never",
        "sandbox_profile": "default",
        "handler": "tests.test_mcp_dynamic_tools:HANDLER_OK",
    }]
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["tools"].extend(extra)
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    calls: list = []
    new_registry = refresh_from_registry(server, registry, _dispatcher(calls),
                                         notifier=None, path=path)
    listed = {t.name for t in asyncio.run(server.list_tools())}
    assert "probe_new" in listed
    assert {"probe_a", "probe_b"} <= listed
    assert new_registry.get("probe_new") is not None


# ── T-5: reload notification seam ────────────────────────────────


def test_reload_notifier_called_once(tmp_path: Path) -> None:
    server = MCPServer(name="t", version="0")
    path = _make_registry(tmp_path)
    registry = load_registry(path, strict_handlers=True)
    register_from_registry(server, registry, _dispatcher([]))

    fired: list[int] = []
    new_registry = refresh_from_registry(server, registry, _dispatcher([]),
                                         notifier=lambda: fired.append(1), path=path)
    assert fired == [1]
    assert new_registry.version == 1


def test_reload_failure_keeps_registration(tmp_path: Path) -> None:
    import asyncio

    server = MCPServer(name="t", version="0")
    path = _make_registry(tmp_path)
    registry = load_registry(path, strict_handlers=True)
    register_from_registry(server, registry, _dispatcher([]))
    path.write_text("version: 9\n", encoding="utf-8")
    with pytest.raises(RegistryError):
        refresh_from_registry(server, registry, _dispatcher([]), path=path)
    assert {t.name for t in asyncio.run(server.list_tools())} >= {"probe_a", "probe_b"}


# ── dispatcher wiring ────────────────────────────────────────────


def test_dispatcher_receives_name_and_args(tmp_path: Path) -> None:
    import asyncio
    import json as _json

    server = MCPServer(name="t", version="0")
    calls: list = []
    registry = load_registry(_make_registry(tmp_path), strict_handlers=True)
    register_from_registry(server, registry, _dispatcher(calls))
    result = asyncio.run(server.call_tool("probe_a", {"topic": "x"}))
    assert calls and calls[0][0] == "probe_a"
    text = result.content[0].text
    assert _json.loads(text)["dispatched"] == "probe_a"


# ── T-R4 follow-up: registry used by adapter is V-8 checked ──────


def test_adapter_rejects_invalid_registry(tmp_path: Path) -> None:
    server = MCPServer(name="t", version="0")
    path = _make_registry(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["tools"][0]["risk"] = "high"
    payload["tools"][0]["approval"] = "never"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(RegistryError):
        load_registry(path, strict_handlers=True)


# ── T-6: GET /api/tools field whitelist ──────────────────────────


def test_api_tools_whitelist(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from researchclaw.server.routes import tools as tools_module

    monkeypatch.setenv("RC_TOOL_REGISTRY", str(_make_registry(tmp_path)))
    tools_module.REGISTRY = None  # reset lazy cache; get_registry re-loads
    app = FastAPI()
    app.include_router(tools_module.router)
    client = TestClient(app)
    resp = client.get("/api/tools")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["version"] == 1
    names = {t["name"] for t in payload["tools"]}
    assert names == {"probe_a", "probe_b"}
    for entry in payload["tools"]:
        assert "inputSchema" in entry
        assert "handler" not in entry
        assert "sandbox_profile" not in entry


def test_api_tools_fail_closed_on_bad_registry(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    bad = tmp_path / "bad.yaml"
    bad.write_text("version: 9\n", encoding="utf-8")
    monkeypatch.setenv("RC_TOOL_REGISTRY", str(bad))

    from researchclaw.server.routes import tools as tools_module

    tools_module.REGISTRY = None  # reset lazy cache
    app = FastAPI()
    app.include_router(tools_module.router)
    client = TestClient(app, raise_server_exceptions=True)
    with pytest.raises(RegistryError):
        client.get("/api/tools")
