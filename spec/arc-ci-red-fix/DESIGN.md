---
id: arc-ci-red-fix-DESIGN
type: design
version: 1.1
status: draft
date: 2026-11-15
depends: [arc-ci-red-fix-RESEARCH]
upstream: arc-ci-red-fix-RESEARCH
---

# 设计文档：CI 红面修复（P-116 设计批）

> **Feature**：P-116，CI 红面修复设计（承接 P-115 调研，零生产代码）。
> **创建日期**：2026-11-15
> **状态**：草稿（Step 4 自审已执行；第二基座独立复审未执行，见 U-7）
> **Spec 步骤**：Step 3-4（T3 设计批）
> **基于调研**：[调研文档 v1.4](RESEARCH.md)

## 1. 设计目标

把 P-115 定位的五类红面收敛为一次可回滚的单批实施：**R-1 恢复默认 sandbox 路径的 iterative refine**（真实生产回归，优先级最高），**R-4 消除解释器版本相关的私有属性遮蔽**，**R-2/R-3/R-5 三处对齐与配置漂移**清零，使 CI 具备达成「连续两次全绿」的条件（分支保护的前置，见 arc-ci-cd-research IMPLEMENTATION §10 Step 5）。

判定标准：四矩阵（3.11/3.12/3.13/3.14）+ spec-gates job 全绿；本地 `test_rc_executor.py` 由 14 failed 转 0；修复不改变 Docker 的 TTL/标签语义、不改变 `ServerConfig` 的 fail-closed 默认值、不新增运行时依赖。

## 2. 设计依据

### 2.1 调研结论

| 调研发现 | 设计决策 | 引用 |
|---|---|---|
| R-1 `run_id` 只在 Docker 后端存在，默认 `sandbox` 模式 refine 必崩 | **D-1** 协议面统一 keyword-only `run_id: Optional[str] = None`，非 Docker 后端接受并忽略 | RESEARCH §3.2、§8.1 |
| R-4 `_TtlWatcher._stop` 实例属性遮蔽 `Thread._stop()`，≤3.12 `join()` 崩 | **D-2** 改名 `_stop_event`（含 1 处测试外部引用） | RESEARCH §3.3、本文件 §2.1.1-2 |
| R-2 前端 `EVENT_TYPES` 缺 `tool.orphan_call` | **D-3** 前端常量镜像补项（后端为真值源） | RESEARCH §3.4 |
| R-3 `test_web_platform.py` 两条断言与实现相反 | **D-4** 以实现为真值，只改测试两行；`config.py` 不动 | RESEARCH §3.5、§8.2 |
| R-5 spec-gates 装 `.[dev]` 缺 `mcp` 与 `server` | **D-5** 改 `.[dev,server,mcp]`，与 Tests job 对齐 | RESEARCH §3.6 |
| U-4 `ci_coverage_check` 收集失败专属提示 | **D-6 本批不实施**（触发条件见 U-4） | RESEARCH §6 |
| U-5 CHECKLIST 回填时点 | **D-7** 修复批取得连续两次全绿后回填（触发条件见 U-5） | RESEARCH §6 |

判定口径：R-1..R-5 每条有且仅有一个承载决策（D-1..D-5）；D-6/D-7 是**显式「本批不做」**，不是遗漏。

### 2.1.1 本设计批取证补强（均一手读码，相对 RESEARCH 的两处口径修正）

1. **R-4 半径 +1 文件（RESEARCH §3.3 的「仅类内使用」被证伪）**：[test_sandbox_boundary.py#L268](../../tests/test_sandbox_boundary.py#L268) 断言 `watcher._stop.is_set()`——这是**类外**引用。改名必须同步改该行，否则 `test_t9_watcher_lifecycle_stop_and_join` 转红。故 R-4 = `docker_sandbox.py` 8 处 + 该测试 1 行。
2. **契约测试口径收窄（RESEARCH §8.1 验收句过宽）**：「7 个实现的 `run`/`run_project` 形参名集合逐项一致」**无法按字面实现**，因为：
   - `run` 首位置参名本就不同：`code`（sandbox/docker/ssh/colab）vs `prompt_text`（collider/biology/stat，见各自 `run` 定义）；
   - `timeout_sec` 默认值不同：协议 `= 300`，三个 agent 后端 `int | None = None`（缺省回落 `config.timeout_sec`）。
   故契约面 = **keyword-only 形参名集合 + 声明顺序**，并要求集合含 `run_id`；默认值与首位置参名不纳入（纳入即会误报既有合法差异）。
3. **签名面复核**：缺口恰为 **14 处** = `SandboxProtocol` 2（`#L299`、`#L301`）+ `ExperimentSandbox` 2（`#L319`、`#L358`）+ `SshRemoteSandbox` 2（`#L56`、`#L69`）+ `ColabDriveSandbox` 2（`#L141`、`#L155`）+ `ColliderAgentSandbox` 2（`#L71`、`#L173`）+ `BiologyAgentSandbox` 2（`#L80`、`#L178`）+ `StatAgentSandbox` 2（`#L63`、`#L150`）。Docker 两处已有（`#L237`、`#L255`），不在改动面。
4. **`_stop` 命中面复核**：`docker_sandbox.py` 全文件恰 8 行（`#L72` 定义 + `#L77/91/95/97/103/106/143` 使用），与 RESEARCH 一致；类外引用仅上述测试 1 处。

### 2.2 相关 ADR

本批不引用 ADR：治理约束以 [SPEC_PROCESS.md](../SPEC_PROCESS.md) 为准；安全默认的裁决出处为 P-006（Q19/H-8），已在 RESEARCH §3.5/§8.2 取证。

### 2.3 职责边界

- **职责内**：`SandboxProtocol` 与其实现的签名一致性、`_TtlWatcher` 私有属性命名、前端事件常量镜像、`test_web_platform.py` 陈旧断言、spec-gates 安装面。
- **职责外**（有独立范式，本设计不回答）：CI 平台能力扩展（lint/类型/覆盖率、Windows 矩阵，已在 arc-ci-cd-research D-8/D-9 显式不实施）；`researchclaw/vendor/**` 内容。
- **能力边界**（本设计做不到，不承诺）：本机无 3.11/3.12 解释器，R-4 的转绿**只能由 CI 矩阵证明**，本地仅能证明 3.13 不回归；U-2 的「1 条差额」已由 P-118 用 CI 日志闭合（四矩阵均 14 条，无差额，RESEARCH §11），不再是前置。
- **明确不动**：`config.py` 的 `127.0.0.1` / 显式 cors / `validate_server_security`（Q19 fail-closed 真值）；Docker 的 TTL 门控与 `rc.run` 标签逻辑；`ExperimentConfig.mode` 默认值。

## 3. 架构设计

### 3.1 整体架构（协议面 + 漂移面两层）

| 层 | 载体 | 职责 | 真值源 |
|---|---|---|---|
| 协议面 | [sandbox.py#L296](../../researchclaw/experiment/sandbox.py#L296) `SandboxProtocol` | 定义所有后端必须接受的关键字形参 | 协议声明 |
| 实现面 | 7 个后端（含 Docker） | 逐项实现协议；`run_id` 仅 Docker 消费 | `inspect.signature` |
| 漂移面 | 前端常量 / 测试断言 / CI 安装串 / 私有属性名 | 与真值源对齐 | 后端常量、`ServerConfig`、Tests job |

### 3.2 模块划分

| 模块 | 变更类型 | 说明 | 预估行 |
|---|---|---|---|
| [sandbox.py](../../researchclaw/experiment/sandbox.py) | 改 | Protocol 2 处 + ExperimentSandbox 2 处签名；Protocol docstring 注明 `run_id` 语义 | 6 |
| [ssh_sandbox.py](../../researchclaw/experiment/ssh_sandbox.py) | 改 | `run` / `run_project` 各加 1 个 keyword-only 形参 | 2 |
| [colab_sandbox.py](../../researchclaw/experiment/colab_sandbox.py) | 改 | 同上 | 2 |
| [collider_agent_sandbox.py](../../researchclaw/experiment/collider_agent_sandbox.py) | 改 | 同上 | 2 |
| [biology_agent_sandbox.py](../../researchclaw/experiment/biology_agent_sandbox.py) | 改 | 同上 | 2 |
| [stat_agent_sandbox.py](../../researchclaw/experiment/stat_agent_sandbox.py) | 改 | 同上 | 2 |
| [docker_sandbox.py](../../researchclaw/experiment/docker_sandbox.py) | 改 | `_stop` → `_stop_event` 纯重命名 8 处 | 8 |
| [api.js](../../frontend-legacy/src/services/api.js) | 改 | `EVENT_TYPES` 补 `tool.orphan_call` | 1 |
| [ci.yml](../../.github/workflows/ci.yml) | 改 | spec-gates 安装串 `.[dev]` → `.[dev,server,mcp]` | 1 |
| [test_web_platform.py](../../tests/test_web_platform.py) | 改 | `:33` host、`:35` cors 两条断言 | 2 |
| [test_sandbox_boundary.py](../../tests/test_sandbox_boundary.py) | 改 | `:268` 跟随属性改名 | 1 |
| `tests/test_sandbox_protocol_contract.py` | **新增** | 协议 keyword-only 面契约测试（防再次漂移） | ~45 |

总半径：**11 个修改文件 + 1 个新增测试 = 12 文件**（相对 RESEARCH §5 的 11 文件，因 R-4 测试引用 +1，见 §2.1.1-1）。

### 3.3 数据流：`run_id` 的落点

```
pipeline/stage_impls/_execution.py（4 处传参：:551 / :557 / :1644 / :1770）
  → SandboxProtocol.run / run_project（声明 run_id，keyword-only，缺省 None）
      → DockerSandbox：TTL 门控 + `--label rc.run=<run_id>`（唯一消费者，行为不变）
      → 其余 6 个后端：接受形参，不读取（无分支、无日志依赖）
```

4 处不传参的调用点（`experiment_repair.py#L811`、`_execution.py#L289`、`#L472`、`pipeline/code_agent.py#L1394`）不受影响，缺省 `None` 即旧行为。

### 3.4 控制流：mode → 后端映射（为何不做条件传参）

`create_sandbox` 共 7 个 mode 分支 + 默认回退：`docker`（**daemon 不可达时回退 `ExperimentSandbox`**，[factory.py#L29](../../researchclaw/experiment/factory.py#L29)）、`ssh_remote`、`colab_drive`、`collider_agent`、`biology_agent`、`stat_agent`、默认 `sandbox`。`mode=docker` 仍可能实际运行在 `ExperimentSandbox` 上，故「按 mode 决定是否传 `run_id`」不可靠（RESEARCH §8.1 取证 6）；协议面统一是唯一不遗漏的形态。

## 4. 接口定义

### 4.1 `SandboxProtocol`（`sandbox.py`，改后）

```python
class SandboxProtocol(Protocol):
    """Structural type for sandbox backends."""

    def run(self, code: str, *, timeout_sec: int = 300,
            run_id: str | None = None) -> SandboxResult: ...

    def run_project(
        self,
        project_dir: Path,
        *,
        entry_point: str = "main.py",
        timeout_sec: int = 300,
        args: list[str] | None = None,
        env_overrides: dict[str, str] | None = None,
        run_id: str | None = None,
    ) -> SandboxResult: ...
```

`run_id` docstring 口径（仅在协议声明处写一次，避免 12 处重复注释）：「仅 docker 后端用于 `rc.run` 标签与 TTL 门控；非容器后端接受该参数但不读取」。

### 4.2 `ExperimentSandbox` 与 5 个非 Docker 后端（改后）

`ExperimentSandbox`（`#L319`/`#L358`）、`SshRemoteSandbox`（`#L56`/`#L69`）、`ColabDriveSandbox`（`#L141`/`#L155`）与协议同形。三个 agent 后端（collider/biology/stat）保持首位置参 `prompt_text` 与 `timeout_sec: int | None = None` 不变，仅追加：

```python
def run(
    self,
    prompt_text: str,
    *,
    timeout_sec: int | None = None,
    run_id: str | None = None,
) -> SandboxResult: ...

def run_project(
    self,
    project_dir: Path,
    *,
    entry_point: str = "main.py",
    timeout_sec: int = 300,
    args: list[str] | None = None,
    env_overrides: dict[str, str] | None = None,
    run_id: str | None = None,
) -> SandboxResult: ...
```

Docker（`#L237`/`#L255`）**不改**：已是 `run_id: str | None = None`。

### 4.3 新增契约测试 `tests/test_sandbox_protocol_contract.py`

```python
_IMPLS = (ExperimentSandbox, DockerSandbox, SshRemoteSandbox, ColabDriveSandbox,
          ColliderAgentSandbox, BiologyAgentSandbox, StatAgentSandbox)

def _kw_only(fn) -> tuple[str, ...]:
    return tuple(n for n, p in inspect.signature(fn).parameters.items()
                 if p.kind is inspect.Parameter.KEYWORD_ONLY)

@pytest.mark.parametrize("method", ["run", "run_project"])
def test_keyword_surface_matches_protocol(method):
    expected = _kw_only(getattr(SandboxProtocol, method))
    for impl in _IMPLS:
        assert _kw_only(getattr(impl, method)) == expected, impl.__name__
    assert "run_id" in expected
```

只断言 keyword-only 名集合与顺序（理由见 §2.1.1-2）；`agentic_sandbox.py`、`experiment/code_agent.py` 不实现 `run`/`run_project`，`pipeline/code_agent.py` 的 `_SandboxLike` 是本地窄 Protocol，均不在契约面。

### 4.4 `_TtlWatcher` 属性改名（`docker_sandbox.py`）

`self._stop` → `self._stop_event`（`#L72` 定义 + `#L77/91/95/97/103/106/143` 使用）；`tests/test_sandbox_boundary.py#L268` 同步为 `watcher._stop_event.is_set()`。无公开接口变化。

### 4.5 前端事件常量（`api.js`）

`'tool.result'` 之后插入 `'tool.orphan_call'`，与 [event_log.py#L40](../../researchclaw/runtime/event_log.py#L40) 对齐；`TERMINAL_EVENTS` 不变。

### 4.6 CI 安装面（`ci.yml#L166`）

`python -m pip install -e ".[dev]"` → `python -m pip install -e ".[dev,server,mcp]"`（与 Tests job `#L121` 对齐）。

### 4.7 陈旧断言（`test_web_platform.py`）

`:33` `assert cfg.host == "127.0.0.1"`；`:35` `assert cfg.cors_origins == ("http://localhost:3000", "http://127.0.0.1:3000")`。

## 5. 替代方案

### 5.1 D-1（`run_id` 协议面）

| 方案 | 结论 | 理由 |
|---|---|---|
| A **协议面统一 keyword-only 可选形参**（选定） | 是 | 单一真值源；调用点无需判断；新增后端由契约测试强制 |
| B 调用点 `isinstance(sandbox, DockerSandbox)` | 否 | 破坏 Protocol 抽象；4 处调用点重复判断；新增后端需回溯改调用点 |
| C 回退调用点的 `run_id` | 否 | 丢失 P-105 的容器归因与 TTL 清理能力，功能倒退 |
| D 按 `config.mode` 条件传参 | 否 | `factory.py#L29` 证明 `mode=docker` 可回退本地后端 |
| E `inspect.signature` 运行时探测 | 否 | 隐式契约、不可静态检查，掩盖签名漂移 |

### 5.2 D-2（`_stop` 遮蔽）

| 方案 | 结论 | 理由 |
|---|---|---|
| A **改名 `_stop_event`**（选定） | 是 | 唯一根治；私有属性无 ABI 承诺；改动 9 行纯重命名 |
| B 覆写 `_stop()` 方法转发到 Event | 否 | `Thread.join()` 内部依赖 `_stop()` 的无参调用语义，覆写后返回值/异常面不可控，且仍占用基类私有名 |
| C 放弃继承 `Thread`，改 `Event` + 后台轮询线程 | 否 | 生命周期语义（`join`/`is_alive`/异常传播）需重写，收益为零 |
| D CI 固定 3.13、放弃 3.11/3.12 | 否 | 与 `requires-python` 及现存四矩阵冲突，属缩小支持面 |

### 5.3 D-3（前端常量漂移）

| 方案 | 结论 | 理由 |
|---|---|---|
| A **前端镜像补 1 项**（选定） | 是 | 与既有守卫（双向集合相等）同构；零运行时风险 |
| B 由 `event_log.py` 生成前端常量 | 否 | 引入构建步骤与生成物入库，收益不抵复杂度 |
| C 测试改子集断言 | 否 | 直接废掉漂移守卫 |

### 5.4 D-4（web 默认值真值）

| 方案 | 结论 | 理由 |
|---|---|---|
| A **以实现为真值，改测试两行**（选定） | 是 | `127.0.0.1` 被 `test_cors_default.py` 双向锁定（RESEARCH §8.2 取证 3） |
| B 实现改 `0.0.0.0` | 否 | 默认构造立即违反 `validate_server_security`，`test_cors_default.py#L33` 转红，与 Q19/H-8 fail-closed 冲突 |

### 5.5 D-5（spec-gates 安装面）

| 方案 | 结论 | 理由 |
|---|---|---|
| A **补 `server` + `mcp` extras**（选定） | 是 | 与 Tests job 同集合；修的是环境声明而非掩盖失败 |
| B 给 3 个测试文件加 `importorskip` | 否 | 让「CI 缺依赖」伪装成 skip，削弱 I-6 本地=CI 同判 |
| C 把 3 个文件移出收集面 | 否 | 其内容（MCP/事件 API）正是 spec-gates 的守卫对象，排除即失守 |

## 6. 数据结构

本批**不新增/不修改**任何数据结构：`SandboxResult`、`ServerConfig`、`EVENT_TYPES` 的形态与语义均不变；仅新增 1 个事件类型**字符串值**（后端已存在，前端补镜像）与若干方法形参。故无 schema 迁移、无配置迁移、无序列化兼容问题。

## 7. 错误处理（失败语义表）

| 失败点 | 行为 | 对使用者的一句话 |
|---|---|---|
| 新增后端漏写 `run_id` | 契约测试失败（keyword-only 面不等） | 「后端签名与协议不一致：补齐 `run_id`」 |
| 调用点传 `run_id` 到未改造后端 | `TypeError: unexpected keyword argument` | 「该后端尚未实现协议：按契约测试报错修复」 |
| 非 Docker 后端收到 `run_id` | 接受并忽略（无异常、无日志噪音） | 无需用户感知 |
| 3.11/3.12 `join()` 再遇私有名冲突 | `TypeError: 'Event' object is not callable` | 「`_TtlWatcher` 属性名不得与 `Thread` 私有方法同名」 |
| spec-gates 仍缺 extras | 收集 ImportError → `ci_coverage_check` exit 1 | 「spec-gates 安装面与 Tests job 不一致」 |
| 前端常量与后端不等 | `test_frontend_event_types_match_runtime` 失败 | 「补 `frontend-legacy/src/services/api.js` 的 `EVENT_TYPES`」 |
| 测试断言与实现相反 | `test_server_config_defaults` 失败 | 「以实现为真值改测试，不改配置默认」 |

原则：不新增静默降级；R-1 的「接受但忽略」是**显式声明**的 no-op，非降级。

## 8. 不变式（Invariants）

- **I-1 协议面单一真值**：`SandboxProtocol.run`/`run_project` 的 keyword-only 形参名集合与顺序，等于 7 个实现的对应集合；`run_id` 必在其中。
- **I-2 语义不扩张**：除 Docker 外，任何后端不得读取 `run_id`；Docker 的 TTL 门控与 `rc.run` 标签逻辑逐字节不变。
- **I-3 fail-closed 不动**：`ServerConfig` 默认 `127.0.0.1` + 显式 cors + `validate_server_security` 不变。
- **I-4 事件类型单一真值**：后端 `EVENT_TYPES` 为唯一声明源，前端常量必须与之双向集合相等。
- **I-5 私有实现不遮蔽**：类内实例属性不得与基类/解释器私有方法同名。
- **I-6 本地=CI 安装面**：spec-gates 的 extras 必须覆盖其收集面所需的导入（`server` + `mcp` + `dev`）。
- **I-7 零新增依赖**：不新增运行时或 dev 依赖；不改 `pyproject.toml`。

## 9. 幻觉抑制审查（Step 4 Review）

### 9.1 设计基于已验证的调研结论

- [x] 所有设计决策可追溯到 RESEARCH.md（§2.1 映射表覆盖 R-1..R-5）
- [x] 无未经验证的假设：§2.1.1 四项均本批逐行读码/`grep` 复核（签名 14 处行号、`_stop` 8 行、测试 `:268`、类名 7 个）
- [x] 无论证驱动的归因扭曲：R-1 崩溃面按「含 docker 回退共 7 后端」如实计入，未裁剪为单点
- [x] 接口签名真实：§4 全部取自源码现状（`#L237`/`#L255` 的 Docker 形参、agent 的 `prompt_text` 首位置参与 `timeout_sec=None` 默认均为实测形态）

**自审发现的两处上游修正（已回填 §2.1.1，均不改变 D-1..D-5）**

| # | 修正 | 证据 | 影响 |
|---|---|---|---|
| 1 | R-4 半径由「纯重命名」扩为「+1 测试行」 | [test_sandbox_boundary.py#L268](../../tests/test_sandbox_boundary.py#L268) `watcher._stop.is_set()` | 文件数 11 → 12 |
| 2 | 契约测试由「形参名集合逐项一致」收窄为「keyword-only 面一致」 | `code` vs `prompt_text`；`300` vs `None` | 验收口径可执行 |

### 9.2 替代方案审查

- [x] 每个决策至少列 2 个替代方案（D-1 五案、D-2 四案、D-3 三案、D-4 两案、D-5 三案）
- [x] 否决理由均基于可核对事实（factory 回退行号、`validate_server_security` 与 `test_cors_default.py` 的双向锁定、dev extra 缺项）

### 9.3 职责边界审查

- [x] 职责边界清晰（§2.3 区分职责外与能力边界）
- [x] 不越界：不纳入 lint/覆盖率（D-8）、不纳入 Windows 矩阵（D-9）、不改 Docker 语义、不重构 sandbox 架构
- [ ] **第二基座独立复审未执行**：本版为同基座自审 + 逐行复核；按 P-108 先例的证伪式独立复审登记为 U-7，不伪称已执行

## 10. 对实施的输入

### 10.1 关键工程约束

1. **单批单提交**：五项互不冲突，混批会放大回滚面；提交面 = §3.2 的 12 文件 + 流程件（DESIGN/PROGRESS/session/派生视图）。
2. **顺序**：先 R-1（含契约测试）→ R-4（含测试行）→ R-2/R-5/R-3；R-1 与 R-4 各自独立可验证。
3. **不改 `config.py`、不改 `pyproject.toml`、不改 Docker 的 TTL/标签代码**。
4. **R-4 的转绿只能由 CI 证明**：本地 3.13 只证明不回归；实施批须显式记录「本地 3.13 绿 ≠ 3.11/3.12 绿」。
5. 新增契约测试须在无 Docker / 无外部服务的环境下可跑（仅 `inspect`，不实例化后端）。
6. 实施后刷新派生视图（`repo_stats.py --write`、`console_gen.py`），并保持 `ci_coverage_check --check` 为 0。

### 10.2 风险与缓解

| ID | 风险 | 缓解 |
|---|---|---|
| RI-1 | 给 6 个后端加形参时漏改某一处，契约测试只覆盖 keyword-only 面 | 契约测试 + `test_rc_executor.py` 14 条转绿双向证明 |
| RI-2 | `_stop` 改名遗漏 `#L143`（`_grace` 等待）导致 TTL 收尾失效 | 全文件 `grep _stop\b` 归零 + `test_sandbox_boundary.py` 19 用例 |
| RI-3 | agent 后端把 `run_id` 误用于会话/任务 ID，产生隐性行为变更 | I-2 明确「不读取」；review 只看是否出现引用 |
| RI-4 | spec-gates 补 extras 后安装变慢或触达网络失败 | 与 Tests job 同集合，已被同一 runner 验证过 |
| RI-5 | 本地绿、CI 红（R-4 版本相关）造成误判结案 | 验收以 CI 四矩阵读数为准，本地读数只作不回归证据 |

### 10.3 实施批次建议与验收读数

单批（B1）交付。验收：

| 项 | 基线（P-115） | 目标 |
|---|---|---|
| `pytest tests/test_rc_executor.py` | 14 failed / 193 passed | **0 failed** |
| `pytest tests/test_sandbox_boundary.py` | 19 passed（3.13） | 19 passed（3.13 不回归）；3.11/3.12 的 6 条经 CI 转绿 |
| `test_event_stream + test_web_platform + test_cors_default + test_frontend_mount` | 2 failed / 81 passed / 10 skipped | **0 failed** |
| `tests/test_sandbox_protocol_contract.py` | 不存在 | 2 passed |
| `ci_coverage_check --check` | 0（本地有 extras） | 0 |
| CI | 76 失败（22/22/16/16）+ spec-gates 红 | 四矩阵 + spec-gates 全绿，连续两次 |

## 11. 未决项登记（四元块）与决策矩阵

**对上游未决项的处置**：U-1/U-3 已在 RESEARCH §8 裁决，本设计直接消费（D-1/D-4），不改判；U-6 已收窄关闭（README 无 `0.0.0.0` 声明）。

**11.1 未决项登记**

- ~~**U-2 R-1 CI 13 条 vs 本地 14 条的 1 条差额**~~：**已关闭（P-118，v1.1）**——CI 四矩阵逐 job 复核 R-1 均为 14 条，与本地同名同数，「13 条」系计数假象；判据「差额条目被指名」不再适用（无差额），证据见 RESEARCH §11。

- **U-4 `ci_coverage_check` 收集失败专属提示**
  - **判据**：出现「收集失败被误读为覆盖差异」的第二次实例
  - **触发条件**：再次发生 collect error 且日志尾部不可辨识
  - **当前倾向**：本批不实施（D-6）；加提示属增强，不解决环境声明错误
  - **证据等级**：E1（本次日志尾部只见 mcp 守卫错误，RESEARCH §3.6）

- **U-5 arc-ci-cd-research CHECKLIST 第二轮回填时点**
  - **判据**：CI 四矩阵 + spec-gates 连续两次全绿（runbook 前置）
  - **触发条件**：本批修复 push 后累计 2 次全绿 run
  - **当前倾向**：D-7——第二次全绿后立即回填 §2.3/§2.5/§2.6/I-5，再执行分支保护
  - **证据等级**：E1（runbook 前置条件原文，IMPLEMENTATION §10 Step 5）

- **U-7 第二基座独立复审**
  - **判据**：由不同基座子代理对 §2.1.1/§4/§8 做证伪式复核并签字
  - **触发条件**：进入实施批前（推荐），或首轮 CI 绿后补做
  - **当前倾向**：推荐实施批前补做；本版不伪称已完成（§9.3 末项）
  - **证据等级**：—（流程项）

**11.2 决策矩阵**：D-1..D-7 全部为 **Type-2（可逆）**——单文件/单词层改动，可单点回滚；不启动矩阵。

---

**Review 签字**：同基座自审（Step 4 清单 + 逐行复核） 日期: 2026-11-15
