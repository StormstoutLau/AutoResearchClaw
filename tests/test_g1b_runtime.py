"""G1b runtime: exit-code contract, attempt records, outbox."""
from __future__ import annotations

import json
from types import SimpleNamespace

from researchclaw.runtime import attempt, exit_codes, outbox
from researchclaw.runtime.event_log import EventLog


def _res(status, error=None):
    return SimpleNamespace(status=SimpleNamespace(value=status), error=error)


# ---------------------------------------------------------------- exit codes

def test_paused_is_not_success_and_not_failure():
    """R-1：审批门/暂停必须单独成码，不能被当作成功或可重试失败。"""
    assert exit_codes.classify_results([_res("paused")]) == exit_codes.PAUSED
    assert exit_codes.classify_results([_res("blocked_approval")]) == exit_codes.PAUSED
    assert exit_codes.classify_results([_res("rejected")]) == exit_codes.PAUSED
    assert not exit_codes.is_retryable(exit_codes.PAUSED)


def test_all_done_is_zero_and_empty_is_data():
    assert exit_codes.classify_results([_res("done"), _res("done")]) == exit_codes.OK
    assert exit_codes.classify_results([]) == exit_codes.DATA


def test_failure_classification():
    assert exit_codes.classify_results([_res("failed", "connection timeout")]) == exit_codes.RETRYABLE
    assert exit_codes.classify_results([_res("failed", "401 Unauthorized")]) == exit_codes.REVOKED
    assert exit_codes.classify_results([_res("failed", "invalid schema version")]) == exit_codes.CONFIG
    assert exit_codes.classify_results([_res("failed", "boom")]) == exit_codes.RETRYABLE


def test_failure_wins_over_paused():
    results = [_res("paused"), _res("failed", "OOM killed")]
    assert exit_codes.classify_results(results) == exit_codes.RETRYABLE


def test_only_75_is_retryable():
    assert exit_codes.is_retryable(75) is True
    for code in (0, 65, 77, 78, 85):
        assert exit_codes.is_retryable(code) is False
    assert exit_codes.class_name(85) == "paused"


# ---------------------------------------------------------------- attempt

def test_attempt_records_and_numbering(tmp_path):
    assert attempt.next_attempt_number(tmp_path, 12) == 1
    rec = attempt.AttemptRecord(
        stage=12, stage_name="EXPERIMENT_RUN", attempt=1,
        started_at="t0", ended_at="t1", exit_class="retryable", exit_code=75,
        resume_note="check artifacts", artifacts=("results.json (12B)",))
    path = attempt.write_attempt(tmp_path, rec)
    assert path.name == "attempt-1.json"
    assert attempt.next_attempt_number(tmp_path, 12) == 2
    assert attempt.read_attempt(tmp_path, 12, 1)["exit_code"] == 75
    assert attempt.latest_attempt(tmp_path, 12)["attempt"] == 1
    assert attempt.latest_attempt(tmp_path, 99) is None


def test_resume_note_contents_and_cap():
    note = attempt.build_resume_note(
        stage=12, stage_name="EXPERIMENT_RUN", attempt=2,
        last_error="timeout after 600s", artifacts=("a.json (1B)",), exit_code=75)
    assert "attempt 2" in note and "Stage 12" in note
    assert "timeout" in note and "a.json" in note
    assert "禁止无条件重复外部付费调用" in note
    long = attempt.build_resume_note(
        stage=1, stage_name="X", attempt=1, last_error="e" * 5000,
        artifacts=tuple("f%d (1B)" % i for i in range(50)))
    assert len(long) <= attempt.MAX_NOTE_CHARS


def test_artifact_inventory(tmp_path):
    d = tmp_path / "stage-12"
    (d / "sub").mkdir(parents=True)
    (d / "results.json").write_text("{}", encoding="utf-8")
    names = attempt.list_artifacts(d)
    assert any("results.json" in n for n in names)
    assert any("sub/" in n for n in names)
    assert attempt.list_artifacts(tmp_path / "missing") == ()


# ---------------------------------------------------------------- outbox

def test_outbox_enqueue_run_and_dedupe(tmp_path):
    log = EventLog(tmp_path, "run-o")
    eff = outbox.enqueue(log, "overleaf_sync", {"stage": 23})
    assert eff.key == outbox.effect_key("overleaf_sync", {"stage": 23})
    assert [e.key for e in outbox.pending(log)] == [eff.key]

    calls = []
    result = outbox.run_pending(log, lambda e: calls.append(e.key) or "ok")
    assert result == {"ok": 1, "failed": 0, "skipped": 0}
    assert calls == [eff.key]
    assert outbox.pending(log) == []

    # 再跑一次不得重复执行
    again = outbox.run_pending(log, lambda e: calls.append(e.key) or "ok")
    assert again["ok"] == 0 and len(calls) == 1


def test_outbox_failure_is_terminal_but_recorded(tmp_path):
    log = EventLog(tmp_path, "run-f")
    outbox.enqueue(log, "k", {"a": 1})

    def boom(_eff):
        raise ValueError("nope")

    result = outbox.run_pending(log, boom)
    assert result["failed"] == 1
    assert outbox.pending(log) == []
    done = [e for e in log.read_all() if e["type"] == "effect.done"]
    assert done[-1]["payload"]["result"].startswith("error:")


def test_outbox_kind_filter(tmp_path):
    log = EventLog(tmp_path, "run-k")
    outbox.enqueue(log, "a", {"x": 1})
    outbox.enqueue(log, "b", {"x": 2})
    seen = []
    outbox.run_pending(log, lambda e: seen.append(e.kind) or "ok", kinds=["b"])
    assert seen == ["b"]
    assert len(outbox.pending(log)) == 1


def test_outbox_survives_missing_log(tmp_path):
    class Broken:
        def read_all(self):
            raise OSError("gone")

    assert outbox.pending(Broken()) == []
