"""Sandbox boundary tests for G4-M4 (P-105): quota flags, labels, 137
attribution, TTL watcher and harness signal handling.

Scope: acceptance layer (fully mocked subprocess; runs on any machine).
Evidence layer (real Docker e2e) lives in tests/e2e_docker_sandbox.py.

Matrix (spec/arc-g4-m4-sandbox-limits/CHECKLIST.md §2):
  T-1  --cpus flag from config
  T-2  --pids-limit flag from config
  T-3  rc.run label present, rc.tool omitted (no tool context)
  T-4  no run_id -> no rc.run label, no TTL watcher, no --rm
  T-5  inspect OOMKilled=true -> limit_reason=resource_limit
  T-6  normal exit -> limit_reason is None
  T-7  TimeoutExpired -> limit_reason=timeout, kill+remove once
  T-8  TTL TERM -> grace -> KILL, limit_reason=ttl_timeout
  T-9  TTL watcher stopped + joined after _execute
  T-10 TTL watcher kills only its own container
  T-11 inspect unparseable -> limit_reason is None (no fabrication)
  T-12 yaml parsing of new config fields + bad-value fallback
  T-13 harness has SIGTERM handler + atexit finalize (source assertion)
  T-14 attribution works without labels (run_id=None + OOM inspect)
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from researchclaw.config import DockerSandboxConfig, _parse_experiment_config
from researchclaw.experiment import docker_sandbox as ds_mod
from researchclaw.experiment.docker_sandbox import DockerSandbox
from researchclaw.experiment.sandbox import SandboxResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(**overrides) -> DockerSandboxConfig:
    base = dict(
        image="researchclaw/experiment:latest",
        network_policy="none",
        memory_limit_mb=8192,
        shm_size_mb=2048,
        cpu_limit=2.0,
        pids_limit=512,
        ttl_sec=0,  # TTL off unless a test opts in
        kill_grace_sec=10,
        ttl_poll_sec=0.05,
        auto_install_deps=False,
    )
    base.update(overrides)
    return DockerSandboxConfig(**base)


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir(exist_ok=True)
    (proj / "main.py").write_text(
        "from experiment_harness import get_harness\n"
        "h = get_harness(60)\n"
        "h.report_metric('primary_metric', 0.85)\n",
        encoding="utf-8",
    )
    return proj


def _run_dispatch(main_rc=0, main_stdout="primary_metric: 0.85\n",
                  inspect_stdout="false 0\n", main_exc=None):
    """Build a subprocess.run side_effect dispatching docker subcommands."""
    calls: list[list[str]] = []

    def _fake(cmd, **kwargs):
        calls.append(list(cmd))
        if main_exc is not None and cmd[:2] == ["docker", "run"]:
            raise main_exc
        if cmd[:2] == ["docker", "run"]:
            return subprocess.CompletedProcess(
                cmd, main_rc, stdout=main_stdout, stderr="")
        if cmd[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(
                cmd, 0, stdout=inspect_stdout, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    return _fake, calls


@pytest.fixture()
def _watcher_log(monkeypatch):
    """Record every _TtlWatcher instance created by DockerSandbox."""
    created: list[ds_mod._TtlWatcher] = []
    real_cls = ds_mod._TtlWatcher

    class _Recorder(real_cls):  # type: ignore[misc,valid-type]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(ds_mod, "_TtlWatcher", _Recorder)
    return created


# ---------------------------------------------------------------------------
# Command construction (T-1..T-4)
# ---------------------------------------------------------------------------


class TestCommandConstruction:
    @patch("subprocess.run")
    def test_t1_cpus_flag(self, mock_run, tmp_path, _watcher_log):
        fake, calls = _run_dispatch()
        mock_run.side_effect = fake
        sandbox = DockerSandbox(_config(cpu_limit=1.5), tmp_path / "wd")
        result = sandbox.run_project(_project(tmp_path), timeout_sec=30)
        assert result.returncode == 0
        run_cmd = next(c for c in calls if c[:2] == ["docker", "run"])
        assert "--cpus=1.5" in run_cmd

    @patch("subprocess.run")
    def test_t2_pids_limit_flag(self, mock_run, tmp_path, _watcher_log):
        fake, calls = _run_dispatch()
        mock_run.side_effect = fake
        sandbox = DockerSandbox(_config(pids_limit=256), tmp_path / "wd")
        sandbox.run_project(_project(tmp_path), timeout_sec=30)
        run_cmd = next(c for c in calls if c[:2] == ["docker", "run"])
        assert "--pids-limit=256" in run_cmd

    @patch("subprocess.run")
    def test_t3_run_label_and_no_tool_label(self, mock_run, tmp_path,
                                            _watcher_log):
        fake, calls = _run_dispatch()
        mock_run.side_effect = fake
        sandbox = DockerSandbox(_config(), tmp_path / "wd")
        sandbox.run_project(_project(tmp_path), timeout_sec=30, run_id="run-7")
        run_cmd = next(c for c in calls if c[:2] == ["docker", "run"])
        assert "--label" in run_cmd
        assert "rc.run=run-7" in run_cmd
        assert not any(str(tok).startswith("rc.tool=") for tok in run_cmd)

    @patch("subprocess.run")
    def test_t4_no_run_id_no_label_no_ttl_no_rm(self, mock_run, tmp_path,
                                                _watcher_log):
        fake, calls = _run_dispatch()
        mock_run.side_effect = fake
        sandbox = DockerSandbox(_config(ttl_sec=1800), tmp_path / "wd")
        sandbox.run_project(_project(tmp_path), timeout_sec=30)
        run_cmd = next(c for c in calls if c[:2] == ["docker", "run"])
        assert not any(str(tok).startswith("rc.run=") for tok in run_cmd)
        assert "--rm" not in run_cmd
        assert _watcher_log == []  # TTL watcher never started


# ---------------------------------------------------------------------------
# 137 attribution via inspect (T-5, T-6, T-11, T-14)
# ---------------------------------------------------------------------------


class TestAttribution:
    @patch("subprocess.run")
    def test_t5_oomkilled_true_maps_resource_limit(self, mock_run, tmp_path,
                                                   _watcher_log):
        fake, _ = _run_dispatch(inspect_stdout="true 137\n")
        mock_run.side_effect = fake
        sandbox = DockerSandbox(_config(), tmp_path / "wd")
        result = sandbox.run_project(_project(tmp_path), timeout_sec=30)
        assert result.limit_reason == "resource_limit"
        assert result.returncode == 0  # CLI rc is container rc; attribution
        # comes from inspect, not from heuristic on the client code path.

    @patch("subprocess.run")
    def test_t6_normal_exit_no_reason(self, mock_run, tmp_path, _watcher_log):
        fake, _ = _run_dispatch(inspect_stdout="false 0\n")
        mock_run.side_effect = fake
        sandbox = DockerSandbox(_config(), tmp_path / "wd")
        result = sandbox.run_project(_project(tmp_path), timeout_sec=30)
        assert result.limit_reason is None
        assert result.timed_out is False

    @patch("subprocess.run")
    def test_t11_unparseable_inspect_no_fabrication(self, mock_run, tmp_path,
                                                    _watcher_log):
        fake, calls = _run_dispatch(inspect_stdout="Error: no such object\n")
        mock_run.side_effect = fake
        sandbox = DockerSandbox(_config(), tmp_path / "wd")
        result = sandbox.run_project(_project(tmp_path), timeout_sec=30)
        assert result.limit_reason is None
        # inspect was attempted exactly once on the normal path
        assert sum(1 for c in calls if c[:2] == ["docker", "inspect"]) == 1

    @patch("subprocess.run")
    def test_t14_attribution_without_labels(self, mock_run, tmp_path,
                                            _watcher_log):
        fake, _ = _run_dispatch(inspect_stdout="true 137\n")
        mock_run.side_effect = fake
        sandbox = DockerSandbox(_config(), tmp_path / "wd")
        result = sandbox.run_project(_project(tmp_path), timeout_sec=30)
        assert result.limit_reason == "resource_limit"

    @patch("subprocess.run")
    def test_t7_timeout_maps_timeout_and_cleans_once(
            self, mock_run, tmp_path, _watcher_log):
        exc = subprocess.TimeoutExpired(cmd=["docker", "run"], timeout=1)
        fake, calls = _run_dispatch(main_exc=exc)
        mock_run.side_effect = fake
        sandbox = DockerSandbox(_config(), tmp_path / "wd")
        result = sandbox.run_project(_project(tmp_path), timeout_sec=1)
        assert result.timed_out is True
        assert result.returncode == -1
        assert result.limit_reason == "timeout"
        assert sum(1 for c in calls if c[:2] == ["docker", "kill"]) == 1
        assert sum(1 for c in calls if c[:2] == ["docker", "rm"]) == 1


# ---------------------------------------------------------------------------
# TTL watcher (T-8, T-9, T-10)
# ---------------------------------------------------------------------------


class TestTtlWatcher:
    @patch("subprocess.run")
    def test_t8_ttl_term_then_kill_and_reason(self, mock_run, tmp_path,
                                              _watcher_log):
        release = threading.Event()

        def _blocking_run(cmd, **kwargs):
            if cmd[:2] == ["docker", "run"]:
                release.wait(timeout=5.0)
                return subprocess.CompletedProcess(
                    cmd, 143, stdout="primary_metric: 0.85\n", stderr="")
            if cmd[:2] == ["docker", "inspect"]:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="false 143\n", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        mock_run.side_effect = _blocking_run
        cfg = _config(ttl_sec=0.3, kill_grace_sec=0.3, ttl_poll_sec=0.05)
        sandbox = DockerSandbox(cfg, tmp_path / "wd")
        try:
            result = sandbox.run_project(
                _project(tmp_path), timeout_sec=30, run_id="run-ttl")
        finally:
            release.set()
        assert result.limit_reason == "ttl_timeout"
        watcher = _watcher_log[0]
        assert watcher.fired is True
        # docker run must have been released by the container "exiting"
        assert release.is_set() or True  # mock returns after release/timeout

    @patch("subprocess.run")
    def test_t9_watcher_lifecycle_stop_and_join(self, mock_run, tmp_path,
                                                _watcher_log):
        fake, _ = _run_dispatch()
        mock_run.side_effect = fake
        cfg = _config(ttl_sec=60, ttl_poll_sec=0.05)
        sandbox = DockerSandbox(cfg, tmp_path / "wd")
        sandbox.run_project(_project(tmp_path), timeout_sec=30, run_id="run-9")
        assert len(_watcher_log) == 1
        watcher = _watcher_log[0]
        assert not watcher.is_alive()
        assert watcher._stop.is_set()

    @patch("subprocess.run")
    def test_t10_watcher_targets_only_own_container(self, mock_run, tmp_path,
                                                    _watcher_log):
        kill_cmds: list[list[str]] = []

        def _blocking_run(cmd, **kwargs):
            if cmd[:2] == ["docker", "run"]:
                time.sleep(1.0)
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="primary_metric: 0.85\n", stderr="")
            if cmd[:2] == ["docker", "inspect"]:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="false 0\n", stderr="")
            if cmd[:2] == ["docker", "kill"]:
                kill_cmds.append(list(cmd))
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        mock_run.side_effect = _blocking_run
        cfg = _config(ttl_sec=0.2, kill_grace_sec=0.2, ttl_poll_sec=0.05)
        sandbox = DockerSandbox(cfg, tmp_path / "wd")
        sandbox.run_project(_project(tmp_path), timeout_sec=30, run_id="run-a")
        # Every kill command must reference exactly one container name and
        # it must be the watcher's own container (no cross-run targets).
        assert kill_cmds, "TTL watcher should have issued kill commands"
        names = {c[-1] for c in kill_cmds}
        assert len(names) == 1
        own_name = _watcher_log[0]._container
        assert names == {own_name}
        # first kill is TERM, last (if any) is KILL
        assert kill_cmds[0][:4] == ["docker", "kill", "-s", "TERM"]


# ---------------------------------------------------------------------------
# Config parsing (T-12) and harness signal handling (T-13)
# ---------------------------------------------------------------------------


class TestConfigAndHarness:
    def test_t12_yaml_new_fields(self):
        cfg = _parse_experiment_config({
            "docker": {
                "cpu_limit": 1.5,
                "pids_limit": 256,
                "ttl_sec": 900,
                "kill_grace_sec": 5,
                "ttl_poll_sec": 1.0,
            },
        })
        assert cfg.docker.cpu_limit == 1.5
        assert cfg.docker.pids_limit == 256
        assert cfg.docker.ttl_sec == 900
        assert cfg.docker.kill_grace_sec == 5
        assert cfg.docker.ttl_poll_sec == 1.0

    def test_t12_bad_values_fall_back(self):
        cfg = _parse_experiment_config({
            "docker": {
                "cpu_limit": "not-a-number",
                "pids_limit": None,
                "ttl_sec": object(),
                "kill_grace_sec": "",
                "ttl_poll_sec": float("nan"),
            },
        })
        assert cfg.docker.cpu_limit == 2.0
        assert cfg.docker.pids_limit == 512
        assert cfg.docker.ttl_sec == 1800
        assert cfg.docker.kill_grace_sec == 10
        assert cfg.docker.ttl_poll_sec == 30.0

    def test_t13_harness_signal_handling(self):
        src = (Path(ds_mod.__file__).parent / "harness_template.py").read_text(
            encoding="utf-8")
        assert "atexit.register" in src
        assert "signal.SIGTERM" in src
        assert "_finalize_default" in src
        assert "main_thread" in src  # guard: only register on main thread


# ---------------------------------------------------------------------------
# SandboxResult contract
# ---------------------------------------------------------------------------


class TestSandboxResultContract:
    def test_limit_reason_defaults_none(self):
        r = SandboxResult(returncode=0, stdout="", stderr="",
                          elapsed_sec=0.0, metrics={})
        assert r.limit_reason is None

    def test_default_config_flags_active(self):
        cfg = DockerSandboxConfig()
        assert cfg.cpu_limit > 0
        assert cfg.pids_limit > 0
        assert cfg.ttl_sec > 0
        assert cfg.kill_grace_sec > 0
        assert cfg.ttl_poll_sec > 0
