"""W2 / B-53: 求值隔离 —— AST 白名单 + 子进程 worker + 双超时

依据: spec/sandbox-isolation/DESIGN.md D1–D10 / IMPLEMENTATION.md §3.1

三层防护（缺一不可）:
  1. **AST 白名单**（父进程）: 先于执行拒绝越权节点/dunder 名/dunder 属性;
  2. **子进程 worker**: 表达式不在宿主进程内执行 ⇒ 崩溃/死循环不拖垮管线;
  3. **父侧超时**（reader 线程 + `queue.get(timeout=)`）: Windows 管道不支持
     `select`，子进程自报超时不可信 ⇒ 超时判定必须在父进程做。

⚠ 诚实边界: 内存/进程数上限见 `limits.py`（W8/B-60）；**不做** OS 级网络隔离
   （B-66）。本批（W10）只加 AST **桥跳名黑名单**（`_FORBIDDEN_ATTRS`），
   并把 `network_isolation="ast-deny-list"` 作为只读读数暴露；它不是 OS 级隔离。
   内存上限**不替代**墙钟超时 —— `9**9**9` 的结果本身在 cap 之内,
   仍需父侧超时（RESEARCH §3.5）。
"""
from __future__ import annotations

import ast
import json
import os
import queue
import shutil
import site
import subprocess
import sys
import tempfile
import threading
import time

from .limits import (
    DEFAULT_MEMORY_LIMIT_MB,
    WindowsJobLimits,
    apply_worker_env,
    coerce_limit_mb,
    posix_rlimit_available,
)

# 表达式长度闸（D2 第 1 步）: 超长即拒，避免解析/传输放大
MAX_EXPR_CHARS = 4096
# 单次求值超时（D6 / D-W2-2；可由 config 覆盖，非法值回落此默认）
DEFAULT_TIMEOUT_S = 2.0
# 单批预算（判定路径 15 例；D-W2-2）
DEFAULT_BATCH_BUDGET_S = 10.0
# 单次反例搜索预算（D-W2-2）
DEFAULT_SEARCH_BUDGET_S = 30.0

# worker 引导（协议版本 v1；变更即协议变更，需同步测试）
#   · 请求: 一行 JSON {"expr", "params", "expected", "tolerance"}
#   · 响应: 一行 JSON {"ok": true, "value": <float>} 或
#           {"ok": false, "error": "<ExceptionType>", "detail": "..."}
#   · `loc["params"] = params`: 既有 `_IDENTITY_EXPR` 形态用 `params[...]` 取键;
#     `loc` 同时展开键名（LLM 常写裸 `n + 0`）。
#   · globals 只给 `np` 且 `__builtins__` 置空 —— 与收口前语义逐位一致。
_WORKER_PREAMBLE = r'''
import os, sys

_mb = 0
try:
    _mb = int(os.environ.get("AUTOPROVER_SANDBOX_AS_MB", "0") or 0)
except (TypeError, ValueError):
    _mb = 0
_nofile = 0
try:
    _nofile = int(os.environ.get("AUTOPROVER_SANDBOX_NOFILE", "0") or 0)
except (TypeError, ValueError):
    _nofile = 0
if _mb > 0 or _nofile > 0:
    try:
        import resource
        if _mb > 0:
            _lim = _mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (_lim, _lim))
        if _nofile > 0:
            resource.setrlimit(resource.RLIMIT_NOFILE, (_nofile, _nofile))
    except (ImportError, ValueError, OSError):
        pass  # Windows 无 resource / 设限越界 ⇒ 释放，父侧 fail-open
'''

_WORKER = _WORKER_PREAMBLE + r'''
import json
import numpy as np

def _send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

while True:
    line = sys.stdin.readline()
    if not line:
        break
    try:
        req = json.loads(line)
        params = dict(req.get("params") or {})
        loc = dict(params)
        loc["params"] = params
        loc["expected"] = req.get("expected", 0.0)
        loc["tolerance"] = req.get("tolerance", 0.0)
        code = compile("computed = " + req["expr"], "<sandbox>", "exec")
        exec(code, {"np": np, "__builtins__": {}}, loc)
        _send({"ok": True, "value": float(loc.get("computed", 0.0))})
    except BaseException as exc:
        # D9: BaseException（含 SystemExit/KeyboardInterrupt）视为请求失败并回传,
        #     否则 worker 会静默退出、父侧只能看到 EOF。
        _send({"ok": False, "error": type(exc).__name__,
               "detail": str(exc)[:300]})
'''

# 允许的 AST 节点（D2）。比 DESIGN 的清单多两项，均已在上游兼容矩阵出现:
#   · ast.keyword —— `normal(loc=..., scale=..., size=...)` 的关键字实参;
#   · ast.Store   —— 列表/生成器推导的目标名上下文（值不可写，无逃逸面）。
_ALLOWED_NODES = frozenset(
    [
        ast.Expression, ast.Constant, ast.Name, ast.Load, ast.Store,
        ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
        ast.Call, ast.keyword, ast.Attribute, ast.Subscript, ast.Slice,
        ast.Tuple, ast.List, ast.Dict, ast.IfExp,
        ast.comprehension, ast.ListComp, ast.GeneratorExp,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
        ast.UAdd, ast.USub, ast.Not, ast.And, ast.Or,
        ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ]
)


# B-66 / W10: native / 进程 / 网络桥的**跳名**黑名单（D1）。
# 依据 spec/safety-residuals/RESEARCH.md §2.1: 任何到达 ctypes / os / subprocess /
# 下载对象的属性链都必须经过下列名字之一 ⇒ 在 AST 层截断, 不依赖模块身份。
# ⚠ 启发式: 未枚举的桥跳名仍可能穿透（OS 级网络隔离仍属 B-66 未达成）。
_FORBIDDEN_ATTRS = frozenset({
    # FFI / ctypes 家族
    "ctypeslib", "ctypes", "CDLL", "PyDLL", "WinDLL",
    "windll", "oledll", "LoadLibrary", "load_library",
    "from_address", "from_buffer",
    # 进程 / 系统（f2py / testing.extbuild 桥）
    "os", "sys", "subprocess", "Popen", "system", "popen", "spawn",
    # 网络 / 下载
    "DataSource", "urlopen", "socket",
    # 动态导入 / 反序列化
    "importlib", "builtins", "pickle",
})


class UnsafeExpressionError(ValueError):
    """表达式未通过 AST 白名单 / 长度闸（fail-closed）。"""


class EvaluationError(RuntimeError):
    """worker 内执行失败（异常回传，不返回哨兵值）。"""


class EvaluationTimeout(EvaluationError):
    """单次求值超时或批预算耗尽。"""


class WorkerCrashed(EvaluationError):
    """worker 进程意外退出（EOF）。"""


def _coerce_positive(value, default: float) -> float:
    """正数校验：非数值/≤0 回落默认（D6 回退点，不抛异常）。"""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    return num if num > 0.0 else default


def validate_expression(expr: str) -> None:
    """执行前校验（父进程侧，D2 第 1–3 步）。

    Raises:
        UnsafeExpressionError: 超长 / 语法错误 / 越权节点 / dunder 名或属性。
    """
    if not isinstance(expr, str):
        raise UnsafeExpressionError(f"expression must be str, got {type(expr).__name__}")
    if len(expr) > MAX_EXPR_CHARS:
        raise UnsafeExpressionError(
            f"expression too long: {len(expr)} > {MAX_EXPR_CHARS}")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpressionError(
            f"syntax error: {exc.msg} (line {exc.lineno})") from exc

    for node in ast.walk(tree):
        node_type = type(node)
        if node_type not in _ALLOWED_NODES:
            line = getattr(node, "lineno", "?")
            raise UnsafeExpressionError(
                f"node type {node_type.__name__} not allowed (line {line})")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise UnsafeExpressionError(
                f"attribute '{node.attr}' not allowed (line {node.lineno})")
        if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_ATTRS:
            raise UnsafeExpressionError(
                f"attribute '{node.attr}' not allowed (line {node.lineno})")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise UnsafeExpressionError(
                f"name '{node.id}' not allowed (line {node.lineno})")


# worker 环境变量白名单（D5）: 只保留解释器/系统必需的项，避免把宿主的
# 令牌/端点配置（如 *API_KEY*）泄漏进求值进程。
_KEEP_ENV = (
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "PATH",
    "PYTHONHOME", "PYTHONPATH", "PYTHONUTF8",
    "TEMP", "TMP", "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
)


def _sandbox_env(memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB) -> dict:
    env = {k: os.environ[k] for k in _KEEP_ENV if k in os.environ}
    apply_worker_env(env, memory_limit_mb)
    return env


def _worker_executable() -> str:
    """Prefer the real base interpreter over a venv redirector.

    On Windows, a venv's ``Scripts\\python.exe`` is a redirector/trampoline
    that spawns the base interpreter.  The sandbox Job Object sets
    ``JOB_OBJECT_LIMIT_ACTIVE_PROCESS=1``, so that spawn fails with
    ``WinError 1816`` and the worker appears to crash.  ``sys._base_executable``
    is the real interpreter (CPython C-API ``base_executable``).
    """
    base = getattr(sys, "_base_executable", None)
    if base and os.path.isfile(base):
        return base
    return sys.executable


def _worker_env(memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB) -> dict:
    """Worker env; when using the base interpreter, expose venv site-packages."""
    env = _sandbox_env(memory_limit_mb)
    if os.path.normcase(_worker_executable()) == os.path.normcase(sys.executable):
        return env
    paths = [env.get("PYTHONPATH", "")] + list(site.getsitepackages())
    env["PYTHONPATH"] = os.pathsep.join(
        dict.fromkeys(p for p in paths if p)
    )
    return env


def _json_default(obj):
    """numpy 标量（float32/int64 等非 float 子类）→ Python 原生类型。"""
    item = getattr(obj, "item", None)
    if callable(item):
        return item()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _reader_loop(proc, sink: "queue.Queue") -> None:
    """后台读 worker stdout：累积到可解析 JSON 为止（沿用 D3 多行契约）。"""
    buf = ""
    while True:
        try:
            chunk = proc.stdout.readline()
        except (ValueError, OSError):   # 管道被 kill 关闭
            chunk = ""
        if not chunk:
            sink.put(("eof", None))
            return
        buf += chunk
        try:
            payload = json.loads(buf)
        except json.JSONDecodeError:
            continue
        buf = ""
        sink.put(("resp", payload))


class SafeEvaluator:
    """受限求值器（懒启动；`close()` 幂等）。

    Args:
        timeout_s: 单次求值超时（父侧计时）。
        total_budget_s: 会话总预算（搜索路径用；`None` = 不限制）。
            每次求值的实际超时取 ``min(timeout_s, 剩余预算)``，预算耗尽 ⇒
            :class:`EvaluationTimeout`（消息为 ``batch budget exceeded``）。
        memory_limit_mb: worker 提交内存上限（MiB；`0` = 关闭）。Windows 用
            Job Object，POSIX 由 worker 自设 `RLIMIT_AS`（见 `limits.py`）。
            非法值 / 负数 ⇒ 回落 :data:`DEFAULT_MEMORY_LIMIT_MB`。
    """

    def __init__(self, timeout_s: float = DEFAULT_TIMEOUT_S,
                 total_budget_s: float | None = None,
                 memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB):
        self.timeout_s = _coerce_positive(timeout_s, DEFAULT_TIMEOUT_S)
        self.memory_limit_mb = coerce_limit_mb(memory_limit_mb)
        if total_budget_s is None:
            self.total_budget_s = None
            self._deadline = None
        else:
            self.total_budget_s = _coerce_positive(
                total_budget_s, DEFAULT_SEARCH_BUDGET_S)
            self._deadline = time.monotonic() + self.total_budget_s
        self._proc = None
        self._queue: queue.Queue | None = None
        self._workdir: str | None = None
        self._limits: WindowsJobLimits | None = None
        self._limit_reason = ""

    # -- 生命周期 ----------------------------------------------------------
    def __enter__(self) -> "SafeEvaluator":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False

    def close(self) -> None:
        """终止 worker 并清理临时目录（幂等）。"""
        self._kill()
        if self._workdir:
            shutil.rmtree(self._workdir, ignore_errors=True)
            self._workdir = None

    def _kill(self) -> None:
        if self._limits is not None:
            self._limits.close()
            self._limits = None
        proc = self._proc
        self._proc = None
        self._queue = None
        if proc is None:
            return
        try:
            proc.kill()          # D8: Windows 上 terminate 未必生效 ⇒ 直接强杀
        except OSError:
            pass  # 进程已退出 ⇒ 无需再杀
        try:
            proc.wait(timeout=1.0)
        except (subprocess.TimeoutExpired, OSError):
            pass  # 等不到就放弃（父侧已不再持有该进程）

    def _start(self) -> None:
        self._workdir = tempfile.mkdtemp(prefix="autoprover-sandbox-")
        self._limit_reason = ""
        proc = subprocess.Popen(
            [_worker_executable(), "-u", "-c", _WORKER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            cwd=self._workdir,
            env=_worker_env(self.memory_limit_mb),
            close_fds=True,
        )
        sink: queue.Queue = queue.Queue()
        threading.Thread(
            target=_reader_loop, args=(proc, sink), daemon=True).start()
        self._proc = proc
        self._queue = sink
        # W8 / B-60: Windows 用 Job Object 封顶提交内存 + 活动进程数。
        # 失败 ⇒ fail-open（只记 reason，不影响求值）。
        if self.memory_limit_mb > 0:
            lim = WindowsJobLimits(self.memory_limit_mb)
            if not lim.attach(proc):
                self._limit_reason = lim.reason or "job object unavailable"
            else:
                self._limits = lim

    def _ensure(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        if self._proc is not None:
            self._kill()
        self._start()

    def budget_exhausted(self) -> bool:
        """会话预算是否已耗尽（搜索路径用于提前终止，避免记录惩罚点假反例）。"""
        return self._deadline is not None and time.monotonic() >= self._deadline

    def limits_status(self) -> dict:
        """资源上限的**只读**读数（W8/DS D5；不参与 verdict/pass_rate）。

        POSIX 下 `memory_cap_active=True` 表示**参数已下发**给 worker
        （`RLIMIT_AS` 由 worker 自设，父进程无法逐值确认），不是「已确认生效」。
        """
        is_win = sys.platform == "win32"
        if is_win:
            active = (self.memory_limit_mb > 0
                      and self._limits is not None and self._limits.active)
            reason = self._limit_reason
        else:
            active = self.memory_limit_mb > 0 and posix_rlimit_available()
            reason = ""
        return {
            "platform": "windows" if is_win else "posix",
            "requested_mb": self.memory_limit_mb,
            "memory_cap_active": active,
            "process_cap_active": active,
            "reason": reason,
            # B-66 / W10: 主动防线 = AST 桥跳名黑名单；**不是** OS 级隔离。
            "network_isolation": "ast-deny-list",
            "os_network_isolation": False,
        }

    # -- 求值 --------------------------------------------------------------
    def evaluate(self, params: dict, expr: str,
                 expected: float = 0.0, tolerance: float = 0.0) -> float:
        """求值单个表达式（同步）。

        Raises:
            UnsafeExpressionError: 白名单/长度闸拒绝（执行前）。
            EvaluationTimeout: 单次超时或批预算耗尽（worker 已杀）。
            WorkerCrashed: worker 意外退出。
            EvaluationError: worker 内执行异常。
        """
        validate_expression(expr)

        timeout = self.timeout_s
        if self._deadline is not None:
            remaining = self._deadline - time.monotonic()
            if remaining <= 0.0:
                raise EvaluationTimeout("batch budget exceeded")
            timeout = min(timeout, remaining)

        self._ensure()
        request = json.dumps(
            {"expr": expr, "params": params,
             "expected": float(expected), "tolerance": float(tolerance)},
            default=_json_default,
        ) + "\n"
        try:
            self._proc.stdin.write(request)
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as exc:
            self._kill()
            raise WorkerCrashed(f"sandbox worker pipe closed: {exc}") from exc

        try:
            kind, payload = self._queue.get(timeout=timeout)
        except queue.Empty:
            self._kill()          # D8: 超时 ⇒ 杀进程；会话路径下次求值自动重建
            raise EvaluationTimeout(
                f"evaluation exceeded {timeout:.2f}s") from None

        if kind == "eof":
            self._kill()
            raise WorkerCrashed("sandbox worker exited unexpectedly")
        if not payload.get("ok"):
            raise EvaluationError(
                f"{payload.get('error', 'Error')}: {payload.get('detail', '')}")
        return float(payload.get("value", 0.0))
