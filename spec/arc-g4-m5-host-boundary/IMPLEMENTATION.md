# 实施文档：G4-M5 宿主边界（env allowlist / safe_join / HostProfile / AST 守卫）

---
id: arc-g4-m5-host-boundary-IMPLEMENTATION
type: design
version: 1.4
status: verified
date: 2026-11-14
depends: [arc-g4-m5-host-boundary-DESIGN, arc-g4-m5-host-boundary-RESEARCH]
upstream: arc-g4-m5-host-boundary-DESIGN
---

> **Feature**: arc-g4-m5-host-boundary（P-106，G4-M5）
> **创建日期**: 2026-11-14
> **状态**: verified（Step 5-6：实施计划 + 自查；U-5..U-9 已按 DESIGN §11 裁决冻结；v1.1 仅上游引用同步；**v1.2** 六步 TDD 实施完成后按实测回填：58→60 调用、~30→31 写点、3 条 exempt→1 条、R5 谓词/目标参数位按 DESIGN §11.2 订正；**v1.3** 独立异构复审订正（hardware.py 行数实测 +21、N-1 负向用例宣称如实降级，见 DESIGN §13.7）；**v1.4** F-1 负向用例补录（`test_t14_alias_spawn_is_outside_scan`，17 用例 / 30 passed，DESIGN §13.7 F-1 闭环））
> **Spec 步骤**: Step 5-6
> **基于设计**: [DESIGN.md](./DESIGN.md)（v1.6）
> **基于调研**: [RESEARCH.md](./RESEARCH.md)（v1.2）
> **批次性质**: P-106 原为纯文档批；本文件 v1.2 已由实施批（2026-11-14）执行并回填实测结果（§13）。

---

## 1. 实现目标

把 DESIGN §2.2 D-1..D-7 与 §4 接口落成可执行的施工单，交付三件产物与一道常驻门禁：

1. **A4-7**：7 处「执行模型生成物/用户内容」的子进程改走 `build_subprocess_env(overrides)` 内联形态（E-1..E-7），E-8 与 51 处宿主工具/生命周期调用登记分类；
2. **A4-8**：按 DESIGN §11 U-9 **候选 A** 冻结的「拼接触发」定义（实施订正见 DESIGN §11.2），登记并由守卫双向校验动态名写点（实施落盘 31 处，含 1 条 `policy: exempt`）；
3. **A4-9**：新增只读 `HostProfile` 快照 + `hardware.list_gpu_devices()`，`researchclaw/**` 内 `shell=True` 恒 0；
4. **M4-D6**：`tests/boundary_registry.yaml`（单一登记源）+ `tests/test_boundary_coverage.py`（R1..R6 双向一致 + 元测试）。

**测试通过 ≠ 设计落地**（ADD Iron Law）：每条验收项都必须有红/绿可复现用例（§6）。

## 2. 环境与依赖

| 项 | 版本 | 说明 |
|----|------|------|
| Python | 3.11+（`requires-python = ">=3.11"`） | 现有双环境纪律 |
| PyYAML | `pyyaml>=6.0`（pyproject 既有依赖） | 注册表加载，**不新增依赖** |
| 新增依赖 | **无** | `host_profile` 仅用 stdlib（`os`/`shutil`/`subprocess`/`ctypes`/`re`/`pathlib`） |
| 基线 | HEAD `5cf14e7` | P-105 收敛批已推送 |
| 测试入口 | `pytest tests/test_boundary_coverage.py tests/test_host_profile.py` | 另加既有 9 用例回归 |

## 3. 文件清单（改动面）

| # | 文件 | 动作 | 内容 | 回退点 |
|---|------|------|------|--------|
| 1 | `tests/boundary_registry.yaml` | 新 | `version/scan` + 60 条 `subprocess_calls` + 31 条动态名 `write_sites`（含 1 条 exempt） | 删除文件 |
| 2 | `tests/test_boundary_coverage.py` | 新 | `load()/scan()/check()` + T-5..T-9 | 删除文件 |
| 3 | `tests/test_host_profile.py` | 新 | T-1..T-4 | 删除文件 |
| 4 | `researchclaw/runtime/host_profile.py` | 新 | `HostProfile`（frozen）+ `detect_host_profile()` | 删除文件 |
| 5 | `researchclaw/hardware.py` | 改 | 新增 `list_gpu_devices()`（+21 行实测，含 docstring）；`detect_hardware`/`_detect_nvidia` 不动 | 按 hunk revert |
| 6 | `researchclaw/experiment/stat_agent_sandbox.py` | 改 | E-1：删 `_build_env`，调用点内联 allowlist | 单文件 revert |
| 7 | `researchclaw/experiment/biology_agent_sandbox.py` | 改 | E-2：同上 | 单文件 revert |
| 8 | `researchclaw/experiment/collider_agent_sandbox.py` | 改 | E-3：同上 | 单文件 revert |
| 9 | `researchclaw/experiment/code_agent.py` | 改 | E-4：`{**os.environ, **self._env_extra}` → `build_subprocess_env(self._env_extra)` | 单行 revert |
| 10 | `researchclaw/hitl/hooks.py` | 改 | E-5：RC_* overrides 内联到 `env=` | 单 hunk revert |
| 11 | `researchclaw/pipeline/opencode_bridge.py` | 改 | E-6：`OPENAI_API_KEY` overrides 内联到 `env=` | 单 hunk revert |
| 12 | `researchclaw/agents/figure_agent/renderer.py` | 改 | E-7：本地执行加 `env=build_subprocess_env()`；E-8（:329）**不改码** | 单行 revert |
| 13 | `researchclaw/utils/paths.py` | 改 | `safe_join` docstring 补 TOCTOU 边界（无行为变更） | 单 hunk revert |
| 14 | `.github/workflows/ci.yml` | 改 | contract tests 固定清单追加两个新测试文件（门禁接线） | 单 hunk revert |
| 15 | `spec/arc-g4-m5-host-boundary/`、`docs/PROGRESS.md`、`docs/arc-master-roadmap.md` | 改 | 四文档 + 进度/路线图（流程件，不计代码面） | 按文件 revert |

> **无改码登记**：`researchclaw/evidence/sidecar.py:222` `env=_build_env(config)` 保持不变——其本体 `:87-104` 为自建 allowlist（语义合规、形态不匹配），注册表登记 `env: sourced:_build_env`。

## 4. 实现顺序（TDD，先红后绿）

| 步 | 动作 | 红/绿判据 |
|---|------|-----------|
| 1 | 建 `tests/boundary_registry.yaml` 骨架（仅 `version: 1` + `scan`）+ `tests/test_boundary_coverage.py` 的 `load/scan/check` 框架 | 跑测试 → **红**（R1：60 调用全未登记，失败信息列出 `relpath:qualname#ordinal`；实测首跑 89 条错误 = 60 subprocess + 31 write，R3 = 0） |
| 2 | 一次性只读 AST 脚本生成初稿（**脚本不入仓**）→ 人工逐条核对 `category`/`env`/`reason` → 落盘（实测 60 条） | 跑测试 → R1/R2/R3 绿（R4 对 7 处仍红、R5 对动态名还红） |
| 3 | 改 E-1..E-7 为内联 allowlist 形态（§5.5），同步把对应 7 条登记 `env: allowlist` | R4 绿；T-11 绿（哨兵键不泄漏） |
| 4 | 按 U-9 定义重扫写点 → 动态名子集登记 `safe_join`/`exempt` → 改造 `safe_join(base, name)` | R5 绿；T-8/T-12 绿 |
| 5 | 新增 `runtime/host_profile.py` + `hardware.list_gpu_devices()` + `tests/test_host_profile.py` | T-1..T-4 绿 |
| 6 | 补 `utils/paths.py` docstring；ci.yml 接线；跑全量套件（新增 + 既有 9 用例） | T-13 绿；R6 元测试绿 |

**顺序约束**：步骤 1 的「跑红」= R1 全红；R6 元测试需要至少 1 条登记后才可执行（DESIGN §13 E 项订正），故 R6 在步骤 2 后首次可验证，步骤 6 正式纳入套件。

## 5. 接口实现细节

### 5.1 `tests/boundary_registry.yaml` 与登记口径

字段严格按 DESIGN §4.5；本节只补「如何机械复现键」：

- `relpath`：POSIX 风格、相对仓库根（如 `researchclaw/pipeline/stage_impls/_execution.py`）。
- `qualname`：模块内以 `.` 连接的类/函数栈（如 `ExperimentSandbox.run`）。
- `ordinal`：
  - `subprocess_calls`：同一 `(relpath, qualname)` 内**全部** subprocess 调用按 `(lineno, col_offset)` 升序的 1-based 序号；
  - `write_sites`：同一 `(relpath, qualname)` 内**满足 U-9 动态名谓词的写点**按 `(lineno, col_offset)` 升序的 1-based 序号。
- `env` 枚举与代码形态**强绑定**（守卫双向校验）：

| `env` 值 | 要求的 AST 形态 |
|---|---|
| `inherit` | 调用**无** `env=` 关键字 |
| `allowlist` | `env=` 值本身是 `build_subprocess_env(...)` 调用，或同函数单层别名 `env = build_subprocess_env(...)` 后 `env=env` |
| `sourced:<name>` | `env=` 值是 `<name>(...)` 调用（如 `_build_env`） |
| `prefix` | 无 `env=`，env 以命令前缀注入（SSH）；`reason` 必填 |
| `overrides` | 保留枚举，现状无实例，不使用 |

- `category`：A=宿主工具/CLI、B=工作负载执行、C=生命周期管理；**B 类必须 `env: allowlist`**，例外三类（均须 `reason` 说明）：`sourced:<name>` 自建 allowlist 来源（S-010/S-057）、`prefix`（U-5 SSH，S-033）、容器内执行 `inherit`（E-8 / S-012 / S-025，env 仅达 docker 客户端、无 `-e` 透传）。
- 豁免只允许出现在 `write_sites.policy: exempt`，且 `reason/owner/expires` 三项必填；`expires` 为 ISO 日期，过期即红。

### 5.2 `tests/test_boundary_coverage.py`

```python
@dataclass(frozen=True)
class Finding:
    relpath: str
    qualname: str
    ordinal: int
    lineno: int
    kind: str          # "subprocess" | "write"
    form: str          # inherit | allowlist | alias | sourced:<name> | prefix | other
    shell_true: bool
    first_line: str

def load(path: Path = REGISTRY_PATH) -> dict[str, Any]: ...          # 缺失/版本不符 → 抛异常（fail-closed）
def scan(roots, exclude=()) -> tuple[list[Finding], list[Finding]]: ...  # (subprocess, write)
def check(registry: dict, findings) -> list[str]: ...                # 纯函数，返回错误列表（空 = 绿）
```

- `scan` 用 `ast.parse` 遍历 `*.py`，`exclude` 按相对路径前缀过滤；`ordinal` 按 §5.1 计算。
- 调用识别：`Call.func` 为 `Attribute(attr in {run, Popen, check_call, check_output, call})` 且链根为 `subprocess`；或 `Name` 为 `Popen`（`from subprocess import Popen` 形态）。
- 写点识别（目标参数位，v1.2 按 DESIGN §11.2 订正）：`write_text/write_bytes` → **接收者**；`Path.open(...)` 且 mode 含 `w/a/x/+` → **接收者**；内建 `open(...)` 同模式 → `args[0]`；`shutil.copy/copy2/copyfile/copytree` → `args[1]`；`os.replace`（仅 `os.` 根）→ `args[1]`。`Path.replace`/`str.replace` **不判**。
- **U-9 动态名谓词**（DESIGN §11 U-9 冻结）：

```python
def _has_name(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Name) for n in ast.walk(node))

def _is_dynamic(target: ast.AST) -> bool:
    # v1.2: 名称成分触发（DESIGN §11.2 V-1）——基目录为变量不单独触发
    if isinstance(target, ast.BinOp) and isinstance(target.op, ast.Div):
        return _has_name(target.right)
    if isinstance(target, ast.BinOp) and isinstance(target.op, ast.Add):
        return _has_name(target.left) or _has_name(target.right)
    if isinstance(target, ast.Call) and isinstance(target.func, ast.Attribute) \
            and target.func.attr in {"join", "joinpath"}:
        return any(_has_name(a) for a in target.args)
    if isinstance(target, ast.JoinedStr):
        return any(_has_name(v.value) for v in target.values if isinstance(v, ast.FormattedValue))
    return False
```

- `check` 判定顺序：R3（任一 `shell_true` → 立即返回）→ R1/R2（双向键一致）→ R4（`env` 形态与登记一致）→ R5（动态写点与登记双向一致）。
- R2 失败信息附「该 qualname 下已登记 ordinal 列表 + 各调用点首行文本」；键在但 ordinal 不可达 → 输出「疑似 ordinal 漂移」。

### 5.3 `researchclaw/runtime/host_profile.py`

```python
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


def detect_host_profile(
    *,
    disk_root: Path | None = None,
    toolchains: tuple[str, ...] = ("python", "docker", "git"),
) -> HostProfile: ...
```

实施要点：

- **先校验后探测**：任一 `toolchains` 元素不匹配 `_TOOLCHAIN_RE` → `ValueError`（在任何子进程之前）。
- `_memory_total_mb()`：Windows 用 `ctypes` `GlobalMemoryStatusEx`（`_MEMORYSTATUSEX` 结构体，`dwLength` 先赋值）；POSIX 用 `os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")`；`AttributeError/OSError/ValueError` → `0`。
- `_disk_free_gb(root)`：`shutil.disk_usage(str(root)).free / 2**30`；异常 → `0.0`。
- `_probe_toolchain(name)`：`subprocess.run([name, "--version"], capture_output=True, text=True, timeout=5, check=False, env=build_subprocess_env())`；`FileNotFoundError/TimeoutExpired/OSError` 或 `returncode != 0` → `None`；取 `stdout`（空则 `stderr`）首个非空行 `strip()`。
- `toolchains` 仅收录探测成功的键；**不写默认值**（缺失即省略，DESIGN §7）。
- `as_dict()` 返回副本，保证调用方无法通过返回值污染快照（I-1）。
- 不引入 `psutil`、不建第二套 GPU 探测。

### 5.4 `researchclaw/hardware.py::list_gpu_devices()`

```python
def list_gpu_devices() -> tuple[str, ...]:
    """All GPU lines from ``nvidia-smi -L``; () when unavailable."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "-L"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ()
    if result.returncode != 0:
        return ()
    return tuple(line.strip() for line in (result.stdout or "").splitlines() if line.strip())
```

- 放在 `_detect_nvidia` 之后，不改其 `splitlines()[0]` 既有行为（DESIGN §11.1）。
- 原文返回（含 `UUID`），解析责任在下游。

### 5.5 E-1..E-7 env 接入（内联 allowlist）

> 统一形态：`env=build_subprocess_env(<overrides>)`；overrides **只减不增**（I-6）。行号为当前基线参考，实施以 `qualname` 定位。

**E-1/E-2/E-3（三个 agent sandbox，结构同形）**

现状：`env = self._build_env()`（stat:88 / biology:116 / collider:107）→ `env=env`；`_build_env` 本体（stat:380 / biology:455 / collider:680）为 `os.environ.copy()` + 两个 MAGNUS 键。

改造：删 `_build_env` 方法（各文件仅一个调用点，已核实无其他消费者），调用点改为

```python
            proc = subprocess.run(
                cmd,
                cwd=str(workspace),
                env=build_subprocess_env(
                    {
                        key: value
                        for key, value in (
                            ("MAGNUS_ADDRESS", self.config.magnus_address),
                            ("MAGNUS_TOKEN", self.config.magnus_token),
                        )
                        if value
                    }
                ),
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
```

新增导入：`from researchclaw.utils.env import build_subprocess_env`。

**E-4 `code_agent.py:462`**

```python
            env={**os.environ, **self._env_extra},   # 改前
            env=build_subprocess_env(self._env_extra),  # 改后
```

`_env_extra` 来自 `CliAgentConfig.env_extra`（config.py:1551 显式配置的键值对），是认证/代理通道，整体作为 overrides 保留。

**E-5 `hitl/hooks.py:211-225`**

删除 :211-216 的 `env` 构造，改为

```python
            result = subprocess.run(
                [str(script)],
                capture_output=True,
                text=True,
                timeout=30,
                env=build_subprocess_env(
                    {
                        "RC_STAGE_NUM": str(stage_num),
                        "RC_STAGE_NAME": stage_name,
                        "RC_HOOK_NAME": hook_name,
                        **({"RC_RUN_DIR": str(self.run_dir)} if self.run_dir else {}),
                    }
                ),
                cwd=str(self.run_dir) if self.run_dir else None,
            )
```

**E-6 `pipeline/opencode_bridge.py:462-488`**

保留 `api_key` 计算（`:464-470`），删除 `env = os.environ.copy()` 与 `env[...]` 写入，调用点改为

```python
                env=build_subprocess_env(
                    {"OPENAI_API_KEY": api_key} if api_key else None
                ),
```

**E-7 `agents/figure_agent/renderer.py:264-274`**

在 `subprocess.run(...)` 增加一个关键字参数（当前无 `env=`）：

```python
                env=build_subprocess_env(),
```

**E-8 `renderer.py:329`（不改码）**：docker 形态执行同源脚本，env 仅达 docker 客户端（容器无 `-e` 透传）；注册 `category: B`, `env: inherit`, `reason` 注明「容器内执行；无 -e 透传」+ `owner`。

**附带核验（DESIGN U-5）**：SSH 后端 `env_overrides` 从 `run()` 上游到 `env_prefix` 的传值链须确认不含密钥；确认结果写入实施提交说明。不成立则回 DESIGN §11 改判。

### 5.6 写点改造与登记（U-9 候选 A）

1. 用 §5.2 的谓词全量重扫 `researchclaw/**`，得到动态名清单（预计 ~30，**以扫描输出为准**；实施实测 **31 处 / 15 文件**）。
2. 逐条二选一：
   - `policy: safe_join`：把 `base / name` / `f"{name}"` 等改为 `safe_join(base, name)`，导入 `from researchclaw.utils.paths import safe_join`；
   - `policy: exempt`：仅限「名称为函数内固定字面量派生」且 `reason/owner/expires` 齐全——实施落盘 **1 条**（`pipeline/runner.py` 的 `current_dir / fname`，现 :1767）；原列的 `copy2`/`copytree` 两处目标为纯 `Name`，按 U-9 不触发 R5，故不登记（DESIGN §11.2 V-4）。
3. 改写时保持返回类型 `Path`（`safe_join` 返回已 resolve 的 `Path`）；对需要 `str` 的调用点显式 `str(...)`，不改变既有下游契约。
4. **不动** `safe_join` / `_safe_filename` 本体；`_execution.py:1258` 既有 `safe_join` 消费点保持不变。
5. 固定字面量写点**不登记、不改**（U-9 谓词不触发）。

### 5.7 `utils/paths.py` docstring

在 `safe_join` docstring 追加（无行为变更）：

```
The symlink check is point-in-time: a directory swapped concurrently
after ``resolve()`` can still redirect the write.  This helper does not
provide ``O_NOFOLLOW``-level guarantees; callers that share a writable
tree across processes must serialise access themselves.
```

### 5.8 ci.yml 接线

在 contract tests 固定清单（`ci.yml:150` 附近）追加：

```yaml
            tests/test_boundary_coverage.py \
            tests/test_host_profile.py \
```

守卫不接线即无门禁效力；此项为 DESIGN §3.2 的落地必要条件，不改任何门禁判据。

## 6. 测试计划

### 6.1 `tests/test_host_profile.py`（T-1..T-4）

| # | 用例 | 手段 | 断言 |
|---|------|------|------|
| T-1 | `as_dict()` 可序列化、无 callable | 构造 `HostProfile` 直接调用 | 值为 `int/float/list/dict/str`；`json.dumps` 成功 |
| T-2 | 多行 `nvidia-smi -L` 全解析 | mock `subprocess.run` 返回 2 行 | `list_gpu_devices() == (line1, line2)` |
| T-3 | 探测失败降级 | mock 抛 `FileNotFoundError` / 返回码 1 | `gpu_devices == ()`；`detect_host_profile` 不抛异常 |
| T-4 | 非法 toolchain 名 | `toolchains=("python; rm -rf /",)` | `ValueError`，且**未发生**任何子进程调用 |

### 6.2 `tests/test_boundary_coverage.py`（T-5..T-9）

| # | 用例 | 手段 | 断言 |
|---|------|------|------|
| T-5 | 未登记 subprocess → 红 | `tmp_path` 迷你包 `subprocess.run([...])`，空注册表 | 错误含 `unregistered subprocess call` |
| T-6 | 陈旧条目 → 红 | 注册表含 AST 中不存在的键 | 错误含 `stale registry entry` |
| T-7 | `shell=True` → 红 | 真实扫描根（`researchclaw/**`） | 当前 0 命中；合成树注入 `shell=True` 后必红且无豁免通道 |
| T-8 | 动态写点未登记 → 红 | 合成 `(base / name).write_text(...)` | 错误含 `unregistered dynamic write`；固定字面量不触发 |
| T-9 | R6 元测试 | `check(load(), scan(...)) == []` 后，从内存删除 1 条登记 | 再次 `check` 非空（守卫非空转）；**不落临时文件** |

补充负向：R4 三分支各 1 例——内联 `build_subprocess_env` 绿、`env = build_subprocess_env(...)` 单层别名绿、`env = os.environ.copy()` 红；`sourced:_build_env` 形态绿。

### 6.3 行为验证（T-10..T-13）

| # | 用例 | 手段 | 断言 |
|---|------|------|------|
| T-10 | 7 处 env 来源合规（两层验证） | (a) AST 层：`test_t10_seven_sites_use_inline_allowlist` 断言 7 条登记 `env: allowlist` 且实测形态为 `allowlist`；(b) builder 层：`test_t10_env_is_closed_over_allowlist` 以哨兵键验证 `build_subprocess_env` 白名单封闭 | `env` 仅含 `SAFE_ENV_KEYS`/`LC_*`/overrides |
| T-11 | 哨兵键不泄漏 | 宿主设 `AWS_SECRET_ACCESS_KEY=...`，调 `build_subprocess_env`（7 处共用同一 builder） | 子进程 env 无该键（`test_t10_env_is_closed_over_allowlist`）；MAGNUS/RC_*/OPENAI_API_KEY 等显式键仍在 |
| T-12 | `safe_join` 三类逃逸 | `..`、绝对路径、符号链接 | 均 `ValueError`；正常名返回 `Path` 且在 base 内 |
| T-13 | 回归 | `pytest tests/test_env_allowlist.py tests/test_safe_join.py` | 既有 9 用例全绿（4+5） |

### 6.4 全量套件

```bash
python -m pytest tests/test_boundary_coverage.py tests/test_host_profile.py \
                 tests/test_env_allowlist.py tests/test_safe_join.py -q
```

## 7. 兼容性与迁移

| 项 | 影响 | 处置 |
|---|---|---|
| 子进程不再继承全量 env（E-1..E-7） | 依赖父进程隐式变量的 CLI 可能缺键（如 `HTTP(S)_PROXY`、自定义 `ANTHROPIC_*`） | **行为变更登记**；需要的键由配置 `env_extra` 显式提供（不改 allowlist 本体） |
| 删除 3 个 `_build_env` 方法 | 私有方法，无外部消费者（已 grep 核实） | 直接删除；如测试有 monkeypatch 引用，按新形态改写 |
| `HostProfile.toolchains` 为可变 dict 字段 | frozen 仅防字段重绑 | `as_dict()` 返回副本；I-1 以用例锁定 |
| `safe_join` 改写 31 处 | 返回已 resolve 的绝对路径 | 需要相对路径或 `str` 的调用点显式转换；逐点回归 |
| 注册表新增 | 无运行时消费 | 仅测试读取，零生产影响 |
| `shell=True` 现状 0 | 无迁移 | — |

## 8. 低效操作排除

| 排除项 | 理由 |
|---|---|
| 全仓扫描（含 `tools/**`） | U-6 已裁决不纳入；`scan.roots` 留一行扩展 |
| 为守卫引入 Bandit / 第三方 AST 框架 | 纯 `ast` + PyYAML 足够；零新依赖 |
| 319/328 处写点全量改 `safe_join` | U-4=A 已否决；固定字面量改收益为零 |
| 统一子进程 wrapper 收口 60 处 | 改造面与认证回归面最大，DESIGN §5 已否决 |
| `safe_join` 加 `O_NOFOLLOW` | 职责外（DESIGN §2.3），仅补 docstring |
| 每次守卫运行都重新解析注册表 | `load()` 在模块级 fixture 缓存一次；`check()` 保持纯函数 |

## 9. 版本核验表（Step 6 Review）

| 依赖/接口 | 声明 | 验证方式 | 状态 |
|---|---|---|---|
| `subprocess.run/Popen` 的 `env`/`shell` 语义 | Python 3.11+ 文档 | RESEARCH §3.2 T1 原文 | ✅ |
| `pathlib.Path.resolve` symlink 语义 | Python 3.11+ 文档 | RESEARCH §3.2 T1 | ✅ |
| `shutil.disk_usage` | stdlib | 本机 `python -c` 实测 | ✅ |
| `ctypes` `GlobalMemoryStatusEx` | Win32 API（kernel32） | 本机 Windows 实测 | ✅ |
| `yaml.safe_load` | PyYAML ≥6.0 | pyproject 既有依赖；`safe_load` 避免任意对象构造 | ✅ |
| `safe_join` 异常语义 | 仓内实现 `utils/paths.py:13-24` | 既有 5 用例 | ✅ |

## 10. 回退方案

- 代码面：§3 每文件独立可 revert；整批回退 = revert 单个提交。
- 注册表：删除 `boundary_registry.yaml` + 测试文件即完全移除门禁，不影响生产代码。
- 数据/配置：无迁移、无 schema 变更。
- 若 E-4 引发 CLI 认证回归：单行回退 `code_agent.py:462`，其余点不受影响。

## 11. 风险与已知限制

| 风险 | 等级 | 缓解 |
|---|---|---|
| 注册表 60 条人工登记错位 | 中 | AST 生成初稿 + 双人核对；R2 兜陈旧、R1 兜遗漏 |
| E-4 切断隐式代理/认证变量 | 中 | T-11 哨兵用例 + 配置 `env_extra` 显式回填；行为变更登记（§7） |
| R5 纯 Name 盲区（U-9 候选 A 代价） | 中 | DESIGN §11.1 已登记；人工审查兜底；改判 B 需重估注册表规模 |
| R1 方法别名盲区（`supervisor.py:71`） | 低 | 注册 R1 已知限制；威胁面为默认命令（负向用例已补录 `test_t14_alias_spawn_is_outside_scan`，DESIGN §13.7 F-1 闭环，IMPL §13.5） |
| `memory_total_mb` 平台差异返回 0 | 低 | 设计即降级，不阻断 pipeline |
| `expires` 到期导致守卫变红 | 低 | 豁免仅 1 条固定名写点，续期或改码二选一 |

## 12. 与 DESIGN 的对齐自检（Step 6）

- [x] 每个模块对应 DESIGN §3.2；新增 4 文件与 §10.3 一致。
- [x] 接口签名与 DESIGN §4.1/§4.2 逐字段一致（`HostProfile` 五字段、`detect_host_profile` 两个仅关键字参数、`list_gpu_devices -> tuple[str, ...]`）。
- [x] 守卫规则 R1..R6 与 §4.6 一一对应；R5 谓词即 §11 U-9 裁决定义。
- [x] E-1..E-8 与 §4.3 表逐条对应（E-8 不改码）。
- [x] 豁免 1 条 + `sourced:_build_env` 1 条与 §4.5 注释一致（v1.2 实测订正）。
- [x] 验收项 A4-7/A4-8/A4-9/M4-D6 与 §12 映射的 T 编号一致（T-1..T-13 无悬空）。
- [x] 无 DESIGN 未覆盖的实施项；ci.yml 接线为门禁生效的必要条件，已显式声明。
- [x] 零新增第三方依赖；零生产运行时消费注册表。

## 13. 实施记录（v1.2 回填，2026-11-14）

### 13.1 六步红/绿留痕

| 步 | 实测结果 | 证据 |
|---|---|---|
| 1 骨架 + 守卫框架 | **红**：89 条错误（60 `unregistered subprocess call` + 31 `unregistered dynamic write`），R3 = 0 | `python -m pytest tests/test_boundary_coverage.py -q` |
| 2 登记落盘 | R1/R2/R3 绿；R4 仅 7 处（E-1..E-7）红、R5 31 处红 | 同上 |
| 3 E-1..E-7 内联 allowlist | R4 绿；T-10/T-11 绿 | 同上 |
| 4 写点 safe_join（30 转换 + 1 exempt） | R5 绿 | 同上 |
| 5 `host_profile.py` + `list_gpu_devices` | 首跑 `ModuleNotFoundError` 红 → 实现后用例绿 | `tests/test_host_profile.py`（13 用例） |
| 6 docstring + ci.yml + 全量套件 | `29 passed`（两新文件）；合并回归 **60 passed** | 见 §13.2 |

### 13.2 最终验证

```
python -m pytest tests/test_boundary_coverage.py tests/test_host_profile.py -q
29 passed

python -m pytest tests/test_boundary_coverage.py tests/test_host_profile.py \
                 tests/test_env_allowlist.py tests/test_safe_join.py \
                 tests/test_sandbox_boundary.py tests/test_forged_execution_guards.py -q
60 passed
```

- 注册表实测：`subprocess_calls` 60、`write_sites` 31（30 `safe_join` + 1 `exempt`）。
- 守卫全量扫描 `researchclaw/**`：**0.93s**（目标 <5s）。
- `detect_host_profile()` 正常路径（三 toolchain 均存在）：**0.15s**（目标 <2s）。
- `git diff --stat`：25 文件 / +130 / −77（23 源文件 + `ci.yml` + `docs/PROGRESS.md`；新增 4 文件未计入）。
- `grep -rn "_build_env" researchclaw/`：仅 `evidence/sidecar.py:87/222`（按设计保留，登记 `sourced:_build_env`）。
- `researchclaw/**` 内 `shell=True`：0 命中。

### 13.3 与预期的差异

- 动态写点 **31**（预期 ~30）；豁免 **1 条**（预期 3 条）——见 DESIGN §11.2 V-1/V-4。
- subprocess **60 条**（RESEARCH 存量 58 + 本批新增 2 条）。

### 13.4 独立异构复审登记（v1.3，2026-11-14）

GLM-5.3-Flash 独立上下文异构复审（vs DeepSeek-V4.1-Flash 实施批）：独立 AST 复扫（谓词按 DESIGN §11.2/本文件 §5.2 规格文本独立转写，不导入守卫代码）60 subprocess + 31 写点与注册表双向零偏差、env/policy 零失配、`shell=True` 0 命中；29 passed 复跑（全扫描用例 0.90–1.01s ↔ §13.2 宣称 0.93s）；U-5..U-9 与禁改面（`utils/env.py`/`safe_join` 本体、`_execution.py:1258`、renderer:329/E-8）逐条实证未破；step-gate legacy exit 0（4/5 步）、dc_validator 0 违规复跑证实。发现 **1 P2 + 5 P3 + 2 观察**，全部订正与登记见 **DESIGN §13.7**；本文件订正：§3 hardware.py 行数（+约 14 → +21 实测）、§8 R1 行负向用例宣称如实降级。上游引用同步：DESIGN v1.4 → v1.5。

### 13.5 F-1 负向用例补录（v1.4，2026-11-14）

DESIGN §13.7 F-1（P2）闭环批：`tests/test_boundary_coverage.py` 新增 `test_t14_alias_spawn_is_outside_scan`——合成模块镜像 supervisor.py:71/:102 形态（`self._spawn = spawn or subprocess.Popen` + `self._spawn(...)`），断言 (a) 真实扫描 `researchclaw/runtime/supervisor.py` 零 finding（别名通道在注册表外）且 (b) 合成模块零 subprocess finding、空注册表 `check` 绿。红条件 = 守卫谓词未来扩展解析别名形态 → 本用例转红，强制注册表返工后再发布。测试计数 **16→17**（boundary）；两套件 **29→30 passed**（3.12 / 3.13.5 本机均实跑 30 passed）。DESIGN §4.6 R1 / §11.1 / §13.3 N-1 / §13.7 F-1 / 本文件 §8 / CHECKLIST §8.2 宣称同步订正。

---

**Review 签字**: DeepSeek-V4.1-Flash（实施计划自审） 日期: 2026-11-14
