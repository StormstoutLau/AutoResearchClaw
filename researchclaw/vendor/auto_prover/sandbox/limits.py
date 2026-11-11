"""W8 / B-60: 求值 worker 的资源上限

依据: spec/resource-limits/DESIGN.md D1–D7

两条路径（零新增依赖）:
  · Windows: **Job Object**（`ctypes`）—— `JOB_OBJECT_LIMIT_PROCESS_MEMORY`
    限制提交内存, `JOB_OBJECT_LIMIT_ACTIVE_PROCESS=1` 禁止派生子进程;
  · POSIX: worker **自设** `resource.setrlimit` —— `RLIMIT_AS`（地址空间）
    + `RLIMIT_NOFILE`（句柄）。父进程不设 `preexec_fn`（多线程下不安全）。

⚠ 诚实边界:
  · `RLIMIT_AS` 限**虚拟地址空间**, 与 Windows 的**提交内存**不是同一尺度
    （默认 256 MiB → POSIX 2048 MiB, DESIGN D7）;
  · Windows **无** per-process 句柄上限（只有活动进程数）;
  · 本模块**不做** OS 级网络隔离（B-66）; 求值侧主动防线 = AST 桥跳名
    黑名单（`evaluator._FORBIDDEN_ATTRS`）, 见 `limits_status()` 读数。
"""
from __future__ import annotations

import ctypes
import sys

# 默认提交内存上限（MiB）。实测合法用例峰值 18.43 MiB ⇒ 余量 ≥ 13.8×。
# 0 = 关闭（逃生开关，仅对照实验用）。
DEFAULT_MEMORY_LIMIT_MB = 256

# POSIX `RLIMIT_AS` 换算（DESIGN D7）: 地址空间 ≫ 常驻内存 ⇒ 8× + 2 GiB 下界
POSIX_AS_MULTIPLIER = 8
POSIX_AS_FLOOR_MB = 2048
POSIX_NOFILE_LIMIT = 256

# BLAS/OMP 单线程（DESIGN D3）。不设时 `import numpy` 需约 500 MiB。
THREAD_ENV = {
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
}

_IS_WINDOWS = sys.platform == "win32"

_JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
_JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
_JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def coerce_limit_mb(value) -> int:
    """非负整数校验；非法值回落默认（DESIGN D2/D3）。"""
    try:
        num = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MEMORY_LIMIT_MB
    return num if num >= 0 else DEFAULT_MEMORY_LIMIT_MB


def posix_as_limit_mb(memory_limit_mb: int) -> int:
    """Windows 提交内存上限 → POSIX 地址空间上限（DESIGN D7）。"""
    return max(POSIX_AS_FLOOR_MB, coerce_limit_mb(memory_limit_mb) * POSIX_AS_MULTIPLIER)


def posix_rlimit_available() -> bool:
    try:
        import resource
        return hasattr(resource, "setrlimit")
    except ImportError:
        return False


def apply_worker_env(env: dict, memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB) -> None:
    """注入 BLAS 单线程与 POSIX rlimit 参数（常量覆盖，不读宿主值）。"""
    env.update(THREAD_ENV)
    mb = coerce_limit_mb(memory_limit_mb)
    if not _IS_WINDOWS and mb > 0:
        env["AUTOPROVER_SANDBOX_AS_MB"] = str(posix_as_limit_mb(mb))
        env["AUTOPROVER_SANDBOX_NOFILE"] = str(POSIX_NOFILE_LIMIT)


class WindowsJobLimits:
    """Windows Job Object 封装（懒创建；`close()` 幂等；失败 fail-open）。"""

    def __init__(self, memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB):
        self.memory_limit_mb = coerce_limit_mb(memory_limit_mb)
        self.reason = ""
        self._handle = None
        self._kernel32 = None

    @property
    def active(self) -> bool:
        return self._handle is not None

    def attach(self, proc) -> bool:
        """把已启动的子进程挂到 Job；失败返回 False + `reason`（不抛）。"""
        if not _IS_WINDOWS or self.memory_limit_mb <= 0:
            return False
        try:
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.CreateJobObjectW.restype = ctypes.c_void_p
            k.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
            k.SetInformationJobObject.restype = ctypes.c_int
            k.SetInformationJobObject.argtypes = [
                ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
            k.QueryInformationJobObject.restype = ctypes.c_int
            k.QueryInformationJobObject.argtypes = [
                ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                ctypes.c_uint32, ctypes.c_void_p]
            k.AssignProcessToJobObject.restype = ctypes.c_int
            k.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            k.CloseHandle.restype = ctypes.c_int
            k.CloseHandle.argtypes = [ctypes.c_void_p]

            job = k.CreateJobObjectW(None, None)
            if not job:
                self.reason = "CreateJobObjectW failed"
                return False

            cap = self.memory_limit_mb * 1024 * 1024
            info = _EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = (
                _JOB_OBJECT_LIMIT_PROCESS_MEMORY
                | _JOB_OBJECT_LIMIT_JOB_MEMORY
                | _JOB_OBJECT_LIMIT_ACTIVE_PROCESS)
            info.BasicLimitInformation.ActiveProcessLimit = 1
            info.ProcessMemoryLimit = cap
            info.JobMemoryLimit = cap
            if not k.SetInformationJobObject(
                    job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                    ctypes.byref(info), ctypes.sizeof(info)):
                self.reason = "SetInformationJobObject failed"
                k.CloseHandle(job)
                return False

            handle = ctypes.c_void_p(int(proc._handle))
            if not k.AssignProcessToJobObject(job, handle):
                self.reason = "AssignProcessToJobObject failed"
                k.CloseHandle(job)
                return False

            self._kernel32 = k
            self._handle = job
            return True
        except (OSError, ctypes.ArgumentError) as exc:   # D5: fail-open
            self.reason = f"{type(exc).__name__}: {exc}"
            self._handle = None
            return False

    def query_peak_mb(self) -> float:
        """Job 峰值提交内存（测试/诊断用；不可用 ⇒ -1.0）。"""
        if self._handle is None or self._kernel32 is None:
            return -1.0
        try:
            info = _EXTENDED_LIMIT_INFORMATION()
            ok = self._kernel32.QueryInformationJobObject(
                self._handle, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(info), ctypes.sizeof(info), None)
            return info.PeakProcessMemoryUsed / (1024.0 * 1024.0) if ok else -1.0
        except (OSError, ctypes.ArgumentError):
            return -1.0

    def close(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is not None and self._kernel32 is not None:
            try:
                self._kernel32.CloseHandle(handle)
            except (OSError, ctypes.ArgumentError):
                pass  # 已无效的句柄 ⇒ 无操作
        self._kernel32 = None
