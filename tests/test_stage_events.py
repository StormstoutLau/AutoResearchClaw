"""G3 M2 (P-078): stage_events progress ledger and loop guard."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig
from researchclaw.pipeline import runner as rc_runner
from researchclaw.pipeline.executor import StageResult
from researchclaw.pipeline.stages import Stage, StageStatus
from researchclaw.runtime.stage_events import (
    E_LOOP_DETECTED,
    StageEventError,
    append_stage_event,
    collect_progress,
    evaluate_loop,
    load_stage_events,
    plan_payload,
    plan_signature,
    record_stage_progress,
)


def _write_stage3(
    run_dir: Path,
    *,
    queries: tuple[str, ...] = ("topic a", "topic b"),
    sources: tuple[str, ...] = ("arxiv", "semantic_scholar"),
    year_min: int = 2020,
) -> None:
    stage3 = run_dir / "stage-03"
    stage3.mkdir(parents=True, exist_ok=True)
    (stage3 / "queries.json").write_text(
        json.dumps({"queries": list(queries), "year_min": year_min}),
        encoding="utf-8",
    )
    (stage3 / "sources.json").write_text(
        json.dumps([{"id": sid} for sid in sources]),
        encoding="utf-8",
    )
    (stage3 / "search_plan.yaml").write_text(
        f"filters:\n  min_year: {year_min}\n  language:\n  - en\n",
        encoding="utf-8",
    )


def _write_rows(path: Path, ids: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps({"id": item}) + "\n" for item in ids),
        encoding="utf-8",
    )


def _write_stage4(run_dir: Path, ids: tuple[str, ...], *, degraded: bool = False) -> None:
    _write_rows(run_dir / "stage-04" / "candidates.jsonl", ids)
    (run_dir / "stage-04" / "retrieval_status.json").write_text(
        json.dumps(
            {
                "retrieval_degraded": degraded,
                "real_search_succeeded": not degraded,
                "degraded_reason": [] if not degraded else ["academic_api_search_failed"],
            }
        ),
        encoding="utf-8",
    )


def _write_stage5(run_dir: Path, ids: tuple[str, ...]) -> None:
    _write_rows(run_dir / "stage-05" / "shortlist.jsonl", ids)


def test_plan_signature_is_order_independent(tmp_path: Path) -> None:
    _write_stage3(tmp_path)
    first = plan_payload(tmp_path, 4)
    assert first is not None
    sig_first = plan_signature(first)

    _write_stage3(
        tmp_path,
        queries=("topic b", "topic a"),
        sources=("semantic_scholar", "arxiv"),
    )
    second = plan_payload(tmp_path, 4)
    assert second is not None
    assert plan_signature(second) == sig_first


def test_plan_signature_missing_inputs_returns_none(tmp_path: Path) -> None:
    assert plan_payload(tmp_path, 4) is None


def test_collect_stage4_progress(tmp_path: Path) -> None:
    _write_stage3(tmp_path)
    _write_stage4(tmp_path, ("p1", "p2"))
    progress = collect_progress(tmp_path, 4)
    assert progress["plan_sig"].startswith("sha256:")
    assert progress["new_rows"] == 2
    assert progress["network_error"] is False
    assert progress["row_ids_digest"].startswith("sha256:")


def test_collect_stage4_progress_marks_network_error(tmp_path: Path) -> None:
    _write_stage3(tmp_path)
    _write_stage4(tmp_path, ("p1",), degraded=True)
    assert collect_progress(tmp_path, 4)["network_error"] is True


def test_collect_stage5_progress_uses_shortlist(tmp_path: Path) -> None:
    _write_stage3(tmp_path)
    _write_stage5(tmp_path, ("p1", "p2", "p3"))
    progress = collect_progress(tmp_path, 5, quality_threshold=0.8)
    assert progress["new_rows"] == 3
    assert progress["network_error"] is False
    stage5_payload = plan_payload(tmp_path, 5, quality_threshold=0.8)
    assert stage5_payload is not None
    assert stage5_payload["filters"]["quality_threshold"] == 0.8
    assert stage5_payload["stage"] == 5


def test_append_stage_event_monotonic(tmp_path: Path) -> None:
    first = append_stage_event(
        tmp_path,
        stage=4,
        stage_name="LITERATURE_COLLECT",
        attempt=1,
        plan_sig="sha256:a",
        new_rows=0,
        row_ids_digest="sha256:empty",
        network_error=False,
    )
    second = append_stage_event(
        tmp_path,
        stage=4,
        stage_name="LITERATURE_COLLECT",
        attempt=2,
        plan_sig="sha256:a",
        new_rows=0,
        row_ids_digest="sha256:empty",
        network_error=False,
    )
    assert (first.seq, second.seq) == (1, 2)
    loaded = load_stage_events(tmp_path)
    assert [event.attempt for event in loaded] == [1, 2]


def test_load_tolerates_torn_tail(tmp_path: Path) -> None:
    append_stage_event(
        tmp_path,
        stage=4,
        stage_name="LITERATURE_COLLECT",
        attempt=1,
        plan_sig="sha256:a",
        new_rows=1,
        row_ids_digest="sha256:d",
        network_error=False,
    )
    with (tmp_path / "stage_events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"seq": 2, "stage": 4')
    assert len(load_stage_events(tmp_path)) == 1


def test_load_rejects_middle_corruption(tmp_path: Path) -> None:
    append_stage_event(
        tmp_path,
        stage=4,
        stage_name="LITERATURE_COLLECT",
        attempt=1,
        plan_sig="sha256:a",
        new_rows=1,
        row_ids_digest="sha256:d",
        network_error=False,
    )
    path = tmp_path / "stage_events.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(lines[0] + "\n{not json\n" + lines[0] + "\n", encoding="utf-8")
    with pytest.raises(StageEventError):
        load_stage_events(tmp_path)


def test_load_tolerates_multiple_torn_tail_lines(tmp_path: Path) -> None:
    """P-079 O-1: consecutive torn lines at EOF are dropped like EventLog does."""
    append_stage_event(
        tmp_path,
        stage=4,
        stage_name="LITERATURE_COLLECT",
        attempt=1,
        plan_sig="sha256:a",
        new_rows=1,
        row_ids_digest="sha256:d",
        network_error=False,
    )
    with (tmp_path / "stage_events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"seq": 2, "sta\n{"seq": 3, "stage"\n')
    assert len(load_stage_events(tmp_path)) == 1


def test_evaluate_loop_rejects_non_positive_window(tmp_path: Path) -> None:
    """P-079 O-2: window < 1 must not silently pause forever."""
    events = load_stage_events(tmp_path)
    for bad in (0, -5):
        with pytest.raises(ValueError):
            evaluate_loop(events, stage=4, window=bad)


def test_append_stage_event_auto_attempt(tmp_path: Path) -> None:
    first = append_stage_event(
        tmp_path,
        stage=4,
        stage_name="LITERATURE_COLLECT",
        plan_sig="sha256:a",
        new_rows=0,
        row_ids_digest="sha256:empty",
        network_error=False,
    )
    second = append_stage_event(
        tmp_path,
        stage=4,
        stage_name="LITERATURE_COLLECT",
        plan_sig="sha256:a",
        new_rows=0,
        row_ids_digest="sha256:empty",
        network_error=False,
    )
    assert (first.attempt, second.attempt) == (1, 2)


def test_stage_events_concurrent_append_unique_seq(tmp_path: Path) -> None:
    """P-079 O-3: concurrent appends must keep seq unique and lossless."""
    _write_stage3(tmp_path)
    _write_stage4(tmp_path, ("p1",))
    barrier = threading.Barrier(8)
    errors: list[str] = []

    def worker() -> None:
        try:
            barrier.wait()
            record_stage_progress(tmp_path, 4, "LITERATURE_COLLECT")
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    events = load_stage_events(tmp_path)
    assert len(events) == 8
    assert sorted(event.seq for event in events) == list(range(1, 9))
    assert sorted(event.attempt for event in events) == list(range(1, 9))


def test_loop_warns_at_two_rounds(tmp_path: Path) -> None:
    _write_stage3(tmp_path)
    _write_stage4(tmp_path, ("p1", "p2"))
    record_stage_progress(tmp_path, 4, "LITERATURE_COLLECT")
    decision = record_stage_progress(tmp_path, 4, "LITERATURE_COLLECT")
    assert decision["action"] == "warn"
    assert decision["consecutive"] == 2


def test_loop_pauses_after_three_identical_rounds(tmp_path: Path) -> None:
    _write_stage3(tmp_path)
    _write_stage4(tmp_path, ("p1", "p2"))
    record_stage_progress(tmp_path, 4, "LITERATURE_COLLECT")
    record_stage_progress(tmp_path, 4, "LITERATURE_COLLECT")
    decision = record_stage_progress(tmp_path, 4, "LITERATURE_COLLECT")
    assert decision["action"] == "pause"
    assert decision["code"] == E_LOOP_DETECTED


def test_loop_does_not_pause_when_rows_change(tmp_path: Path) -> None:
    _write_stage3(tmp_path)
    _write_stage4(tmp_path, ("p1",))
    record_stage_progress(tmp_path, 4, "LITERATURE_COLLECT")
    _write_stage4(tmp_path, ("p1", "p2", "p3", "p4", "p5"))
    record_stage_progress(tmp_path, 4, "LITERATURE_COLLECT")
    _write_stage4(tmp_path, ("p1", "p2", "p3", "p4", "p5", "p6"))
    decision = record_stage_progress(tmp_path, 4, "LITERATURE_COLLECT")
    assert decision["action"] != "pause"


def test_network_error_round_is_exempt(tmp_path: Path) -> None:
    _write_stage3(tmp_path)
    _write_stage4(tmp_path, ("p1", "p2"), degraded=True)
    record_stage_progress(tmp_path, 4, "LITERATURE_COLLECT")
    record_stage_progress(tmp_path, 4, "LITERATURE_COLLECT")
    decision = record_stage_progress(tmp_path, 4, "LITERATURE_COLLECT")
    assert decision["action"] != "pause"
    assert decision["consecutive"] == 0


def test_record_skips_without_plan_inputs(tmp_path: Path) -> None:
    decision = record_stage_progress(tmp_path, 4, "LITERATURE_COLLECT")
    assert decision["action"] == "skip"
    assert load_stage_events(tmp_path) == []


def test_evaluate_loop_is_pure(tmp_path: Path) -> None:
    events = load_stage_events(tmp_path)
    before = list(events)
    evaluate_loop(events, stage=4)
    assert events == before


def _config(tmp_path: Path) -> RCConfig:
    data = {
        "project": {"name": "rc-m2-test", "mode": "docs-first"},
        "research": {"topic": "loop guard testing"},
        "runtime": {"timezone": "UTC"},
        "notifications": {"channel": "local"},
        "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
        "openclaw_bridge": {},
        "llm": {
            "provider": "openai-compatible",
            "base_url": "http://localhost:1234/v1",
            "api_key_env": "RC_TEST_KEY",
            "api_key": "inline",
        },
    }
    return RCConfig.from_dict(data, project_root=tmp_path, check_paths=False)


def _doney(stage: Stage, artifacts: tuple[str, ...]) -> StageResult:
    return StageResult(stage=stage, status=StageStatus.DONE, artifacts=artifacts)


def test_runner_pauses_on_loop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_stage3(run_dir)
    config = _config(tmp_path)

    def mock_execute_stage(stage: Stage, **kwargs) -> StageResult:
        _ = kwargs
        if stage == Stage.LITERATURE_COLLECT:
            _write_stage4(run_dir, ("p1", "p2"))
            return _doney(stage, ("candidates.jsonl",))
        if stage == Stage.LITERATURE_SCREEN:
            _write_stage5(run_dir, ("p1",))
            return _doney(stage, ("shortlist.jsonl",))
        return _doney(stage, ("out.md",))

    monkeypatch.setattr(rc_runner, "execute_stage", mock_execute_stage)

    for _ in range(2):
        results = rc_runner.execute_pipeline(
            run_dir=run_dir,
            run_id="run-loop",
            config=config,
            adapters=AdapterBundle(),
            from_stage=Stage.LITERATURE_COLLECT,
            to_stage=Stage.LITERATURE_SCREEN,
        )
        assert all(item.status == StageStatus.DONE for item in results)

    results = rc_runner.execute_pipeline(
        run_dir=run_dir,
        run_id="run-loop",
        config=config,
        adapters=AdapterBundle(),
        from_stage=Stage.LITERATURE_COLLECT,
        to_stage=Stage.LITERATURE_SCREEN,
    )
    assert results[-1].stage == Stage.LITERATURE_COLLECT
    assert results[-1].status == StageStatus.PAUSED
    assert results[-1].error == E_LOOP_DETECTED
    summary = json.loads((run_dir / "pipeline_summary.json").read_text(encoding="utf-8"))
    assert summary["final_status"] == "paused"
    checkpoint = json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["last_completed_stage"] == int(Stage.LITERATURE_SCREEN)


class _FakeLog:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    def append(self, *args, **kwargs) -> None:
        self.calls.append((args, kwargs))


def test_emit_summary_anchor_skips_nested_execution(tmp_path: Path) -> None:
    log = _FakeLog()
    summary = {"run_id": "r", "generated": "2026-11-12T00:00:00Z"}
    rc_runner._emit_summary_anchor(tmp_path, summary, log, False)
    assert log.calls == []
    rc_runner._emit_summary_anchor(tmp_path, summary, log, True)
    assert len(log.calls) == 1
    assert log.calls[0][0][0] == "pipeline.summary"


def test_events_disabled_skips_anchor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ARC_EVENTS_DISABLED", "1")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_stage3(run_dir)
    config = _config(tmp_path)

    def mock_execute_stage(stage: Stage, **kwargs) -> StageResult:
        _ = kwargs
        if stage == Stage.LITERATURE_COLLECT:
            _write_stage4(run_dir, ("p1",))
            return _doney(stage, ("candidates.jsonl",))
        _write_stage5(run_dir, ("p1",))
        return _doney(stage, ("shortlist.jsonl",))

    monkeypatch.setattr(rc_runner, "execute_stage", mock_execute_stage)
    results = rc_runner.execute_pipeline(
        run_dir=run_dir,
        run_id="run-no-events",
        config=config,
        adapters=AdapterBundle(),
        from_stage=Stage.LITERATURE_COLLECT,
        to_stage=Stage.LITERATURE_SCREEN,
    )
    assert all(item.status == StageStatus.DONE for item in results)
    assert not (run_dir / "events.jsonl").exists()
    assert (run_dir / "pipeline_summary.json").is_file()


def test_runner_anchors_summary_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_stage3(run_dir)
    config = _config(tmp_path)

    def mock_execute_stage(stage: Stage, **kwargs) -> StageResult:
        _ = kwargs
        if stage == Stage.LITERATURE_COLLECT:
            _write_stage4(run_dir, ("p1",))
            return _doney(stage, ("candidates.jsonl",))
        _write_stage5(run_dir, ("p1",))
        return _doney(stage, ("shortlist.jsonl",))

    monkeypatch.setattr(rc_runner, "execute_stage", mock_execute_stage)
    rc_runner.execute_pipeline(
        run_dir=run_dir,
        run_id="run-anchor",
        config=config,
        adapters=AdapterBundle(),
        from_stage=Stage.LITERATURE_COLLECT,
        to_stage=Stage.LITERATURE_SCREEN,
    )
    from researchclaw.evidence.summary_check import verify_summary

    result = verify_summary(run_dir, require_event=True)
    assert result["ok"] is True, result["errors"]
    events = [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [e["type"] for e in events].count("pipeline.summary") == 1
