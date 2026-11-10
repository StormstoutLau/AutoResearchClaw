"""G1b runtime: exit-code contract, attempt records, outbox."""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

from researchclaw.experiment.code_agent import ClaudeCodeAgent, create_code_agent
from researchclaw.runtime import attempt, exit_codes, outbox
from researchclaw.runtime.event_log import EventLog


def _res(status, error=None):
    return SimpleNamespace(status=SimpleNamespace(value=status), error=error)


def _fake_config(provider: str = "claude_code") -> SimpleNamespace:
    agent_cfg = SimpleNamespace(
        provider=provider, binary_path="claude", model="",
        max_budget_usd=1.0, timeout_sec=60, extra_args=[], env_extra=[],
    )
    return SimpleNamespace(experiment=SimpleNamespace(cli_agent=agent_cfg))


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


# ---------------------------------------------------------------- A1-9 session

def test_stage_session_id_is_a_stable_uuid(tmp_path):
    sid = attempt.stage_session_id(tmp_path, 10)
    assert sid == attempt.stage_session_id(tmp_path, 10)
    assert sid != attempt.stage_session_id(tmp_path, 13)
    uuid.UUID(sid)  # --session-id 只接受合法 UUID


def test_session_telemetry_ignores_stale_stage_log(tmp_path):
    stage = tmp_path / "stage-10"
    stage.mkdir()
    (stage / "cli_agent_log.json").write_text(json.dumps({
        "generated": "2026-11-11T10:00:00+00:00",
        "session": {"id": "sid-10", "resumed": True},
    }), encoding="utf-8")
    assert attempt.read_session_telemetry(stage) == ("sid-10", True)
    # 上一次 attempt 的日志不能冒充本次记录
    assert attempt.read_session_telemetry(
        stage, since="2026-11-11T10:00:01+00:00") == (None, False)

    (stage / "refinement_log.json").write_text(json.dumps({
        "generated": "2026-11-11T10:00:05+00:00",
        "cli_agent": {"session": {"id": "sid-13", "resumed": False}},
    }), encoding="utf-8")
    assert attempt.read_session_telemetry(
        stage, since="2026-11-11T10:00:01+00:00") == ("sid-13", False)


def test_claude_cmd_pins_then_resumes_session(tmp_path):
    first = ClaudeCodeAgent("claude", session_id="sid-1")
    cmd = first._build_cmd(tmp_path)
    assert cmd[cmd.index("--session-id") + 1] == "sid-1"
    assert "--resume" not in cmd

    retry = ClaudeCodeAgent("claude", session_id="sid-1", resume_session=True)
    cmd = retry._build_cmd(tmp_path)
    assert cmd[cmd.index("--resume") + 1] == "sid-1"
    assert "--session-id" not in cmd


def test_factory_pins_first_attempt_and_resumes_the_second(tmp_path):
    cfg = _fake_config()
    first = create_code_agent(cfg, session_ctx=(tmp_path, 10))
    assert first._session_id == attempt.stage_session_id(tmp_path, 10)
    assert first._resume_session is False

    attempt.write_attempt(tmp_path, attempt.AttemptRecord(
        stage=10, stage_name="CODE_GENERATION", attempt=1,
        started_at="t0", ended_at="t1", exit_class="retryable", exit_code=75))
    second = create_code_agent(cfg, session_ctx=(tmp_path, 10))
    assert second._session_id == first._session_id
    assert second._resume_session is True

    # 未登记续接的 backend 不拿到会话
    codex = create_code_agent(_fake_config("codex"), session_ctx=(tmp_path, 10))
    assert codex._session_id is None and codex._resume_session is False


def test_missing_session_falls_back_to_a_fresh_one(tmp_path):
    agent = ClaudeCodeAgent("claude", session_id="sid-x", resume_session=True)
    seen: list[list[str]] = []

    def fake_run(cmd, workdir, timeout, stdin_text=None):
        seen.append(list(cmd))
        if "--resume" in cmd:
            return 1, "", "No conversation found with session ID: sid-x", 0.1, False
        return 0, "ok", "", 0.2, False

    agent._run_subprocess = fake_run  # type: ignore[method-assign]
    rc, _out, _err, elapsed, timed_out = agent._invoke("prompt", tmp_path, 30)

    assert (rc, timed_out) == (0, False)
    assert abs(elapsed - 0.3) < 1e-9
    assert len(seen) == 2
    assert "--resume" in seen[0] and "--session-id" in seen[1]
    assert agent.last_session == {
        "id": "sid-x", "resumed": False, "resume_requested": True,
    }


def test_attempt_record_persists_the_real_provider_session(tmp_path):
    from researchclaw.pipeline import runner
    from researchclaw.pipeline.stages import Stage

    stage_dir = tmp_path / "stage-10"
    stage_dir.mkdir()
    (stage_dir / "cli_agent_log.json").write_text(json.dumps({
        "generated": "2026-11-11T10:00:02+00:00",
        "session": {"id": "sid-run", "resumed": True},
    }), encoding="utf-8")

    result = _res("done")
    runner._record_attempt(
        tmp_path, Stage.CODE_GENERATION, result, "2026-11-11T10:00:00+00:00")

    rec = attempt.read_attempt(tmp_path, 10, 1)
    assert rec["session_id"] == "sid-run"
    assert rec["context_replayed"] is False
