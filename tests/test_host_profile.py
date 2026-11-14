"""Contract tests for the read-only HostProfile snapshot (M0 §8)."""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path

import pytest

from researchclaw.runtime.host_profile import HostProfile, detect_host_profile


def test_t1_shape_and_scalar_only_payload() -> None:
    profile = detect_host_profile(toolchains=())
    payload = profile.as_dict()
    assert set(payload) == {
        "cpu_count",
        "memory_total_mb",
        "disk_free_gb",
        "gpu_devices",
        "toolchains",
    }
    assert isinstance(payload["gpu_devices"], list)
    assert isinstance(payload["toolchains"], dict)
    assert profile.cpu_count >= 0
    assert profile.memory_total_mb >= 0
    assert profile.disk_free_gb >= 0.0
    assert all(not callable(value) for value in payload.values())


def test_detect_requires_keyword_arguments_and_defaults() -> None:
    import inspect

    with pytest.raises(TypeError):
        detect_host_profile(Path.cwd())  # type: ignore[misc]

    parameters = inspect.signature(detect_host_profile).parameters
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters.values())
    assert parameters["disk_root"].default is None
    assert parameters["toolchains"].default == ("python", "docker", "git")


def test_t1_snapshot_is_frozen() -> None:
    profile = detect_host_profile(toolchains=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        profile.cpu_count = 1  # type: ignore[misc]


def test_t2_invalid_toolchain_rejected_before_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(ValueError):
        detect_host_profile(toolchains=("python; rm -rf /",))
    assert calls == []


def test_t3_successful_toolchain_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd, **kwargs):  # noqa: ANN001
        if cmd[0] == "python":
            return subprocess.CompletedProcess(cmd, 0, "Python 3.11.9\n", "")
        return subprocess.CompletedProcess(cmd, 127, "", "not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    profile = detect_host_profile(
        toolchains=("python", "docker"), disk_root=Path.cwd()
    )
    assert profile.toolchains == {"python": "Python 3.11.9"}


def test_t3_probe_exception_is_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd, **kwargs):  # noqa: ANN001
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert detect_host_profile(toolchains=("git",)).toolchains == {}


def test_t3_probe_uses_allowlist_env(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        seen.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, "git version 2.0\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    detect_host_profile(toolchains=("git",))
    assert seen.get("shell") is not True
    assert "env" in seen
    assert seen.get("env") is not None


def test_t4_as_dict_returns_copies() -> None:
    profile = HostProfile(
        cpu_count=1,
        memory_total_mb=2,
        disk_free_gb=3.0,
        gpu_devices=("gpu0",),
        toolchains={"python": "3"},
    )
    payload = profile.as_dict()
    payload["gpu_devices"].append("gpu1")
    payload["toolchains"]["python"] = "9"
    assert profile.gpu_devices == ("gpu0",)
    assert profile.toolchains == {"python": "3"}


def test_t4_gpu_devices_come_from_hardware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "researchclaw.runtime.host_profile.list_gpu_devices",
        lambda: ("GPU 0: Test (UUID: x)",),
    )
    assert detect_host_profile(toolchains=()).gpu_devices == ("GPU 0: Test (UUID: x)",)


def test_list_gpu_devices_parses_all_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    from researchclaw import hardware

    seen: dict[str, object] = {}

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        seen["cmd"] = cmd
        seen.update(kwargs)
        return subprocess.CompletedProcess(
            cmd, 0, "GPU 0: A (UUID: x)\n\nGPU 1: B (UUID: y)\n", ""
        )

    monkeypatch.setattr(hardware.subprocess, "run", fake_run)
    assert hardware.list_gpu_devices() == ("GPU 0: A (UUID: x)", "GPU 1: B (UUID: y)")
    assert seen["cmd"] == ["nvidia-smi", "-L"]
    assert seen["timeout"] == 10
    assert seen["check"] is False
    assert seen.get("shell") is not True


def test_list_gpu_devices_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    from researchclaw import hardware

    def missing(cmd, **kwargs):  # noqa: ANN001
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(hardware.subprocess, "run", missing)
    assert hardware.list_gpu_devices() == ()

    monkeypatch.setattr(
        hardware.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 1, "", "boom"),
    )
    assert hardware.list_gpu_devices() == ()


def test_detect_nvidia_first_line_behaviour_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from researchclaw import hardware

    monkeypatch.setattr(
        hardware.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(
            cmd, 0, "NVIDIA A, 1000\nNVIDIA B, 2000\n", ""
        ),
    )
    profile = hardware._detect_nvidia()
    assert profile is not None
    assert profile.gpu_name == "NVIDIA A"
    assert profile.vram_mb == 1000


def test_t4_disk_failure_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    import researchclaw.runtime.host_profile as host_profile

    def boom(path: str):  # noqa: ANN001
        raise OSError("unavailable")

    monkeypatch.setattr(host_profile.shutil, "disk_usage", boom)
    assert host_profile.detect_host_profile(toolchains=()).disk_free_gb == 0.0
