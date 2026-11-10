"""Event log invariants (G1a / A1-1, A1-5, A1-6, Q9)."""
from __future__ import annotations

import gzip
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from researchclaw.runtime.event_log import (
    EventDurabilityError,
    EventLog,
    EventQuotaExceeded,
    ZERO_HASH,
    canonical_json,
    rebuild_checkpoint,
)


def _log(tmp_path: Path, **kw) -> EventLog:
    return EventLog(tmp_path, "run-1", **kw)


def test_append_chain_and_payload_digest(tmp_path):
    log = _log(tmp_path)
    e1 = log.append("run.started", {"topic": "x"})
    e2 = log.append("stage.started", {"name": "TOPIC_INIT"}, stage=1)

    assert (e1.seq, e2.seq) == (1, 2)
    assert e1.prev_sha256 == ZERO_HASH
    ok, msg = log.verify_chain()
    assert ok, msg

    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    assert first["payload_sha256"] == __import__("hashlib").sha256(
        canonical_json({"topic": "x"}).encode()).hexdigest()


def test_tamper_breaks_chain(tmp_path):
    log = _log(tmp_path)
    log.append("run.started", {"a": 1})
    log.append("stage.started", {"b": 2})
    log.append("stage.completed", {"c": 3})
    p = tmp_path / "events.jsonl"
    lines = p.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"b":2', '"b":3')   # 中间行篡改 → 后继 prev_sha256 失配
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, msg = EventLog(tmp_path, "run-1").verify_chain()
    assert not ok and "prev_sha256" in msg


def test_torn_tail_is_dropped_and_appends_continue(tmp_path):
    log = _log(tmp_path)
    log.append("run.started", {})
    p = tmp_path / "events.jsonl"
    with p.open("a", encoding="utf-8") as fh:
        fh.write('{"seq": 2, "broken"')
    reopened = EventLog(tmp_path, "run-1")
    assert reopened.truncated is True
    assert len(reopened.read_all()) == 1
    assert reopened.last_seq == 1
    nxt = reopened.append("stage.started", {})
    assert nxt.seq == 2
    ok, msg = reopened.verify_chain()
    assert ok, msg


def test_run_quota_is_enforced(tmp_path):
    log = _log(tmp_path, max_run_events=2)
    log.append("run.started", {})
    log.append("stage.started", {})
    with pytest.raises(EventQuotaExceeded):
        log.append("stage.completed", {})


def test_segment_rolling_keeps_chain(tmp_path):
    log = _log(tmp_path, max_segment_bytes=1)
    for i in range(4):
        log.append("stage.started", {"i": i}, stage=i + 1)
    segments = sorted(p.name for p in tmp_path.glob("events.*.jsonl"))
    assert segments, "expected at least one rolled segment"
    ok, msg = EventLog(tmp_path, "run-1").verify_chain()
    assert ok, msg
    assert len(EventLog(tmp_path, "run-1").read_all()) == 4


def test_retention_archives_then_deletes(tmp_path):
    log = _log(tmp_path, max_segment_bytes=1)
    log.append("stage.started", {"i": 0})
    log.append("stage.started", {"i": 1})
    seg = next(p for p in tmp_path.glob("events.*.jsonl"))
    old = (datetime.now(timezone.utc) - timedelta(days=40)).timestamp()
    os.utime(seg, (old, old))

    result = log.apply_retention(retention_days=30, archive_days=365)
    assert result["archived"] == [seg.name + ".gz"]
    gz = tmp_path / (seg.name + ".gz")
    assert gz.exists()
    with gzip.open(gz, "rt", encoding="utf-8") as fh:
        assert "stage.started" in fh.read()

    older = (datetime.now(timezone.utc) - timedelta(days=400)).timestamp()
    os.utime(gz, (older, older))
    result = log.apply_retention(retention_days=30, archive_days=365)
    assert result["deleted"] == [gz.name]
    assert not gz.exists()


def test_summary_records_head_tail_and_key_events(tmp_path):
    log = _log(tmp_path)
    log.append("run.started", {})
    log.append("stage.started", {"name": "A"}, stage=1)
    log.append("stage.completed", {"name": "A", "stage": 1}, stage=1)
    log.append("run.completed", {"stages_run": 1})
    s = log.write_summary()

    assert s["first_seq"] == 1 and s["last_seq"] == 4 and s["count"] == 4
    assert s["chain_head"] != ZERO_HASH and s["chain_tail"] != ZERO_HASH
    assert [k["type"] for k in s["key_events"]] == ["run.started", "run.completed"]
    assert (tmp_path / "events_summary.json").is_file()


def test_rebuild_checkpoint_from_stage_completed(tmp_path):
    log = _log(tmp_path)
    log.append("run.started", {})
    log.append("stage.completed", {"name": "TOPIC_INIT", "stage": 1}, stage=1)
    log.append("stage.completed", {"name": "LITERATURE_SEARCH", "stage": 2}, stage=2)
    cp = rebuild_checkpoint(log.read_all())
    assert cp["last_completed_stage"] == 2
    assert cp["last_completed_name"] == "LITERATURE_SEARCH"
    assert cp["recovered"] is True
    assert cp["recovered_from_seq"] == 3


def test_rebuild_checkpoint_none_without_completed_stage(tmp_path):
    log = _log(tmp_path)
    log.append("run.started", {})
    assert rebuild_checkpoint(log.read_all()) is None


def test_fsync_failure_raises_durability_error(tmp_path, monkeypatch):
    log = _log(tmp_path)
    log.append("run.started", {})

    def boom(_fd):
        raise OSError(5, "I/O error")

    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(EventDurabilityError):
        log.append("stage.started", {})


def test_read_after_cursor(tmp_path):
    log = _log(tmp_path)
    for i in range(5):
        log.append("stage.started", {"i": i})
    got = log.read_after(3)
    assert [e["seq"] for e in got] == [4, 5]
