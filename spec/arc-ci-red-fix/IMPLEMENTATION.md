---
id: arc-ci-red-fix-IMPLEMENTATION
type: design
version: 1.0
status: draft
date: 2026-11-15
depends: [arc-ci-red-fix-DESIGN, arc-ci-red-fix-RESEARCH]
upstream: arc-ci-red-fix-DESIGN
---

> **Feature**: CI 红面修复（P-117 实施文档批）
> **创建日期**: 2026-11-15
> **状态**: draft（草稿；实施未开始，本文档 = 施工单）
> **Spec 步骤**: Step 5-6
> **基于设计**: [DESIGN.md](./DESIGN.md)
> **基于调研**: [RESEARCH.md](./RESEARCH.md)

---

## 1. 实施概述

单批（B1）交付 12 个文件：11 改 + 1 新增。按「契约先行 → R-1 → R-4 → R-2/R-5/R-3」顺序施工：先写契约测试并确认**红**，再补 14 处签名使其转绿，随后做纯重命名与三处单行对齐。全部改动为可选关键字形参、私有属性改名、常量补项与配置对齐，**不新增依赖、不改 `config.py`、不改 Docker 的 TTL/标签逻辑**。

落地标准 = DESIGN §10.3 的读数表：`test_rc_executor.py` 14 failed → 0；`test_sandbox_boundary.py` 19 passed 不回归；四文件合集 2 failed → 0；新契约测试 2 passed；CI 四矩阵 + spec-gates 连续两次全绿。R-4 的 3.11/3.12 转绿**只能由 CI 证明**，本地 3.13 仅提供「不回归」证据。

明确不做（DESIGN §2.3）：lint/类型/覆盖率门禁（D-8）、Windows 矩阵（D-9）、`ci_coverage_check` 收集失败提示增强（D-6/U-4）、CHECKLIST 二次回填（D-7/U-5，待两次全绿）。

## 2. 工程细节

### 2.1 技术栈

| 组件 | 技术 | 版本 | 验证状态 |
|---|---|---|---|
| 语言 | Python | 3.11+（CI 矩阵 3.11/3.12/3.13/3.14） | ✅ 现存 `requires-python` |
| 测试 | pytest + pytest-asyncio | 既有 `dev` extra | ✅ 本机已跑通基线 |
| 契约检查 | 标准库 `inspect` | 3.11+ 稳定 API | ✅ `inspect.signature` / `Parameter.KEYWORD_ONLY` |
| 前端 | 原生 JS（frontend-legacy） | 无构建步骤 | ✅ `node --check` 可校验语法 |
| 新增依赖 | **无** | — | ✅ 不改 `pyproject.toml` |

### 2.2 依赖版本验证

本批**零新增依赖**，无需 PyPI 版本查询：

| 依赖 | 声明版本 | 来源 | 兼容性 | 验证方式 |
|---|---|---|---|---|
| `inspect` | 标准库 | CPython | ✅ | `pytest` 实跑契约测试用例 |
| `pytest` | 既有 `dev` extra | `pyproject.toml` | ✅ | 基线 193 passed 已证 |
| `threading` | 标准库 | CPython | ✅ | `test_sandbox_boundary.py` 19 passed 已证 |

### 2.3 文件结构（变更清单）

| # | 文件 | 类型 | 依据 | 预估行 |
|---|---|---|---|---|
| 1 | [sandbox.py](../../researchclaw/experiment/sandbox.py) | 改 | DESIGN §4.1/§4.2（协议 2 + ExperimentSandbox 2） | +6 |
| 2 | [ssh_sandbox.py](../../researchclaw/experiment/ssh_sandbox.py) | 改 | DESIGN §4.2（`#L56`/`#L69`） | +2 |
| 3 | [colab_sandbox.py](../../researchclaw/experiment/colab_sandbox.py) | 改 | DESIGN §4.2（`#L141`/`#L155`） | +2 |
| 4 | [collider_agent_sandbox.py](../../researchclaw/experiment/collider_agent_sandbox.py) | 改 | DESIGN §4.2（`#L71`/`#L173`） | +2 |
| 5 | [biology_agent_sandbox.py](../../researchclaw/experiment/biology_agent_sandbox.py) | 改 | DESIGN §4.2（`#L80`/`#L178`） | +2 |
| 6 | [stat_agent_sandbox.py](../../researchclaw/experiment/stat_agent_sandbox.py) | 改 | DESIGN §4.2（`#L63`/`#L150`） | +2 |
| 7 | [docker_sandbox.py](../../researchclaw/experiment/docker_sandbox.py) | 改 | DESIGN §4.4（`_stop` 8 处） | 8 |
| 8 | [api.js](../../frontend-legacy/src/services/api.js) | 改 | DESIGN §4.5（`EVENT_TYPES`） | 1 |
| 9 | [ci.yml](../../.github/workflows/ci.yml) | 改 | DESIGN §4.6（`#L166`） | 1 |
| 10 | [test_web_platform.py](../../tests/test_web_platform.py) | 改 | DESIGN §4.7（`:33`/`:35`） | 2 |
| 11 | [test_sandbox_boundary.py](../../tests/test_sandbox_boundary.py) | 改 | DESIGN §2.1.1-1（`:268`） | 1 |
| 12 | `tests/test_sandbox_protocol_contract.py` | **新增** | DESIGN §4.3 | ~45 |

注：清单中行号为**改前**行号；同文件内多处编辑按文本锚点定位，不受前序编辑行号漂移影响。

## 3. 模块实施

### 3.1 协议面（`sandbox.py`）

#### 职责

`SandboxProtocol` 是 7 个后端的唯一结构性真值源（DESIGN §3.1）；`ExperimentSandbox` 是其本地默认实现。

#### 接口签名

见 §4.1/§4.2（与 DESIGN §4.1 一致 ✅）。

#### 实施要点

- 4 处均只加 1 个 keyword-only 形参，**不加默认读取逻辑**（`ExperimentSandbox` 不消费 `run_id`）。
- 协议 `run` 是单行签名，追加后用两行续行，保持黑式风格（缩进对齐 `timeout_sec`）。
- 协议 docstring 增加一句语义说明（唯一出处）；**实现侧不加重复注释**（DESIGN §4.1 已收窄）。

#### 低效操作排除

无循环/IO 变化；新增形参不参与任何运行时判断。

### 3.2 五个非 Docker 后端

#### 职责

`SshRemoteSandbox` / `ColabDriveSandbox` 与协议同形；`ColliderAgentSandbox` / `BiologyAgentSandbox` / `StatAgentSandbox` 保留 `prompt_text` 首位置参与 `timeout_sec: int | None = None`。

#### 实施要点

- 仅在 `env_overrides` 之后追加 `run_id: str | None = None,`；**函数体零改动**（I-2）。
- 三个 agent 后端的 `run` 在 `timeout_sec` 之后追加；不改变 `None` → `self.config.timeout_sec` 的回落语义（stat 是显式回落，collider/biology 在内部处理）。

#### 低效操作排除

无新增分配、无额外 I/O、无日志。

### 3.3 `_TtlWatcher` 私有属性（`docker_sandbox.py`）

#### 职责

TTL 守护线程；`_stop` 与 `Thread._stop()` 同名，≤3.12 被基类方法覆盖为可调用对象，`wait()/is_set()` 随之 TypeError。

#### 实施要点

- 8 处纯字符串替换 `self._stop` → `self._stop_event`；其中 `#L91`/`#L103` 是 `while` 条件、`#L95`/`#L106`/`#L143` 是 `wait()`、`#L77` 是 `set()`、`#L97` 是 `is_set()`。
- 不动 `stop()` 公开方法名、不动 `_fire()` 与 SIGKILL 路径（Docker 归因语义零变化）。
- 测试 `:268` 同步改 `watcher._stop_event.is_set()`。

#### 低效操作排除

纯重命名，无运行时成本变化。

### 3.4 前端事件常量（`api.js`）

#### 职责

镜像后端 `EVENT_TYPES`，供前端过滤/展示；后端为真值源。

#### 实施要点

- 在 `'tool.result'` 后插入 `'tool.orphan_call'`，保持单引号与同行风格；不重排其他项、不动 `TERMINAL_EVENTS`。
- 校验：`node --check`（若本机无 node，则记为环境缺口，由 CI 前端测试覆盖）。

### 3.5 CI 安装面（`ci.yml`）

#### 实施要点

- `#L166` 单行替换为 `python -m pip install -e ".[dev,server,mcp]"`，与 Tests job `#L121` 同集合。
- 不动 spec-gates 的其余步骤与命令。

### 3.6 测试面

| 文件 | 变更 | 目的 |
|---|---|---|
| `tests/test_sandbox_protocol_contract.py` | 新增 | keyword-only 面契约（先红后绿） |
| `tests/test_web_platform.py` | `:33`/`:35` 两行 | 与 fail-closed 默认对齐 |
| `tests/test_sandbox_boundary.py` | `:268` 一行 | 跟随属性改名 |

## 4. 接口实施

### 4.1 `SandboxProtocol`（`sandbox.py`）

改前（`:299`）：

```python
    def run(self, code: str, *, timeout_sec: int = 300) -> SandboxResult: ...
```

改后：

```python
    def run(self, code: str, *, timeout_sec: int = 300,
            run_id: str | None = None) -> SandboxResult: ...
```

`run_project`（`:301`）在 `env_overrides: dict[str, str] | None = None,` 之后追加 `run_id: str | None = None,`。

**签名一致性**: 与 DESIGN §4.1 一致 ✅

### 4.2 `ExperimentSandbox`（`sandbox.py`）

`:319` 改前：

```python
    def run(self, code: str, *, timeout_sec: int = 300) -> SandboxResult:
```

改后：

```python
    def run(self, code: str, *, timeout_sec: int = 300,
            run_id: str | None = None) -> SandboxResult:
```

`:358` 的 `run_project` 参数表末尾追加同形参（**函数体不动**，`run_id` 不被读取）。

### 4.3 `SshRemoteSandbox` / `ColabDriveSandbox`

| 文件 | 方法 | 改前 | 追加位置 |
|---|---|---|---|
| `ssh_sandbox.py` | `run`（`:56`） | `def run(self, code: str, *, timeout_sec: int = 300) -> SandboxResult:` | 签名改为两行，加 `run_id` |
| `ssh_sandbox.py` | `run_project`（`:69`） | 参数表止于 `env_overrides` | 其后加 `run_id` |
| `colab_sandbox.py` | `run`（`:141`） | 同 ssh | 同 ssh |
| `colab_sandbox.py` | `run_project`（`:155`） | 参数表止于 `env_overrides` | 其后加 `run_id` |

**签名一致性**: 与 DESIGN §4.1 一致 ✅

### 4.4 三个 agent 后端

改前（以 collider `:71` 为例，biology `:80`、stat `:63` 同形）：

```python
    def run(
        self,
        prompt_text: str,
        *,
        timeout_sec: int | None = None,
    ) -> SandboxResult:
```

改后：

```python
    def run(
        self,
        prompt_text: str,
        *,
        timeout_sec: int | None = None,
        run_id: str | None = None,
    ) -> SandboxResult:
```

`run_project`（collider `:173`、biology `:178`、stat `:150`）在 `env_overrides` 之后追加 `run_id: str | None = None,`。

**签名一致性**: 与 DESIGN §4.2 一致 ✅

### 4.5 契约测试（新增 `tests/test_sandbox_protocol_contract.py`）

```python
"""Contract: every sandbox backend mirrors SandboxProtocol's keyword surface."""

from __future__ import annotations

import inspect

import pytest

from researchclaw.experiment.biology_agent_sandbox import BiologyAgentSandbox
from researchclaw.experiment.colab_sandbox import ColabDriveSandbox
from researchclaw.experiment.collider_agent_sandbox import ColliderAgentSandbox
from researchclaw.experiment.docker_sandbox import DockerSandbox
from researchclaw.experiment.sandbox import ExperimentSandbox, SandboxProtocol
from researchclaw.experiment.ssh_sandbox import SshRemoteSandbox
from researchclaw.experiment.stat_agent_sandbox import StatAgentSandbox

_IMPLS = (
    ExperimentSandbox,
    DockerSandbox,
    SshRemoteSandbox,
    ColabDriveSandbox,
    ColliderAgentSandbox,
    BiologyAgentSandbox,
    StatAgentSandbox,
)


def _kw_only(fn) -> tuple[str, ...]:
    return tuple(
        name
        for name, param in inspect.signature(fn).parameters.items()
        if param.kind is inspect.Parameter.KEYWORD_ONLY
    )


@pytest.mark.parametrize("method", ["run", "run_project"])
def test_keyword_surface_matches_protocol(method: str) -> None:
    expected = _kw_only(getattr(SandboxProtocol, method))
    assert "run_id" in expected
    for impl in _IMPLS:
        assert _kw_only(getattr(impl, method)) == expected, impl.__name__
```

只比对 keyword-only 名与顺序（DESIGN §2.1.1-2）；默认值、首位置参名不纳入。

### 4.6 `_TtlWatcher` 改名（`docker_sandbox.py`）

| 改前行 | 改前 | 改后 |
|---|---|---|
| `:72` | `self._stop = threading.Event()` | `self._stop_event = threading.Event()` |
| `:77` | `self._stop.set()` | `self._stop_event.set()` |
| `:91` | `while not self._stop.is_set():` | `while not self._stop_event.is_set():` |
| `:95` | `if self._stop.wait(min(self._poll, remaining)):` | `if self._stop_event.wait(min(self._poll, remaining)):` |
| `:97` | `if self._stop.is_set():` | `if self._stop_event.is_set():` |
| `:103` | `while not self._stop.is_set():` | `while not self._stop_event.is_set():` |
| `:106` | `if self._stop.wait(min(self._poll, 1.0)):` | `if self._stop_event.wait(min(self._poll, 1.0)):` |
| `:143` | `if self._stop.wait(self._grace):` | `if self._stop_event.wait(self._grace):` |

配套：`tests/test_sandbox_boundary.py:268` → `assert watcher._stop_event.is_set()`。

### 4.7 前端常量（`api.js:89`）

改后：

```javascript
  'tool.call', 'tool.result', 'tool.orphan_call', 'llm.call', 'llm.result',
```

### 4.8 CI 与陈旧断言

| 文件 | 行 | 改后 |
|---|---|---|
| `ci.yml` | `:166` | `          python -m pip install -e ".[dev,server,mcp]"` |
| `test_web_platform.py` | `:33` | `        assert cfg.host == "127.0.0.1"` |
| `test_web_platform.py` | `:35` | `        assert cfg.cors_origins == ("http://localhost:3000", "http://127.0.0.1:3000")` |

## 5. 兼容性

### 5.1 Python 版本兼容

| Python 版本 | 支持 | 说明 |
|---|---|---|
| 3.11 / 3.12 | ✅ | 改名后不再触碰 `Thread._stop()`；本机无解释器，**由 CI 矩阵举证** |
| 3.13 | ✅ | 本地可跑；现网基线亦绿 |
| 3.14 | ✅ | 由 CI 矩阵举证 |

### 5.2 依赖兼容

零新增依赖；`.[dev,server,mcp]` 三项在 Tests job 已组合使用（同 runner），无新组合风险。

### 5.3 向后兼容

| 面 | 影响 | 处理 |
|---|---|---|
| 公开 Python API | `run`/`run_project` 仅**新增** keyword-only 可选参 | 旧调用零改动；位置调用不受影响 |
| 第三方后端（若存在） | 未实现 `run_id` 仍可工作（协议不强制运行时校验） | 由契约测试提示补齐，不做运行时断言 |
| 前端 | `EVENT_TYPES` 增 1 项 | 消费者按名匹配，新增项不破坏旧逻辑 |
| 配置/序列化 | 无变化 | 无迁移 |

## 6. 错误处理实施

| 错误场景（DESIGN §7） | 异常类型 | 处理代码 | 测试 |
|---|---|---|---|
| 新后端漏 `run_id` | 无（静态断言失败） | 契约测试逐实现比对 | `test_sandbox_protocol_contract.py` |
| 调用点传参到未改造后端 | `TypeError` | 由契约测试在合入前拦住 | 同上 + `test_rc_executor.py` |
| 非 Docker 收到 `run_id` | 无（显式 no-op） | 形参未读取（I-2） | 契约测试（签名含 `run_id`） |
| 3.11/3.12 `join()` 私有名遮蔽 | `TypeError`（改名后消失） | `_stop_event` 全量替换 | `test_sandbox_boundary.py` |
| spec-gates 缺 extras | `ImportError` → `ci_coverage_check` exit 1 | `ci.yml:166` | CI spec-gates job |
| 前端常量不等 | `AssertionError` | `api.js` 补项 | 前端事件类型一致性测试 |
| 陈旧 web 断言 | `AssertionError` | 测试两行修正 | `test_web_platform.py` |

## 7. 不变式实施

| 不变式（DESIGN §8） | 实施位置 | 验证方式 |
|---|---|---|
| I-1 协议面单一真值 | 14 处签名 + 契约测试 | `test_keyword_surface_matches_protocol` 2 用例 |
| I-2 语义不扩张 | 6 个非 Docker 后端函数体零改动 | `git diff -U0` 人工确认仅签名行变化 |
| I-3 fail-closed 不动 | 不改 `config.py` | `test_cors_default.py` 4 用例 + `test_web_platform.py` |
| I-4 事件类型单一真值 | `api.js` 镜像 1 项 | 前端事件一致性测试 |
| I-5 私有实现不遮蔽 | `_stop_event` | `grep -n "self\._stop\b" docker_sandbox.py` 为 0 + boundary 19 用例 |
| I-6 本地=CI 安装面 | `ci.yml:166` | CI spec-gates job 收集 0 错误 |
| I-7 零新增依赖 | 不改 `pyproject.toml` | `git diff --stat` 无该文件 |

## 8. 测试策略

### 8.1 单元测试

| 模块 | 测试文件 | 用例数 | 说明 |
|---|---|---|---|
| 协议面契约 | `test_sandbox_protocol_contract.py` | 2 | 新增；无外部依赖，仅 `inspect` |
| Docker TTL | `test_sandbox_boundary.py` | 19 | 既有，改名后须全绿 |
| 执行器 | `test_rc_executor.py` | 207 | 既有，14 failed 基线须归零 |

### 8.2 集成测试（读数表 = 验收口径）

| 命令 | 基线（P-115） | 目标 |
|---|---|---|
| `python -m pytest tests/test_rc_executor.py -q` | 14 failed / 193 passed | **0 failed** |
| `python -m pytest tests/test_sandbox_boundary.py -q` | 19 passed | 19 passed |
| `python -m pytest tests/test_event_stream.py tests/test_web_platform.py tests/test_cors_default.py tests/test_frontend_mount.py -q` | 2 failed / 81 passed / 10 skipped | **0 failed** |
| `python -m pytest tests/test_sandbox_protocol_contract.py -q` | 不存在 | 2 passed |
| `python scripts/spec/ci_coverage_check.py --check` | 0 | 0 |
| CI（四矩阵 + spec-gates） | 76 failed + spec-gates 红 | 全绿，**连续两次** |

### 8.3 属性测试

契约测试本身即「协议面属性」：对任意实现集合，keyword-only 名序列恒等于协议。不引入 hypothesis。

## 9. 幻觉抑制审查（Step 6 Review）

### 9.1 依赖版本验证

- [x] 零新增依赖，无需 PyPI 查询（§2.2 已说明）
- [x] 无虚构库/函数：`inspect.Parameter.KEYWORD_ONLY`、`inspect.signature` 均为 3.11+ 标准库稳定 API
- [x] 版本兼容性：`.[dev,server,mcp]` 组合在 Tests job 现存

### 9.2 接口签名验证

- [x] 14 处签名与 DESIGN §4.1/§4.2 逐项一致（本文件 §4.1-§4.4 给出改前原文）
- [x] 可实现：均为可选 keyword-only，无不可能的类型组合
- [x] 契约测试可导入 7 个实现（类名与模块路径已逐文件核对）

### 9.3 实施与设计对齐

- [x] 12 个文件与 DESIGN §3.2 模块表逐条对应
- [x] 每个接口对应 DESIGN §4 的一节
- [x] 无设计未覆盖的实施项（D-6/D-7 显式不做，未混入）

### 9.4 低效操作排除

- [x] 无新增循环/O(n²)
- [x] 无新增 I/O（契约测试只反射签名）
- [x] 无重复计算

**未执行项**：第二基座独立复审（U-7）仍未执行，本文件为同基座施工单；若用户要求，可在实施前补做。

## 10. 实施步骤

### Step 0: 基线冻结

- 文件: —
- 内容: `git status --short` 确认工作区仅本批文件；沿用 P-115 基线读数（`test_rc_executor.py` 14 failed / 193 passed / 151.42s）。若环境有漂移嫌疑，先复跑该文件并记录。
- 测试: 无

### Step 1: 契约测试先行（红）

- 文件: `tests/test_sandbox_protocol_contract.py`（新增）
- 内容: 按 §4.5 全文落盘
- 测试: `python -m pytest tests/test_sandbox_protocol_contract.py -q` → **预期 2 failed**（`run`/`run_project` 各 1，首差即断）

### Step 2: R-1 协议面

- 文件: `sandbox.py`
- 内容: `SandboxProtocol` 2 处（`:299`/`:301`）+ `ExperimentSandbox` 2 处（`:319`/`:358`）
- 测试: 契约测试仍红（其余 5 后端未改）

### Step 3: R-1 五个后端

- 文件: `ssh_sandbox.py`、`colab_sandbox.py`、`collider_agent_sandbox.py`、`biology_agent_sandbox.py`、`stat_agent_sandbox.py`
- 内容: 每文件 `run`/`run_project` 各 1 处，共 10 处
- 测试: `python -m pytest tests/test_sandbox_protocol_contract.py -q` → **2 passed**

### Step 4: R-1 回归

- 文件: —
- 内容: 无改动
- 测试: `python -m pytest tests/test_rc_executor.py -q` → **0 failed**（基线 14 failed）；`python -m pytest tests/test_sandbox_boundary.py -q` → 19 passed

### Step 5: R-4 改名

- 文件: `docker_sandbox.py`、`tests/test_sandbox_boundary.py`
- 内容: §4.6 的 8 行替换 + 测试 `:268` 一行
- 测试: `grep -n "self\._stop\b" researchclaw/experiment/docker_sandbox.py` → 0 命中

### Step 6: R-4 回归

- 文件: —
- 测试: `python -m pytest tests/test_sandbox_boundary.py -q` → 19 passed；`grep -rn "\._stop\b" tests/` → 0 命中

### Step 7: R-2 前端常量

- 文件: `frontend-legacy/src/services/api.js`
- 内容: §4.7 单行
- 测试: `python -m pytest tests/test_event_stream.py -q` → 原有失败归零；`node --check frontend-legacy/src/services/api.js`（无 node 则记环境缺口）

### Step 8: R-5 CI 安装面

- 文件: `.github/workflows/ci.yml`
- 内容: §4.8 单行
- 测试: `python scripts/spec/ci_coverage_check.py --check` → 0；CI spec-gates job 转绿（需 push 后观察）

### Step 9: R-3 陈旧断言

- 文件: `tests/test_web_platform.py`
- 内容: §4.8 两行
- 测试: `python -m pytest tests/test_web_platform.py tests/test_cors_default.py -q` → 0 failed

### Step 10: 全量、派生视图与推送

- 文件: `docs/PROGRESS.md`、session、`docs/REPO_STATS.md`、`docs/CONSOLE.md`
- 内容: 四文件合集复跑；`repo_stats.py --write`、`console_gen.py`；`git add` 明确路径；`step_enforce`
- 测试: §8.2 全部命令 + `python -m pytest -m "not heavy" -q`（CI 等价）；`git push` 后观察四矩阵与 spec-gates，**连续两次全绿**方可触发 U-5 回填与分支保护

### 回滚方案（单点，按序）

1. `ci.yml` 一行 revert（恢复 `.[dev]`）→ spec-gates 回到红，不影响其他；
2. `api.js` 一行 revert → 前端守卫回到红；
3. `test_web_platform.py` 两行 revert → 断言回到陈旧态；
4. `_stop_event` 整体 revert（9 行）→ 3.13 绿、3.11/3.12 恢复红；
5. R-1 反向 revert 顺序：先撤 5 个后端，再撤 `sandbox.py` 与契约测试（因契约测试会立即报红，回滚必须成对）。

---

**Review 签字**: 同基座自审（Step 6 清单） 日期: 2026-11-15
