"""Tests for frontend mounting and the projects API (PR-2).

The web UI must be reachable even though the frontend directory in this
repository is named ``frontend-legacy`` rather than ``frontend``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio


def _config():
    from researchclaw.config import RCConfig

    data = {
        "project": {"name": "test"},
        "research": {"topic": "test"},
        "runtime": {"timezone": "UTC"},
        "notifications": {"channel": "console"},
        "knowledge_base": {"root": "knowledge"},
        "llm": {
            "provider": "openai-compatible",
            "base_url": "http://localhost",
            "api_key_env": "TEST",
        },
    }
    return RCConfig.from_dict(data, check_paths=False)


def _client(app):
    from httpx import ASGITransport, AsyncClient

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_frontend_index_is_served() -> None:
    pytest.importorskip("fastapi")
    from researchclaw.server.app import create_app

    app = create_app(_config())
    async with _client(app) as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "ResearchClaw" in resp.text


async def test_frontend_static_assets_are_served() -> None:
    pytest.importorskip("fastapi")
    from researchclaw.server.app import create_app

    app = create_app(_config())
    async with _client(app) as client:
        resp = await client.get("/static/src/app.js")
    assert resp.status_code == 200
    assert len(resp.text) > 0


async def test_frontend_dir_can_be_overridden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    from researchclaw.server.app import create_app

    custom = tmp_path / "custom-ui"
    (custom / "src").mkdir(parents=True)
    (custom / "index.html").write_text("<html><title>Custom UI</title></html>", encoding="utf-8")
    (custom / "src" / "app.js").write_text("console.log('custom');", encoding="utf-8")

    monkeypatch.setenv("RESEARCHCLAW_FRONTEND_DIR", str(custom))

    app = create_app(_config())
    async with _client(app) as client:
        index = await client.get("/")
        asset = await client.get("/static/src/app.js")

    assert index.status_code == 200
    assert "Custom UI" in index.text
    assert "custom" in asset.text


async def test_missing_frontend_keeps_api_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    from researchclaw.server import app as app_module

    monkeypatch.setattr(app_module, "_resolve_frontend_dir", lambda: None)

    app = app_module.create_app(_config())

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/" not in paths
    assert "/api/health" in paths

    async with _client(app) as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200


async def test_projects_endpoint_reads_real_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    from researchclaw.server.app import create_app

    run_dir = tmp_path / "artifacts" / "rc-20261029-120000-abc123"
    run_dir.mkdir(parents=True)
    (run_dir / "checkpoint.json").write_text(
        json.dumps(
            {
                "last_completed_stage": 12,
                "last_completed_name": "EXPERIMENT_RUN",
                "run_id": run_dir.name,
                "timestamp": "2026-10-29T12:00:00+00:00",
                "schema_version": 1,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    app = create_app(_config())
    async with _client(app) as client:
        resp = await client.get("/api/projects")

    assert resp.status_code == 200
    projects = resp.json()["projects"]
    assert len(projects) == 1
    assert projects[0]["current_stage"] == 12
    assert projects[0]["current_stage_name"] == "EXPERIMENT_RUN"
    assert projects[0]["schema_version"] == 1
