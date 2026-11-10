"""Event replay core (G1c / A1-2): cursor, gap, framing — no FastAPI needed."""
from __future__ import annotations

import json

from researchclaw.runtime.event_log import EventLog
from researchclaw.runtime.event_stream import (
    MAX_LIMIT, gap_frame, heartbeat_frame, parse_cursor, read_page, sse_frame,
)


def _seed(tmp_path, count=5):
    log = EventLog(tmp_path, "run-e")
    for i in range(count):
        log.append("stage.started", {"i": i}, stage=i + 1)
    log.append("run.completed", {"stages_run": count})
    return tmp_path


def test_parse_cursor_prefers_last_event_id():
    assert parse_cursor("7", 3) == 7
    assert parse_cursor(None, 3) == 3
    assert parse_cursor("abc", 3) == 3
    assert parse_cursor(None, None) is None
    assert parse_cursor("-2", None) is None


def test_read_page_returns_tail_after_cursor(tmp_path):
    _seed(tmp_path)
    page = read_page(tmp_path, "run-e", after=3)
    assert [e["seq"] for e in page["events"]] == [4, 5, 6]
    assert page["next_after"] == 6
    assert page["oldest_seq"] == 1
    assert page["gap"] is False
    assert page["terminal"] is True


def test_read_page_limit_and_has_more(tmp_path):
    _seed(tmp_path, count=10)
    page = read_page(tmp_path, "run-e", after=0, limit=4)
    assert len(page["events"]) == 4
    assert page["has_more"] is True
    assert page["next_after"] == 4
    # 上限钳制
    big = read_page(tmp_path, "run-e", after=0, limit=10 ** 6)
    assert len(big["events"]) <= MAX_LIMIT


def test_gap_when_cursor_predates_retention(tmp_path):
    """A1-2 负向：游标落在保留窗口之前必须显式报缺口，不得静默跳号。"""
    log = EventLog(tmp_path, "run-g")
    for i in range(3):
        log.append("stage.started", {"i": i})
    # 模拟最早的行已随归档段删除：oldest 变成 2
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(path.read_text(encoding="utf-8").splitlines()[1:]) + "\n",
                    encoding="utf-8")

    gap_page = read_page(tmp_path, "run-g", after=0)
    assert gap_page["oldest_seq"] == 2
    assert gap_page["gap"] is True
    assert [e["seq"] for e in gap_page["events"]] == [2, 3]

    no_gap = read_page(tmp_path, "run-g", after=1)
    assert no_gap["gap"] is False


def test_terminal_only_from_page(tmp_path):
    _seed(tmp_path, count=2)
    first = read_page(tmp_path, "run-e", after=0, limit=1)
    assert first["terminal"] is False     # 首页没有终止事件


def test_sse_and_gap_frames():
    frame = sse_frame({"seq": 4, "type": "stage.completed", "payload": {"a": 1}})
    assert frame.startswith("id: 4\nevent: stage.completed\ndata: ")
    assert frame.endswith("\n\n")
    assert json.loads(frame.split("data: ", 1)[1].strip())["payload"] == {"a": 1}
    assert "stream.gap" in gap_frame(9) and '"oldest_seq": 9' in gap_frame(9)
    assert heartbeat_frame() == ": ping\n\n"


def test_read_page_missing_log_is_empty(tmp_path):
    page = read_page(tmp_path, "nope")
    assert page["events"] == [] and page["oldest_seq"] == 0
