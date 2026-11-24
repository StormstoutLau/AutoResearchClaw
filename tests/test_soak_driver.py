"""Soak driver/report/CLI (A7-1 scaled, P-160)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from researchclaw.cli import main, parse_duration
from researchclaw.runtime.lease import read_lease
from researchclaw.soak.driver import SoakConfig, SoakDriver
from researchclaw.soak.report import build_report, render_markdown, write_report

REPO_ROOT = Path(__file__).resolve().parents[1]

FAKE_WORKER = r'''
import json, os, sys, time
from pathlib import Path

def atomic(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    last = None
    for _ in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError as exc:
            last = exc
            time.sleep(0.02)
    raise last

def main():
    repo = sys.argv[4]
    sys.path.insert(0, repo)
    from researchclaw.runtime.event_log import EventLog
    from researchclaw.runtime.lease import acquire, release

    run_dir = Path(sys.argv[1])
    total = int(sys.argv[2])
    fail_after = int(sys.argv[3])
    lease = acquire(run_dir, owner="fake:%d" % os.getpid(), ttl=60)
    log = EventLog(run_dir, run_dir.name, fencing=lease.fencing, fsync=False)
    log.append("run.started", {"fake": True})
    cp = run_dir / "checkpoint.json"
    start = 1
    if cp.exists():
        try:
            start = int(json.loads(cp.read_text(encoding="utf-8"))["last_completed_stage"]) + 1
        except Exception:
            start = 1
    for stage in range(start, total + 1):
        time.sleep(0.04)
        atomic(cp, {
            "last_completed_stage": stage,
            "last_completed_name": "S%d" % stage,
            "run_id": run_dir.name,
            "timestamp": "2026-01-01T00:00:00+00:00",
        })
        log.append("stage.completed", {"name": "S%d" % stage, "stage": stage}, stage=stage)
        atomic(run_dir / "heartbeat.json", {
            "pid": os.getpid(), "last_stage": stage, "last_stage_name": "S%d" % stage,
            "run_id": run_dir.name, "timestamp": "2026-01-01T00:00:00+00:00",
        })
        if fail_after and stage == fail_after:
            release(run_dir, lease)
            sys.exit(65)
    atomic(run_dir / "pipeline_summary.json", {
        "run_id": run_dir.name, "final_status": "done", "final_stage": total,
        "stages_executed": total, "stages_done": total,
        "generated": "2026-01-01T00:00:00+00:00",
    })
    release(run_dir, lease)
    sys.exit(0)

if __name__ == "__main__":
    main()
'''


def _worker(tmp_path: Path) -> Path:
    path = tmp_path / "fake_worker.py"
    path.write_text(FAKE_WORKER, encoding="utf-8")
    return path


def _config(tmp_path: Path, *, inject=(), max_restarts=3, duration=30.0,
            total=8, fail_after=0, poll=0.01, min_interval=0.0,
            lease_timeout=10.0) -> SoakConfig:
    run_dir = tmp_path / ("run-%d" % len(list(tmp_path.glob("run-*"))))
    run_dir.mkdir()
    worker = _worker(tmp_path)
    return SoakConfig(
        run_dir=run_dir,
        worker_cmd=(sys.executable, str(worker), str(run_dir), str(total),
                    str(fail_after), str(REPO_ROOT)),
        duration_seconds=duration,
        max_restarts=max_restarts,
        inject_at_stages=tuple(inject),
        poll_seconds=poll,
        min_restart_interval_seconds=min_interval,
        worker_exit_timeout_seconds=10.0,
        lease_clear_timeout_seconds=lease_timeout,
        worker_cwd=REPO_ROOT,
    )


def _run(tmp_path: Path, **kwargs):
    cfg = _config(tmp_path, **kwargs)
    driver = SoakDriver(cfg)
    return cfg, driver, driver.run()


def test_driver_three_injections_converge_like_baseline(tmp_path):
    baseline_cfg, _, baseline = _run(tmp_path, inject=())
    assert baseline.status == "passed", baseline.verification.problems
    soak_cfg, driver, result = _run(tmp_path, inject=(2, 4, 6), max_restarts=3)

    assert result.status == "passed", (result.status, result.verification.problems, driver.session)
    assert len(result.restarts) == 3
    assert all(r.reason == "injected" for r in result.restarts)
    assert result.verification.converged
    assert result.verification.chain_ok
    assert result.verification.seq_gaps == ()
    assert result.verification.event_checkpoint_skew >= 0
    assert result.verification.convergence_signature == baseline.verification.convergence_signature
    assert not result.field_run_satisfied
    assert any(e["event"] == "restart_injected" for e in driver.session)
    assert any(e["event"] == "stale_lease_released" for e in driver.session)
    lease = read_lease(soak_cfg.run_dir)
    assert lease is None or lease.released or not __import__(
        "researchclaw.runtime.lease", fromlist=["is_pid_alive"]
    ).is_pid_alive(lease.pid)


def test_driver_caps_injected_restarts(tmp_path):
    cfg, driver, result = _run(tmp_path, inject=(2, 4, 6, 8), max_restarts=2)

    assert result.status == "passed", result.verification.problems
    assert len(result.restarts) == 2
    assert any(e["event"] == "restart_capped" for e in driver.session)


def test_driver_does_not_restart_data_error(tmp_path):
    cfg, driver, result = _run(tmp_path, inject=(), fail_after=1)

    assert result.status == "failed"
    assert result.restarts == []
    assert not result.verification.converged
    assert not any(e["event"] == "worker_started" and e.get("attempt", 1) > 1
                   for e in driver.session)


def test_driver_reclaims_stale_lease(tmp_path):
    cfg, driver, result = _run(tmp_path, inject=(2,), max_restarts=1)

    assert result.status == "passed", result.verification.problems
    assert any(e["event"] == "stale_lease_released" for e in driver.session)
    lease = read_lease(cfg.run_dir)
    assert lease is None or lease.released


def test_driver_rejects_missing_run_dir(tmp_path):
    from researchclaw.soak.driver import SoakConfig, SoakDriver

    missing = tmp_path / "missing"
    cfg = SoakConfig(run_dir=missing, worker_cmd=(sys.executable, "-c", "pass"),
                     duration_seconds=1.0)
    result = SoakDriver(cfg).run()

    assert result.status == "failed"
    assert "run_dir_missing" in result.verification.problems
    assert not missing.exists()


def test_driver_times_out_without_completion(tmp_path):
    cfg, driver, result = _run(tmp_path, inject=(), duration=0.06, total=8)

    assert result.status == "timed_out"
    assert not result.verification.converged


def test_driver_does_not_override_live_lease(tmp_path):
    from researchclaw.runtime.lease import acquire
    import os

    cfg = _config(tmp_path, inject=(), duration=5.0, lease_timeout=0.05)
    acquire(cfg.run_dir, owner="live:%d" % os.getpid(), ttl=60)
    result = SoakDriver(cfg).run()

    assert result.status == "failed"
    assert any(e["event"] == "lease_held" for e in result.session)
    assert not any(e["event"] == "worker_started" for e in result.session)


def test_report_contains_required_readings(tmp_path):
    cfg, driver, result = _run(tmp_path, inject=(2, 4, 6), max_restarts=3)
    report = build_report(result, driver.session, cfg)

    assert report["schema"] == "arc-soak-report/1"
    assert report["restart_count"] == 3
    assert report["injected_restarts"] == 3
    assert report["recovery_seconds"]["count"] >= 1
    assert report["requirements"]["restarts_satisfied"] is True
    assert report["field_run"]["satisfied"] is False
    assert report["verification"]["chain_ok"] is True
    assert report["failure_stages"] == {}

    markdown = render_markdown(report)
    for heading in ("## Summary", "## Restarts", "## Recovery",
                    "## Failure stages", "## Event replay", "## Convergence"):
        assert heading in markdown

    json_path, md_path = write_report(cfg.run_dir, report)
    assert json_path.is_file() and md_path.is_file()
    assert not list(cfg.run_dir.glob("*.tmp"))


def test_parse_duration_units():
    assert parse_duration("72h") == 72 * 3600
    assert parse_duration("90m") == 90 * 60
    assert parse_duration("5s") == 5
    assert parse_duration("7") == 7
    with pytest.raises(ValueError):
        parse_duration("abc")
    with pytest.raises(ValueError):
        parse_duration("0s")


def test_cli_soak_verify_exit_codes(tmp_path):
    cfg, _, result = _run(tmp_path, inject=())
    assert result.status == "passed"

    assert main(["soak", "verify", "--output", str(cfg.run_dir)]) == 0

    path = cfg.run_dir / "events.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines = [line for line in lines if '"seq":2' not in line]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert main(["soak", "verify", "--output", str(cfg.run_dir)]) == 1


def test_cli_soak_report_rerenders(tmp_path):
    cfg, driver, result = _run(tmp_path, inject=())
    report = build_report(result, driver.session, cfg)
    write_report(cfg.run_dir, report)
    markdown = cfg.run_dir / "soak_report.md"
    markdown.unlink()

    assert main(["soak", "report", "--output", str(cfg.run_dir)]) == 0
    assert markdown.is_file()


def test_cli_rejects_bad_duration(tmp_path):
    cfg = _config(tmp_path)
    assert main(["soak", "run", "--output", str(cfg.run_dir),
                 "--duration", "abc"]) == 2
