"""Read-only host snapshot (M0 §8): no policy, no callables."""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from researchclaw.hardware import list_gpu_devices
from researchclaw.utils.env import build_subprocess_env

_TOOLCHAIN_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


@dataclass(frozen=True)
class HostProfile:
    """Read-only host snapshot. No policy, no callables (M0 §8)."""

    cpu_count: int
    memory_total_mb: int
    disk_free_gb: float
    gpu_devices: tuple[str, ...]
    toolchains: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "cpu_count": self.cpu_count,
            "memory_total_mb": self.memory_total_mb,
            "disk_free_gb": self.disk_free_gb,
            "gpu_devices": list(self.gpu_devices),
            "toolchains": dict(self.toolchains),
        }


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _memory_total_mb() -> int:
    if os.name == "nt":
        try:
            status = _MemoryStatusEx()
            status.dwLength = ctypes.sizeof(_MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys // (1024 * 1024))
        except (AttributeError, OSError, ValueError):
            return 0
        return 0
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(pages * page_size // (1024 * 1024))
    except (AttributeError, OSError, ValueError):
        return 0


def _disk_free_gb(root: Path) -> float:
    try:
        return shutil.disk_usage(str(root)).free / 2**30
    except OSError:
        return 0.0


def _probe_toolchain(name: str) -> str | None:
    try:
        result = subprocess.run(
            [name, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
            env=build_subprocess_env(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    for stream in (result.stdout or "", result.stderr or ""):
        for line in stream.splitlines():
            if line.strip():
                return line.strip()
    return None


def detect_host_profile(
    *,
    disk_root: Path | None = None,
    toolchains: tuple[str, ...] = ("python", "docker", "git"),
) -> HostProfile:
    """Probe the host once and return an immutable snapshot."""
    for name in toolchains:
        if not _TOOLCHAIN_RE.match(name):
            raise ValueError(f"invalid toolchain name: {name!r}")

    root = Path(disk_root) if disk_root is not None else Path.cwd()
    detected: dict[str, str] = {}
    for name in toolchains:
        version = _probe_toolchain(name)
        if version is not None:
            detected[name] = version

    return HostProfile(
        cpu_count=os.cpu_count() or 0,
        memory_total_mb=_memory_total_mb(),
        disk_free_gb=_disk_free_gb(root),
        gpu_devices=tuple(list_gpu_devices()),
        toolchains=detected,
    )
