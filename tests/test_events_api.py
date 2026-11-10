"""HTTP/WS adapters for the event replay core (skipped when FastAPI is absent)."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi import FastAPI                      # noqa: E402
from fastapi.testclient import TestClient        # noqa: E402

from researchclaw.runtime.event_log import EventLog  # noqa: E402
from researchclaw.server.routes import events as ev  # noqa: E402

RUN_ID = "rc-20260101-000000-abcdef"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    log = EventLog(tmp_path, RUN_ID)
    log.append("stage.started", {"name": "A"}, stage=1)
    log.append("stage.completed", {"name": "A", "stage": 1}, stage=1)
    log.append("run.completed", {"stages_run": 1})
    monkeypatch.setattr(ev, "_run_dir", lambda run_id: tmp_path)
    app = FastAPI()
    app.include_router(ev.router)
    return TestClient(app)


def test_cursor_page(client):
    body = client.get("/api/runs/%s/events" % RUN_ID, params={"after": 1}).json()
    assert [e["seq"] for e in body["events"]] == [2, 3]
    assert body["next_after"] == 3
    assert body["terminal"] is True


def test_last_event_id_header_wins(client):
    body = client.get("/api/runs/%s/events" % RUN_ID,
                      params={"after": 0},
                      headers={"Last-Event-ID": "2"}).json()
    assert [e["seq"] for e in body["events"]] == [3]


def test_sse_stream_emits_frames_and_terminates(client):
    with client.stream("GET", "/api/runs/%s/events/stream" % RUN_ID,
                       params={"after": 0}) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        text = "".join(resp.iter_text())
    assert "retry: 3000" in text
    assert "event: run.completed" in text
    assert "id: 3" in text


def test_missing_event_log_is_404(tmp_path, monkeypatch):
    monkeypatch.setattr(ev, "_run_dir", lambda run_id: tmp_path)
    app = FastAPI()
    app.include_router(ev.router)
    assert TestClient(app).get(
        "/api/runs/%s/events" % RUN_ID).status_code == 404


def test_gap_is_reported_over_http(tmp_path, monkeypatch):
    """A1-2 负向（HTTP 层）：游标早于保留窗口时必须显式报缺口。"""
    log = EventLog(tmp_path, RUN_ID)
    for i in range(3):
        log.append("stage.started", {"i": i})
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(path.read_text(encoding="utf-8").splitlines()[1:]) + "\n",
                    encoding="utf-8")
    monkeypatch.setattr(ev, "_run_dir", lambda run_id: tmp_path)
    app = FastAPI()
    app.include_router(ev.router)
    body = TestClient(app).get("/api/runs/%s/events" % RUN_ID,
                               params={"after": 0}).json()
    assert body["gap"] is True
    assert body["oldest_seq"] == 2
    assert [e["seq"] for e in body["events"]] == [2, 3]
