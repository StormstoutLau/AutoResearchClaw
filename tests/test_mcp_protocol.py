"""Contract tests for the official-SDK MCP server (MCP-01 .. MCP-12)."""

from __future__ import annotations

import asyncio
import json
import re
import threading
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from researchclaw.config import RCConfig
from researchclaw.literature.models import Author, Paper
from researchclaw.mcp.client import MCPClient
from researchclaw.mcp.server import ResearchClawMCPServer
from researchclaw.mcp.tools import TOOL_DEFINITIONS
from researchclaw.pipeline.review_service import ReviewResult

RUN_ID = "rc-20260101-000000-abcdef"
_RUN_ID_RE = re.compile(r"^rc-\d{8}-\d{6}-[a-f0-9]{6}$")


def _config(tmp_path: Path) -> RCConfig:
    return RCConfig.from_dict(
        {
            "project": {"name": "mcp-test"},
            "research": {"topic": "test topic"},
            "runtime": {"timezone": "UTC"},
            "notifications": {"channel": "console"},
            "knowledge_base": {"root": str(tmp_path / "kb")},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:1",
                "api_key_env": "MCP_TEST_KEY",
            },
        },
        check_paths=False,
    )


def _make_run(artifacts: Path, *, stage: int = 12, name: str = "EXPERIMENT_RUN") -> Path:
    run_dir = artifacts / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "checkpoint.json").write_text(
        json.dumps(
            {
                "last_completed_stage": stage,
                "last_completed_name": name,
                "run_id": RUN_ID,
                "timestamp": "2026-10-29T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "heartbeat.json").write_text(
        json.dumps(
            {
                "pid": 1,
                "last_stage": stage,
                "last_stage_name": name,
                "run_id": RUN_ID,
                "timestamp": "2026-10-29T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def _call(server: ResearchClawMCPServer, name: str, arguments: dict) -> dict:
    async def _run() -> dict:
        client = MCPClient.in_memory(server.mcp)
        await client.connect()
        try:
            return await client.call_tool(name, arguments)
        finally:
            await client.disconnect()

    return asyncio.run(_run())


# ── MCP-01 / MCP-02: tools/list ───────────────────────────────────


def test_list_tools_matches_definitions(tmp_path: Path) -> None:
    server = ResearchClawMCPServer(artifacts_dir=tmp_path)

    async def _run() -> list:
        client = MCPClient.in_memory(server.mcp)
        await client.connect()
        try:
            return await client.list_tools()
        finally:
            await client.disconnect()

    tools = asyncio.run(_run())
    assert [tool["name"] for tool in tools] == [tool["name"] for tool in TOOL_DEFINITIONS]

    by_name = {tool["name"]: tool for tool in tools}
    for definition in TOOL_DEFINITIONS:
        schema = by_name[definition["name"]]["inputSchema"]
        expected = definition["inputSchema"]
        assert set(schema["properties"]) == set(expected["properties"])
        assert schema.get("required", []) == expected.get("required", [])


# ── MCP-03: unknown tool ─────────────────────────────────────────


def test_unknown_tool_is_error(tmp_path: Path) -> None:
    server = ResearchClawMCPServer(artifacts_dir=tmp_path)
    result = _call(server, "does_not_exist", {})
    assert result["success"] is False


# ── MCP-04 / MCP-05: run_pipeline ────────────────────────────────


def test_run_pipeline_returns_real_run_id(tmp_path: Path) -> None:
    release = threading.Event()
    executed: list[dict] = []

    def fake_execute(**kwargs) -> None:
        executed.append(kwargs)
        release.wait(2)
        run_dir = kwargs["run_dir"]
        (run_dir / "checkpoint.json").write_text(
            json.dumps({"last_completed_stage": 1, "last_completed_name": "TOPIC_INIT"}),
            encoding="utf-8",
        )

    server = ResearchClawMCPServer(
        config=_config(tmp_path),
        artifacts_dir=tmp_path / "artifacts",
        execute_pipeline_fn=fake_execute,
    )

    async def _run() -> tuple[dict, dict]:
        client = MCPClient.in_memory(server.mcp)
        await client.connect()
        try:
            first = await client.call_tool("run_pipeline", {"topic": "GNN"})
            second = await client.call_tool("run_pipeline", {"topic": "GNN"})
            return first, second
        finally:
            release.set()
            await asyncio.sleep(0.05)
            await server.stop()
            await client.disconnect()

    first, second = asyncio.run(_run())
    assert first["success"] is True
    assert _RUN_ID_RE.fullmatch(first["run_id"])
    assert first["status"] == "started"
    assert first["output_dir"].endswith(first["run_id"])
    assert second["success"] is False
    assert second["error_code"] == "RUN_IN_PROGRESS"
    assert (tmp_path / "artifacts" / first["run_id"]).is_dir()


def test_run_pipeline_requires_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("researchclaw.mcp.server.resolve_config_path", lambda _: None)
    server = ResearchClawMCPServer(artifacts_dir=tmp_path)
    result = _call(server, "run_pipeline", {"topic": "GNN"})
    assert result["success"] is False
    assert result["error_code"] == "CONFIG_REQUIRED"


# ── MCP-06: get_pipeline_status ──────────────────────────────────


def test_pipeline_status_reads_run_state(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    run_dir = _make_run(tmp_path)
    (run_dir / "heartbeat.json").write_text(
        json.dumps(
            {
                "pid": 1,
                "last_stage": 12,
                "last_stage_name": "EXPERIMENT_RUN",
                "run_id": RUN_ID,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        ),
        encoding="utf-8",
    )
    server = ResearchClawMCPServer(artifacts_dir=tmp_path)
    result = _call(server, "get_pipeline_status", {"run_id": RUN_ID})
    assert result["success"] is True
    assert result["stage"] == 12
    assert result["stage_name"] == "EXPERIMENT_RUN"
    assert result["is_active"] is True
    assert result["status"] == "running"


def test_pipeline_status_missing_run(tmp_path: Path) -> None:
    server = ResearchClawMCPServer(artifacts_dir=tmp_path)
    result = _call(server, "get_pipeline_status", {"run_id": RUN_ID})
    assert result["error_code"] == "RUN_NOT_FOUND"


# ── MCP-06b: get_experiment_results ──────────────────────────────


def test_experiment_results_stage14(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    stage14 = run_dir / "stage-14"
    stage14.mkdir()
    (stage14 / "experiment_summary.json").write_text(
        json.dumps(
            {
                "metrics_summary": {"accuracy": 0.9},
                "condition_summaries": {"control": {"accuracy": 0.8}},
            }
        ),
        encoding="utf-8",
    )
    server = ResearchClawMCPServer(artifacts_dir=tmp_path)
    result = _call(server, "get_experiment_results", {"run_id": RUN_ID})
    assert result["success"] is True
    assert result["stage"] == 14
    assert result["metrics"]["accuracy"] == 0.9
    assert result["source_path"] == "stage-14/experiment_summary.json"


def test_experiment_results_stage12_fallback(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    runs = run_dir / "stage-12" / "runs"
    runs.mkdir(parents=True)
    (runs / "results.json").write_text(
        json.dumps({"metrics": {"loss": 0.1}, "conditions": {"lr": 0.001}}),
        encoding="utf-8",
    )
    server = ResearchClawMCPServer(artifacts_dir=tmp_path)
    result = _call(server, "get_experiment_results", {"run_id": RUN_ID})
    assert result["stage"] == 12
    assert result["metrics"]["loss"] == 0.1


def test_experiment_results_missing(tmp_path: Path) -> None:
    _make_run(tmp_path)
    server = ResearchClawMCPServer(artifacts_dir=tmp_path)
    result = _call(server, "get_experiment_results", {"run_id": RUN_ID})
    assert result["error_code"] == "NO_RESULTS"


# ── MCP-07: get_paper ────────────────────────────────────────────


def test_get_paper_markdown_and_latex(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    stage22 = run_dir / "stage-22"
    stage22.mkdir()
    (stage22 / "paper_final.md").write_text("# Final paper", encoding="utf-8")
    (stage22 / "paper.tex").write_text("\\documentclass{article}", encoding="utf-8")

    server = ResearchClawMCPServer(artifacts_dir=tmp_path)
    markdown = _call(server, "get_paper", {"run_id": RUN_ID})
    latex = _call(server, "get_paper", {"run_id": RUN_ID, "format": "latex"})
    assert markdown["path"] == "stage-22/paper_final.md"
    assert markdown["content"] == "# Final paper"
    assert latex["path"] == "stage-22/paper.tex"
    assert latex["content"].startswith("\\documentclass")


def test_get_paper_missing(tmp_path: Path) -> None:
    _make_run(tmp_path)
    server = ResearchClawMCPServer(artifacts_dir=tmp_path)
    result = _call(server, "get_paper", {"run_id": RUN_ID})
    assert result["error_code"] == "PAPER_NOT_FOUND"


# ── MCP-08: search_literature ────────────────────────────────────


def test_search_literature_uses_backend(tmp_path: Path, monkeypatch) -> None:
    paper = Paper(
        paper_id="p1",
        title="Graph Neural Networks",
        authors=(Author(name="Alice Smith"),),
        year=2024,
        abstract="...",
        venue="NeurIPS",
        citation_count=10,
        source="arxiv",
    )
    monkeypatch.setattr(
        "researchclaw.mcp.server.search_papers", lambda query, **kwargs: [paper]
    )
    server = ResearchClawMCPServer(artifacts_dir=tmp_path)
    result = _call(server, "search_literature", {"query": "GNN", "max_results": 3})
    assert result["success"] is True
    assert result["count"] == 1
    assert result["results"][0]["title"] == "Graph Neural Networks"


def test_search_literature_upstream_error(tmp_path: Path, monkeypatch) -> None:
    def boom(query: str, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("researchclaw.mcp.server.search_papers", boom)
    server = ResearchClawMCPServer(artifacts_dir=tmp_path)
    result = _call(server, "search_literature", {"query": "GNN"})
    assert result["error_code"] == "UPSTREAM_ERROR"


# ── MCP-09: review_paper ─────────────────────────────────────────


def test_review_paper_requires_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("researchclaw.mcp.server.resolve_config_path", lambda _: None)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    paper = artifacts / "paper.md"
    paper.write_text("# Draft", encoding="utf-8")

    server = ResearchClawMCPServer(artifacts_dir=artifacts)
    result = _call(server, "review_paper", {"paper_path": str(paper)})
    assert result["success"] is False
    assert result["error_code"] == "CONFIG_REQUIRED"


def test_review_paper_success(tmp_path: Path, monkeypatch) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    paper = artifacts / "paper.md"
    paper.write_text("# Draft", encoding="utf-8")

    monkeypatch.setattr("researchclaw.mcp.server.has_llm_config", lambda config: True)
    monkeypatch.setattr("researchclaw.llm.create_llm_client", lambda config: object())
    monkeypatch.setattr(
        "researchclaw.mcp.server.review_paper_text",
        lambda *args, **kwargs: ReviewResult(
            review_markdown="# Reviews\n\nStrong paper.",
            model="test-model",
            independent=False,
            tokens=42,
        ),
    )
    server = ResearchClawMCPServer(
        config=_config(tmp_path), artifacts_dir=artifacts
    )
    result = _call(server, "review_paper", {"paper_path": str(paper)})
    assert result["success"] is True
    assert result["review_markdown"].startswith("# Reviews")
    assert result["model"] == "test-model"
    assert result["tokens"] == 42


# ── MCP-11: path security ────────────────────────────────────────


def test_invalid_run_id_rejected(tmp_path: Path) -> None:
    server = ResearchClawMCPServer(artifacts_dir=tmp_path)
    result = _call(server, "get_paper", {"run_id": "../../etc/passwd"})
    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"


def test_paper_path_must_stay_in_artifacts(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("# nope", encoding="utf-8")
    server = ResearchClawMCPServer(artifacts_dir=artifacts)
    result = _call(server, "review_paper", {"paper_path": str(outside)})
    assert result["error_code"] == "INVALID_PATH"


def test_paper_path_suffix_rejected(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    txt = artifacts / "paper.txt"
    txt.write_text("nope", encoding="utf-8")
    server = ResearchClawMCPServer(artifacts_dir=artifacts)
    result = _call(server, "review_paper", {"paper_path": str(txt)})
    assert result["error_code"] == "INVALID_PATH"


# ── MCP-12: shutdown ─────────────────────────────────────────────


def test_stop_cancels_active_runs(tmp_path: Path) -> None:
    release = threading.Event()

    def fake_execute(**kwargs) -> None:
        release.wait(1)

    server = ResearchClawMCPServer(
        config=_config(tmp_path),
        artifacts_dir=tmp_path / "artifacts",
        execute_pipeline_fn=fake_execute,
    )

    async def _run() -> None:
        result = await server.handle_tool_call("run_pipeline", {"topic": "GNN"})
        assert result["run_id"]
        await server.stop()
        await asyncio.sleep(0)

    asyncio.run(_run())
    release.set()
    assert server._active_tasks == {}
    assert server._active_cancels == {}
