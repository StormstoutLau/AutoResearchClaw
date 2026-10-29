"""PR-5 contract tests: cost tracking (COST-01..05) and spec de-duplication."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from researchclaw.cost_tracker import (
    COST_LOG_FILENAME,
    CostRecord,
    CostTracker,
    get_global_tracker,
    sum_cost_log,
)
from researchclaw.hitl.cost_guard import CostGuard
from researchclaw.llm.client import LLMClient, LLMConfig, LLMResponse


@pytest.fixture(autouse=True)
def _isolated_tracker():
    """Each test gets a clean global tracker except where it sets one up."""
    tracker = get_global_tracker()
    tracker.reset()
    yield
    tracker.reset()


def _read_log(run_dir: Path) -> list[dict]:
    path = run_dir / COST_LOG_FILENAME
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ── COST-01: a chat call appends one line ───────────────────────


def test_cost01_chat_appends_one_line(tmp_path: Path, monkeypatch) -> None:
    tracker = get_global_tracker()
    tracker.begin_run(run_dir=tmp_path, run_id="rc-1")
    tracker.set_stage("PAPER_DRAFT")

    client = LLMClient(
        LLMConfig(
            base_url="http://localhost",
            api_key="k",
            primary_model="m1",
            input_cost_per_1m=1.0,
            output_cost_per_1m=2.0,
        )
    )
    monkeypatch.setattr(
        client,
        "_call_with_retry",
        lambda *args, **kwargs: LLMResponse(
            content="hi",
            model="m1",
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            raw={"usage": {"prompt_tokens": 1000, "completion_tokens": 500}},
        ),
    )

    _ = client.chat([{"role": "user", "content": "hello"}])

    entries = _read_log(tmp_path)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["schema_version"] == 1
    assert entry["run_id"] == "rc-1"
    assert entry["stage"] == "PAPER_DRAFT"
    assert entry["model"] == "m1"
    assert entry["prompt_tokens"] == 1000
    assert entry["completion_tokens"] == 500
    assert entry["total_tokens"] == 1500
    assert entry["source"] == "pricing_table"
    # 1000/1e6*1.0 + 500/1e6*2.0
    assert entry["cost_usd"] == pytest.approx(0.002)


def test_cost01_no_usage_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    tracker = get_global_tracker()
    tracker.begin_run(run_dir=tmp_path, run_id="rc-1")

    client = LLMClient(LLMConfig(base_url="http://localhost", api_key="k"))
    monkeypatch.setattr(
        client,
        "_call_with_retry",
        lambda *args, **kwargs: LLMResponse(content="hi", model="m1"),
    )
    client.chat([{"role": "user", "content": "hello"}])
    assert _read_log(tmp_path) == []


# ── COST-02: budget semantics ───────────────────────────────────


def test_cost02_budget_exceeded(tmp_path: Path) -> None:
    tracker = CostTracker()
    tracker.begin_run(run_dir=tmp_path, run_id="rc-1")
    tracker.record(
        CostRecord(
            timestamp="t",
            run_id="rc-1",
            stage="s",
            model="m",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            cost_usd=0.02,
            source="pricing_table",
        )
    )
    assert tracker.check_budget(0.01) is False
    assert tracker.check_budget(0.03) is True


def test_cost02_zero_budget_disables_check(tmp_path: Path) -> None:
    tracker = CostTracker()
    tracker.begin_run(run_dir=tmp_path, run_id="rc-1")
    tracker.record_llm_call(model="m", prompt_tokens=10, provider_cost=5.0)
    assert tracker.check_budget(0.0) is True
    assert tracker.check_budget(-1.0) is True


def test_cost02_equal_to_budget_counts_as_exhausted(tmp_path: Path) -> None:
    tracker = CostTracker()
    tracker.begin_run(run_dir=tmp_path, run_id="rc-1")
    tracker.record_llm_call(model="m", prompt_tokens=1, provider_cost=1.0)
    assert tracker.check_budget(1.0) is False


# ── COST-03: cost source precedence ────────────────────────────


def test_cost03a_provider_usage_wins(tmp_path: Path) -> None:
    tracker = CostTracker()
    tracker.begin_run(run_dir=tmp_path, run_id="rc-1")
    record = tracker.record_llm_call(
        model="m",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        provider_cost=0.003,
        input_cost_per_1m=99.0,
        output_cost_per_1m=99.0,
    )
    assert record.source == "provider_usage"
    assert record.cost_usd == pytest.approx(0.003)


def test_cost03b_pricing_table_amount(tmp_path: Path) -> None:
    tracker = CostTracker()
    tracker.begin_run(run_dir=tmp_path, run_id="rc-1")
    record = tracker.record_llm_call(
        model="m",
        prompt_tokens=2_000_000,
        completion_tokens=500_000,
        input_cost_per_1m=3.0,
        output_cost_per_1m=15.0,
    )
    assert record.source == "pricing_table"
    assert record.cost_usd == pytest.approx(6.0 + 7.5)


def test_cost03c_unknown_cost_is_zero_and_incomplete(tmp_path: Path) -> None:
    tracker = CostTracker()
    tracker.begin_run(run_dir=tmp_path, run_id="rc-1")
    record = tracker.record_llm_call(model="mystery-model", prompt_tokens=1000)
    assert record.source == "unknown"
    assert record.cost_usd == 0.0
    assert tracker.tracking_complete is False
    assert tracker.unknown_models == ("mystery-model",)


def test_cost04_unknown_model_warns_once(tmp_path: Path, caplog) -> None:
    tracker = CostTracker()
    tracker.begin_run(run_dir=tmp_path, run_id="rc-1")
    with caplog.at_level("WARNING", logger="researchclaw.cost_tracker"):
        tracker.record_llm_call(model="mystery", prompt_tokens=1)
        tracker.record_llm_call(model="mystery", prompt_tokens=1)
    warnings = [r for r in caplog.records if "No cost source" in r.getMessage()]
    assert len(warnings) == 1


# ── run lifecycle ──────────────────────────────────────────────


def test_begin_run_is_idempotent_for_same_run(tmp_path: Path) -> None:
    tracker = CostTracker()
    tracker.begin_run(run_dir=tmp_path, run_id="rc-1")
    tracker.record_llm_call(model="m", prompt_tokens=1, provider_cost=1.0)
    tracker.begin_run(run_dir=tmp_path, run_id="rc-1")
    assert tracker.total_cost_usd == pytest.approx(1.0)
    assert len(_read_log(tmp_path)) == 1


def test_begin_run_switches_accumulator(tmp_path: Path) -> None:
    tracker = CostTracker()
    tracker.begin_run(run_dir=tmp_path / "a", run_id="rc-a")
    tracker.record_llm_call(model="m", prompt_tokens=1, provider_cost=2.0)
    tracker.begin_run(run_dir=tmp_path / "b", run_id="rc-b")
    assert tracker.total_cost_usd == 0.0
    assert tracker.run_id == "rc-b"


def test_snapshot_is_json_serialisable(tmp_path: Path) -> None:
    tracker = CostTracker()
    tracker.begin_run(run_dir=tmp_path, run_id="rc-1")
    tracker.record_llm_call(model="m", prompt_tokens=3, provider_cost=0.5)
    snapshot = tracker.snapshot()
    assert json.loads(json.dumps(snapshot))["total_cost_usd"] == 0.5


def test_sum_cost_log_matches_tracker(tmp_path: Path) -> None:
    tracker = CostTracker()
    tracker.begin_run(run_dir=tmp_path, run_id="rc-1")
    tracker.record_llm_call(model="m", prompt_tokens=10, provider_cost=0.25)
    tracker.record_llm_call(model="m", prompt_tokens=20, provider_cost=0.75)
    total, tokens, lines = sum_cost_log(tmp_path)
    assert lines == 2
    assert tokens == 30
    assert total == pytest.approx(tracker.total_cost_usd, abs=1e-6)


def test_sum_cost_log_ignores_corrupt_lines(tmp_path: Path) -> None:
    (tmp_path / COST_LOG_FILENAME).write_text(
        '{"cost_usd": 1.0, "total_tokens": 5}\nnot json\n\n', encoding="utf-8"
    )
    total, tokens, lines = sum_cost_log(tmp_path)
    assert total == 1.0
    assert tokens == 5
    assert lines == 1


# ── COST-05: CostGuard reads the same numbers ──────────────────


def test_cost05_guard_uses_tracker_totals(tmp_path: Path) -> None:
    tracker = get_global_tracker()
    tracker.begin_run(run_dir=tmp_path, run_id="rc-1")
    tracker.record_llm_call(model="m", prompt_tokens=10, provider_cost=6.0)

    guard = CostGuard(budget_usd=10.0, thresholds=(0.5, 0.8, 1.0))
    status = guard.check(tmp_path)
    assert status.total_usd == pytest.approx(6.0)
    assert status.percent_used == pytest.approx(60.0)
    assert status.threshold_breached == "50%"
    assert status.total_tokens == 10


def test_cost05_guard_falls_back_to_log(tmp_path: Path) -> None:
    (tmp_path / COST_LOG_FILENAME).write_text(
        json.dumps({"cost_usd": 2.0, "total_tokens": 7}) + "\n",
        encoding="utf-8",
    )
    guard = CostGuard(budget_usd=10.0)
    status = guard.check(tmp_path)
    assert status.total_usd == pytest.approx(2.0)
    assert status.total_tokens == 7


def test_cost05_guard_reports_incomplete_tracking(tmp_path: Path) -> None:
    tracker = get_global_tracker()
    tracker.begin_run(run_dir=tmp_path, run_id="rc-1")
    tracker.record_llm_call(model="no-price", prompt_tokens=100)

    status = CostGuard(budget_usd=1.0).check(tmp_path)
    assert status.tracking_complete is False
    assert status.total_usd == 0.0


def test_cost05_guard_over_budget(tmp_path: Path) -> None:
    tracker = get_global_tracker()
    tracker.begin_run(run_dir=tmp_path, run_id="rc-1")
    tracker.record_llm_call(model="m", prompt_tokens=1, provider_cost=12.0)
    status = CostGuard(budget_usd=10.0).check(tmp_path)
    assert status.over_budget is True


# ── SPEC-01: runner no longer writes a duplicate stage-09 spec ─


def test_spec01_runner_does_not_generate_stage09_spec() -> None:
    from researchclaw.pipeline import runner

    source = Path(runner.__file__).read_text(encoding="utf-8")
    # Stage 9 legitimately owns exp_plan.yaml; what must be gone is the
    # duplicated spec *generation* and the stage-09 spec path.
    assert 'run_dir / "stage-09" / "experiment_spec.md"' not in source
    assert "generate_spec(" not in source


def test_spec01_runner_reads_stage10_spec() -> None:
    from researchclaw.pipeline import runner

    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert "stage-10*/experiment_spec.md" in source


# ── D6: dead modules are gone ─────────────────────────────────


@pytest.mark.parametrize(
    "module",
    ["researchclaw.pipeline.event_log", "researchclaw.pipeline.pitfall_detector"],
)
def test_d6_dead_modules_do_not_exist(module: str) -> None:
    import importlib.util

    assert importlib.util.find_spec(module) is None
