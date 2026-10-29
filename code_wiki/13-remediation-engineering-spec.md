# 13 · 修复工程细节与接口契约

> 配套文档：[11-gap-remediation-research.md](11-gap-remediation-research.md)、[12-remediation-acceptance-checklist.md](12-remediation-acceptance-checklist.md)
> 定位：把 11 号文档中的修复方案落到**可实现的接口签名、数据 schema、版本约束、兼容策略与测试用例**。
> 状态：**设计稿（Proposed）**；除标注「现状」外，所有新接口均为建议，不代表已实现。

---

## 0. 阅读约定

- **现状**：当前仓库真实存在的代码/行为，附文件与行号。
- **Proposed**：建议新增或修改的接口，需要评审后实施。
- **MUST / SHOULD / MAY**：验收强制级别。
- 所有新增接口默认放在 `researchclaw/` 包内，不引入新的顶层命名空间。
- 所有路径参数使用 `pathlib.Path`；所有公开函数必须可被类型检查器推断。
- 新增代码必须兼容 Python 3.11（项目 `requires-python = ">=3.11"`）。

---

## 1. 版本与依赖矩阵

### 1.1 运行时版本

| 组件 | 现状 | 建议约束 | 本机验证 | 说明 |
|------|------|----------|----------|------|
| Python | `>=3.11`（`pyproject.toml:5`） | **不设上界**；CI 矩阵 3.11/3.12/3.13 阻断，3.14 非阻断 | 3.11.16 | 遵循 PyPA 建议，避免不必要的 upper bound |
| PyYAML | `>=6.0` | 不变 | — | 核心依赖 |
| rich | `>=13.0` | 不变 | — | 核心依赖 |
| arxiv | `>=2.1` | 不变 | — | 核心依赖 |
| numpy | `>=1.24` | 不变 | — | 核心依赖 |
| hatchling | **未锁定**（`pyproject.toml:41`） | CI 锁定实测版本；建议 `hatchling>=1.30,<2` | 本次复现为 PyPI 当前 1.30 系列 | 未锁定会导致 wheel 行为漂移 |
| build | 未声明 | `build>=1.2,<2`（开发/CI） | — | `python -m build` |
| FastAPI | 未声明 | `fastapi>=0.115,<1.0` | 0.133.1 | 仅 `server` extra |
| Uvicorn | 未声明 | `uvicorn[standard]>=0.30,<1.0` | 0.41.0 | 仅 `server` extra |
| httpx | `>=0.24`（`anthropic`/`dev`） | `httpx>=0.24,<1.0` | 0.28.1 | Anthropic/voice/测试共用 |
| MCP SDK | 未声明 | `mcp>=2.1,<3`（锁定 2.3.x） | 未安装；PyPI 2.3.0 可用 | 官方 SDK v2 高层 `MCPServer`；Python 3.11+ |
| pytest | `>=7.0`（`dev`） | `pytest>=8.0,<9` | 未安装 | 建议与 `pytest-asyncio>=0.23` 配套 |
| pytest-asyncio | `>=0.21`（`dev`） | `>=0.23,<1` | 未安装 | 异步 MCP 测试 |

### 1.2 协议/外部兼容版本

| 协议/接口 | 版本策略 |
|-----------|----------|
| OpenAI Chat Completions | 保持 `chat_completions` 默认；`responses` 继续可选 |
| Anthropic Messages API | 通过 `AnthropicAdapter`，不强制 SDK 版本；`httpx` 兼容 |
| MCP 基础协议 | 官方 SDK v2：支持 2026-07-28，并兼容 2025-11-25；v2 不再要求旧版 handshake/session |
| MCP Tasks 扩展 | 首期不启用；长任务用 `run_id` + `get_pipeline_status` 轮询；后续如需 Tasks，评估 `fastmcp[tasks]` |
| ACP | 保持 `acpx` 外部 CLI 约定，不新增协议版本 |
| checkpoint schema | 新增 `schema_version: 1`；读取器兼容 0/缺失 |
| cost_log schema | 新增 `schema_version: 1`（每行可选字段） |
| ExperimentSpec | 若保留，`schema_version: 1` |
| Agent run JSON | 新增 `schema_version: 1` |

### 1.3 extras 目标

```toml
[project.optional-dependencies]
server = ["fastapi>=0.115,<1.0", "uvicorn[standard]>=0.30,<1.0"]
mcp = ["mcp>=2.1,<3"]
voice = ["httpx>=0.24,<1.0"]
anthropic = ["httpx>=0.24,<1.0"]
web = ["scholarly>=1.7", "crawl4ai>=0.2", "tavily-python>=0.3"]
pdf = ["PyMuPDF>=1.23"]
all = [
  "fastapi>=0.115,<1.0", "uvicorn[standard]>=0.30,<1.0",
  "mcp>=2.1,<3", "httpx>=0.24,<1.0",
  "scholarly>=1.7", "crawl4ai>=0.2", "tavily-python>=0.3",
  "PyMuPDF>=1.23", "huggingface-hub>=0.20",
  "matplotlib>=3.7", "scipy>=1.10",
]
dev = [
  "pytest>=8.0,<9", "pytest-asyncio>=0.23,<1",
  "httpx>=0.24,<1.0", "build>=1.2,<2", "hatchling>=1.30,<2",
]
```

> 版本策略：**核心依赖保持轻量**；FastAPI/uvicorn/mcp 只进 extras。CI 必须至少跑一次 `pip install -e ".[server,mcp,voice]"`。

### 1.4 版本锁定策略

- `pyproject.toml` 只声明**兼容范围**（下限 + 主版本上限），便于用户安装；
- CI 使用 `constraints.txt`（或 uv/pip-tools lock）锁定实测版本：

```text
# constraints.txt（示例，版本以 CI 实测为准）
hatchling==1.30.*
build==1.*
fastapi==0.133.*
uvicorn==0.41.*
httpx==0.28.*
mcp==2.3.*
pytest==8.*
pytest-asyncio==0.23.*
```

- 安装命令：`pip install -e ".[dev,server,mcp,voice]" -c constraints.txt`；
- 升级依赖时只改 `constraints.txt` 并跑全量验收，不同时改接口；
- wheel 构建环境必须与 CI 使用同一 hatchling 锁定版本，避免「本地能构建、CI 失败」。

---

## 2. 打包契约（G1 / G5）

### 2.1 目标 `pyproject.toml`

```toml
[project]
requires-python = ">=3.11"
dependencies = [
    "pyyaml>=6.0",
    "rich>=13.0",
    "arxiv>=2.1",
    "numpy>=1.24",
]

[project.optional-dependencies]
server = ["fastapi>=0.115,<1.0", "uvicorn[standard]>=0.30,<1.0"]
mcp = ["mcp>=2.1,<3"]
voice = ["httpx>=0.24,<1.0"]
# ... 其余保留

[tool.hatch.build.targets.wheel]
packages = ["researchclaw"]

[build-system]
requires = ["hatchling>=1.30,<2"]
build-backend = "hatchling.build"
```

**MUST**：

- 删除 `[tool.hatch.build.targets.wheel.force-include]` 中 `researchclaw/templates/styles` 的自映射；
- 删除 `packages` 中的 `sibyl`、`arc`；
- 不把 `fastapi`/`uvicorn`/`mcp` 放进核心 `dependencies`。

### 2.2 Wheel 内容契约

wheel 必须包含以下资源（Hatchling 默认递归包目录）：

| 资源 | 示例路径 | 验证 |
|------|----------|------|
| LaTeX 样式 | `researchclaw/templates/styles/iclr_2025/*.sty` | wheel 列表 |
| BibTeX 样式 | `.../*.bst` | wheel 列表 |
| 内置技能 | `researchclaw/skills/builtin/**/SKILL.md` | wheel 列表 |
| 领域 profile | `researchclaw/domains/profiles/*.yaml` | wheel 列表 |
| 领域数据 | `researchclaw/data/**/*.yaml` | wheel 列表 |
| Python 包 | `researchclaw/**/*.py` | wheel 列表 |

**MUST NOT**：wheel 中出现重复路径（`zipfile.namelist()` 计数 >1）。

### 2.3 版本兼容验收

- Python 3.11 / 3.12 / 3.13 各跑一次 `python -m build` + `pip install` + `researchclaw --help`；
- Python 3.11 上 `pip install -e ".[all]"` 无依赖冲突；
- 不允许通过 `--no-build-isolation` 才能构建；标准隔离构建必须成功。

---

## 3. 共享运行状态契约（G3）

### 3.1 现状

- 写入：`pipeline/runner.py:83-88` 写 `last_completed_stage` / `last_completed_name` / `run_id` / `timestamp`；
- 读取：`dashboard/collector.py:91-95`、`server/routes/projects.py:31-32` 读旧字段 `stage/stage_name/status`；
- heartbeat：`runner.py:114-120` 写 ISO `timestamp`，`collector.py:105-106` 当 epoch 用。

### 3.2 Proposed：`researchclaw/run_state.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

class RunStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class RunState:
    run_id: str
    current_stage: int                  # last_completed_stage
    current_stage_name: str             # last_completed_name
    status: RunStatus
    topic: str
    start_time: str                     # ISO-8601
    last_update: str                     # ISO-8601
    is_active: bool
    schema_version: int = 1
    hitl: dict | None = None
    artifacts: tuple[str, ...] = ()

def read_run_state(
    run_dir: Path,
    *,
    stale_after_sec: int = 300,
    now: datetime | None = None,
) -> RunState: ...

def read_checkpoint_file(run_dir: Path) -> dict: ...
def read_heartbeat_file(run_dir: Path) -> dict | None: ...
```

### 3.3 字段语义（MUST）

| 字段 | 规则 |
|------|------|
| `current_stage` | `last_completed_stage`；缺失时为 0；不得从 `stage` 静默取 0 而忽略 `last_completed_stage` |
| `current_stage_name` | `last_completed_name`；缺失时用 `Stage(n).name`（若可解析） |
| `status` | 优先 `pipeline_summary.final_status`；否则 fresh heartbeat → `RUNNING`；checkpoint + HITL waiting/paused → `PAUSED`；其余 → `UNKNOWN` |
| `is_active` | heartbeat 存在且 `now - timestamp <= stale_after_sec`；时间戳必须能解析 ISO 或 epoch |
| `topic` | 优先 `config.yaml` 快照的 `research.topic` / `project.name`；缺失时读 `stage-01/goal.md` 首行；再缺失用 `run_id` |
| `start_time` | 优先 `config.yaml` 快照的 mtime；缺失用 checkpoint `timestamp` |
| `last_update` | heartbeat timestamp 或 checkpoint timestamp |
| `schema_version` | 新写入 checkpoint 为 1；读取缺失视为 0（legacy） |

### 3.4 兼容与迁移

- 读取器**只读**，不改变 `read_checkpoint()` 的语义；
- legacy checkpoint（`stage/stage_name/status`）→ 映射后返回，并 `logger.warning` 一次；
- `schema_version > 1` → best-effort + warning，不崩溃；
- 新写入 checkpoint 增加 `"schema_version": 1`，保持 `last_completed_stage` 字段名不变。

### 3.5 调用方契约

| 调用方 | 改动 |
|--------|------|
| `dashboard/collector.py` | 用 `read_run_state()` 生成 `RunSnapshot` |
| `server/routes/projects.py` | `current_stage/status` 来自 `RunState` |
| `server/routes/pipeline.py` | `list_runs` 返回 `RunState` 序列化 |
| `mcp/server.py` | `get_pipeline_status` 用 `RunState` |
| `report.py` | 如使用 checkpoint，统一改用 `RunState` |

### 3.6 示例响应（`/api/projects`）

```json
{
  "run_id": "rc-20261029-120000-abc123",
  "current_stage": 12,
  "current_stage_name": "EXPERIMENT_RUN",
  "status": "running",
  "is_active": true,
  "schema_version": 1
}
```

---

## 4. 成本追踪契约（G8a）

### 4.1 现状

- `runner.py:481` 读取 `config.experiment.cli_agent.max_budget_usd`；
- `runner.py:510-514` 调 `get_global_tracker().check_budget()`，ImportError 被吞；
- `cost_guard.py:111-116` 同样尝试 `get_global_tracker()`，失败后读 `run_dir/cost_log.jsonl`；
- `LLMResponse` 已有 `prompt_tokens/completion_tokens/total_tokens`（`llm/client.py:56-66`），但无 cost 字段。

### 4.2 Proposed：`researchclaw/cost_tracker.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

@dataclass(frozen=True)
class CostRecord:
    timestamp: str
    run_id: str
    stage: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    source: str          # "provider_usage" | "pricing_table" | "unknown"
    schema_version: int = 1

class CostTracker:
    def begin_run(self, *, run_dir: Path, run_id: str) -> None: ...
    def reset(self) -> None: ...          # 仅测试/显式新 run 使用
    def set_stage(self, stage: str) -> None: ...
    def record(self, record: CostRecord) -> None: ...
    def check_budget(self, budget_usd: float) -> bool: ...
    @property
    def total_cost_usd(self) -> float: ...
    @property
    def total_tokens(self) -> int: ...
    def snapshot(self) -> dict: ...

def get_global_tracker() -> CostTracker: ...
```

### 4.3 语义

| 项 | 规则 |
|----|------|
| 预算关闭 | `budget_usd <= 0` → `check_budget()` 返回 True |
| 预算判定 | `total_cost_usd < budget_usd` 为 True；恰好等于视为超限 |
| run 初始化 | `begin_run(run_dir, run_id)` 幂等：`run_id` 相同则保留累计值；不同则清空并指向新日志 |
| 递归 run | PIVOT/REFINE 递归调用 `execute_pipeline` 不得重置累计成本 |
| 成本来源 1 | `LLMResponse.raw["usage"]["cost"]` 为数字 → 直接使用，`source="provider_usage"` |
| 成本来源 2 | 配置 `llm.input_cost_per_1m` / `llm.output_cost_per_1m` → 计算，`source="pricing_table"` |
| 成本来源 3 | 都缺失 → `cost_usd=0.0`，`source="unknown"`，每个 model 只 warning 一次 |
| 并发 | `record()` 用 `threading.Lock`；JSONL 追加 + `flush()` |
| 阶段归属 | `execute_stage()` 调用 `tracker.set_stage(stage.name)`；LLMClient 读取当前 stage |
| 日志 | `run_dir/cost_log.jsonl`，一行一个 `CostRecord` |
| 读取 | `CostGuard` 优先用 tracker 的 `total_cost_usd`；tracker 不可用时回退读日志 |

### 4.4 与现有 `CostGuard` 的兼容

- 现有 `CostGuard._get_total_cost()` 已能读 `cost_log.jsonl`，字段 `cost_usd` 必须保留；
- `CostStatus` 的 50%/80%/100% 阈值不变；
- `total_cost_usd` 与日志求和必须一致（容差 1e-6）。

### 4.5 配置新增（Proposed）

```python
@dataclass(frozen=True)
class LlmConfig:
    # ... 现有字段
    input_cost_per_1m: float = 0.0
    output_cost_per_1m: float = 0.0
```

> 说明：不内置厂商价格表，避免价格漂移；用户/部署方可按模型配置单价。若 provider 返回 `usage.cost`，无需配置。

---

## 5. MCP 契约（G2）

### 5.1 协议与传输

| 项 | 契约 |
|----|------|
| 传输 | 默认 stdio；SSE/HTTP 未实现时必须显式报错，不得静默 |
| 初始化 | 使用官方 SDK v2 的连接流程；v2 不再要求旧版 handshake/session，测试以 SDK client 为准 |
| 工具列表 | `tools/list` 返回 `TOOL_DEFINITIONS` 的当前 schema |
| 工具调用 | `tools/call` 必须校验 `name` + `arguments` |
| 未知工具 | JSON-RPC `-32602`（invalid params），或 `isError` + `INVALID_TOOL` |
| 工具失败 | `isError: true` + `error_code` + `message`；不得返回 `success: true` 空结果 |
| 长任务 | 首期返回 `run_id`，客户端轮询 `get_pipeline_status`；Tasks 扩展延后 |
| 并发 | 默认最多 1 个活跃 run；第二个请求返回 `RUN_IN_PROGRESS` |
| 关闭 | 设置 `cancel_event`，等待线程退出；不得留下子进程 |

### 5.2 工具输入/输出 schema

| 工具 | 输入（required） | 成功输出 | 错误码 |
|------|------------------|----------|--------|
| `run_pipeline` | `topic: str` | `{run_id, status:"started", output_dir, started_at}` | `INVALID_ARGUMENT`, `RUN_IN_PROGRESS`, `BUDGET_EXCEEDED` |
| `get_pipeline_status` | `run_id: str` | `{run_id, stage, stage_name, status, is_active, updated_at, error?}` | `RUN_NOT_FOUND` |
| `get_experiment_results` | `run_id: str`, `stage?: str` | `{run_id, stage, metrics, conditions, source_path}` | `RUN_NOT_FOUND`, `NO_RESULTS` |
| `search_literature` | `query: str`, `max_results?: int` | `{query, count, results: Paper[]}` | `INVALID_ARGUMENT`, `UPSTREAM_ERROR` |
| `review_paper` | `paper_path?: str` 或 `run_id?: str`（二选一） | `{success: true, review_markdown, model, independent, tokens}` 或 `{isError:true,error_code:"CONFIG_REQUIRED"}` | `CONFIG_REQUIRED`, `INVALID_PATH`, `RUN_NOT_FOUND`, `INTERNAL_ERROR` |
| `get_paper` | `run_id: str`, `format?: "markdown"\|"latex"` | `{run_id, format, path, content}` | `RUN_NOT_FOUND`, `PAPER_NOT_FOUND` |

### 5.3 `run_pipeline` 异步契约

```python
async def run_pipeline(topic: str, config_path: str | None = None,
                       auto_approve: bool = True) -> dict:
    run_id = generate_run_id(topic)
    task = asyncio.create_task(
        asyncio.to_thread(execute_pipeline, run_dir=..., run_id=run_id,
                          config=..., adapters=..., auto_approve_gates=auto_approve)
    )
    _ACTIVE_TASKS[run_id] = task          # 强引用，防 GC
    task.add_done_callback(lambda _: _ACTIVE_TASKS.pop(run_id, None))
    return {"run_id": run_id, "status": "started", "output_dir": str(run_dir)}
```

**MUST**：

- 使用官方 SDK v2 的 `MCPServer` 与 `@mcp.tool()`；不自研协议循环；
- 使用强引用注册表（`dict[str, asyncio.Task]`）；
- `execute_pipeline` 在线程池执行，避免阻塞事件循环；
- `cancel_event` 与 server `stop` 共享；
- 不允许返回 `mcp-stub-*`；
- 首期不启用 Tasks 扩展，避免与 SDK 版本耦合。

### 5.4 路径与安全契约

- `run_id` 统一正则：`^rc-\d{8}-\d{6}-[a-f0-9]{6,64}$`；
- `run_dir` 必须 `resolve()` 后位于 `artifacts/` 根目录内；
- `paper_path` 只允许 artifacts 下 `.md`/`.tex`；
- 错误信息不得回显本机绝对路径（可回显相对 run 路径）；
- 输入字符串长度限制：`topic <= 2000`、`query <= 500`、`paper_path <= 1024`。

### 5.5 结果文件定位契约

| 工具 | 查找顺序 |
|------|----------|
| `get_experiment_results` | `stage-14/experiment_summary.json` → `stage-12/runs/results.json` → `results.json` |
| `get_paper` (markdown) | `stage-23/paper_final_verified.md` → `stage-22/paper_final.md` → `stage-17/paper_draft.md` |
| `get_paper` (latex) | `stage-22/paper.tex` → `deliverables/paper.tex` |
| `get_pipeline_status` | `RunState` |

---

## 6. 实验模式契约（G6 / G7）

### 6.1 模式到产物契约

| 模式 | Stage 10 产物 | Stage 12 执行 | Stage 13 |
|------|---------------|---------------|----------|
| `sandbox`/`docker` | `experiment/` + `experiment_spec.md` | subprocess/Docker | 真实 refine |
| `collider_agent` | `collider_plan.md` | `ColliderAgentSandbox.run(plan)` | skip（复制结果） |
| `biology_agent` | `biology_plan.md` | `BiologyAgentSandbox.run(plan)` | skip |
| `stat_agent` | `stat_plan.md` | `StatAgentSandbox.run(plan)` | skip |
| `agentic` | `agent_plan.md` | `AgenticSandbox.run_agent_session(plan)` | skip |
| `simulated` | `experiment/`（占位） | 生成模拟结果 | skip |
| `ssh_remote`/`colab_drive` | `experiment/` | 远端执行 | 真实 refine |

### 6.2 Proposed：计划生成统一入口

```python
def _execute_agent_plan_generation(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    mode: str,                         # collider_agent | biology_agent | stat_agent | agentic
    artifact_name: str,                # collider_plan.md | biology_plan.md | ...
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult: ...
```

要求：

- 读取 `exp_plan.yaml` + `hypotheses.*`；
- 生成 Markdown 计划，写入 `stage-10/<artifact_name>`；
- `StageResult.artifacts` 必须包含该文件；
- 失败时返回 `FAILED` + `decision="retry"`，不生成 Python 工程；
- `collider_plan.md` 保持现有格式，其他模式复用同一结构（Target/Model/Process/Analysis 或对应领域字段）。

### 6.3 Proposed：Stage 12 分派表

```python
AGENT_MODES = {
    "collider_agent": ("collider_plan.md", "collider"),
    "biology_agent": ("biology_plan.md", "biology"),
    "stat_agent": ("stat_plan.md", "stat"),
    "agentic": ("agent_plan.md", "agentic"),
}
```

分支语义：

```python
if mode in AGENT_MODES:
    plan_file, workspace_name = AGENT_MODES[mode]
    plan = _read_prior_artifact(run_dir, plan_file)
    if not plan:
        return StageResult(FAILED, error=f"Missing {plan_file}", decision="upstream_blocked")
    sandbox = create_sandbox(config.experiment, runs_dir / workspace_name)
    result = sandbox.run(plan, timeout_sec=...)
    # 写 runs/run-1.json + results.json
```

`agentic` 例外：使用 `create_agentic_sandbox()` + `run_agent_session()` + `to_sandbox_result()`，因为其公开 API 不是 `run()`。

### 6.4 Agent run JSON schema（Proposed v1）

```json
{
  "schema_version": 1,
  "mode": "biology_agent",
  "status": "completed",
  "returncode": 0,
  "elapsed_sec": 123.4,
  "metrics": {"fba_growth_rate": 0.81},
  "workspace": "runs/biology",
  "stdout_path": "runs/run-1.stdout.log",
  "stderr_path": "runs/run-1.stderr.log",
  "timestamp": "2026-10-29T12:00:00+00:00"
}
```

**MUST**：

- `status` ∈ `completed|partial|failed|timed_out`；
- `metrics` 只包含解析到的有限数值（过滤 NaN/Inf）；
- 不得写入伪造的 `metrics`；
- `results.json` 必须同时存在，格式与 `UniversalMetricParser` 兼容。

### 6.5 超时与清理

| 模式 | 默认超时 | 超时行为 |
|------|----------|----------|
| `collider_agent` | `ColliderAgentConfig.timeout_sec` | 收集部分结果，status=timed_out |
| `biology_agent` | `BiologyAgentConfig.timeout_sec`（3600） | 同上 |
| `stat_agent` | `StatAgentConfig.timeout_sec`（1800） | 同上 |
| `agentic` | `AgenticConfig.timeout_sec` | `AgenticResult.returncode=-1`，`timed_out=True` |

**MUST**：`finally` 清理容器/远端目录；验收检查无残留 `docker ps` 容器。

### 6.6 模式与模拟数据配置契约（D3 / D4）

```python
@dataclass(frozen=True)
class ExperimentConfig:
    mode: str = "sandbox"          # D3：默认 sandbox；simulated 必须显式

@dataclass(frozen=True)
class ResearchConfig:
    allow_simulated_paper: bool = False   # D4：默认阻断 simulated 论文
```

- `RCConfig.from_dict()`：原始配置缺少 `experiment.mode` → `sandbox` + warning；
- `pipeline_summary.data_origin` ∈ `real|simulated|mixed`；
- Stage 20：`simulated` 且未 allow → `E20_SIMULATED_DATA`；
- Stage 22：allow 时加水印 `SIMULATED DATA — NOT FOR SUBMISSION`。

---

## 7. 可选模块契约（G8b / G8c）

### 7.1 `experiment_spec`：建议删除重复逻辑

现状调用（`runner.py:552-579`）与 Stage 10 真实产物（`_code_generation.py:1476-1505`）冲突。**推荐直接删除 runner 段**，不新增模块。

如果评审决定保留一致性校验，Proposed 契约如下：

```python
@dataclass(frozen=True)
class MetricDef:
    name: str
    direction: Literal["higher", "lower", "neutral"] = "higher"
    unit: str = ""
    required: bool = True

@dataclass(frozen=True)
class ExperimentSpec:
    topic: str
    conditions: tuple[str, ...]
    metrics: tuple[MetricDef, ...]
    datasets: tuple[str, ...] = ()
    entry_point: str = "main.py"
    time_budget_sec: int = 0
    schema_version: int = 1

def parse_spec(markdown: str) -> ExperimentSpec: ...
def validate_results_against_spec(
    spec: ExperimentSpec, results: dict
) -> list[dict]: ...   # [{"code": "...", "message": "...", "metric": "..."}]
```

**MUST**：

- 不生成空的 `stage-09/experiment_spec.md`；
- 只读取 `stage-10/experiment_spec.md` + `stage-14/experiment_summary.json`；
- 违规写 `stage-14/spec_violations.json`，结构为对象列表，不是字符串列表。

### 7.2 `event_log`（裁定：删除，D6）

> 结论：本轮删除 `event_log` hook，不创建该模块。以下契约仅供未来重引入参考，不作为本轮实现/验收项。

现状调用：

```python
EventLog(log_dir=run_dir)
create_event(EventType.PIPELINE_START, run_id=..., stages=..., from_stage=...)
event_log.append(event)
```

Proposed 契约：

```python
from dataclasses import dataclass, field
from enum import Enum

class EventType(str, Enum):
    PIPELINE_START = "pipeline_start"
    STAGE_START = "stage_start"
    STAGE_END = "stage_end"
    STAGE_FAIL = "stage_fail"
    PIPELINE_END = "pipeline_end"
    HITL_PAUSE = "hitl_pause"
    HITL_RESUME = "hitl_resume"
    BUDGET_EXCEEDED = "budget_exceeded"

@dataclass(frozen=True)
class Event:
    type: EventType
    timestamp: str
    run_id: str
    stage: str = ""
    status: str = ""
    elapsed_sec: float = 0.0
    error: str | None = None
    payload: dict = field(default_factory=dict)
    schema_version: int = 1

class EventLog:
    def __init__(self, log_dir: Path) -> None: ...
    def append(self, event: Event) -> None: ...   # events.jsonl，线程安全
```

**MUST**：`append()` 不抛异常到主流程；写入失败只 warning。

### 7.3 `pitfall_detector`（裁定：删除，D6）

> 结论：本轮删除 `pitfall_detector` hook，不创建该模块。以下契约仅供未来重引入参考。

Proposed 契约：

```python
class PitfallType(str, Enum):
    SYNTHETIC_DATA = "synthetic_data"
    NO_REAL_DATA = "no_real_data"
    NO_BASELINE = "no_baseline"
    NO_SEEDS = "no_seeds"
    HARD_CODED_RESULTS = "hardcoded_results"
    TIME_GUARD = "time_guard"
    SILENT_EXCEPTION = "silent_exception"

@dataclass(frozen=True)
class Pitfall:
    type: PitfallType
    severity: Literal["info", "warning", "critical"]
    description: str
    line: int | None = None

class PitfallDetector:
    def detect_all(
        self, *, code: str, results: dict | None = None,
        experiment_config: dict | None = None,
    ) -> list[Pitfall]: ...
```

**MUST**：只做静态/启发式检查；`results`/`experiment_config` 为空时不得误报 critical。若无法达到该标准，建议删除 hook。

---

## 8. Web / 前端契约（G4）

### 8.1 目录解析

```python
def _resolve_frontend_dir() -> Path | None:
    """RESEARCHCLAW_FRONTEND_DIR > repo/frontend > repo/frontend-legacy > package/webui/dist"""
```

**MUST**：

- 每个候选目录必须包含 `index.html`；
- 找不到时 `logger.error` 一次，不抛异常；
- 不允许静默 `if is_dir(): mount(...)` 而不记录。

### 8.2 路由契约

| 路由 | 方法 | 响应 |
|------|------|------|
| `/` | GET | `index.html`（200） |
| `/static/{path}` | GET | 静态文件（200/404） |
| `/api/health` | GET | `{status:"ok", version:"0.5.0"}` |
| `/api/config` | GET | 配置摘要 |
| `/api/projects` | GET | `RunState[]` |
| `/ws/events` | WS | 事件流 |

**MUST**：API 路由优先于 SPA fallback；静态文件不得逃逸目录。

### 8.3 `create_app` lifecycle

现状使用 `@app.on_event("startup")`。建议改为 `lifespan`（FastAPI 0.115+ 推荐），但不是 P1 阻塞项：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await _start_background_tasks()
    yield
    await _stop_background_tasks()
```

---

## 9. OpenClaw 适配器契约（G12）

> 裁定：本轮不实现真实 OpenClaw 适配器（D7）；默认 Recording + 宿主注入。以下为扩展点契约，不是本轮验收项。

### 9.1 现有 Protocol（保持不变）

```python
class MessageAdapter(Protocol):
    def notify(self, channel: str, subject: str, body: str) -> str: ...

class WebFetchAdapter(Protocol):
    def fetch(self, url: str) -> FetchResponse: ...

class MemoryAdapter(Protocol):
    def append(self, namespace: str, content: str) -> str: ...

class SessionsAdapter(Protocol):
    def spawn(self, name: str, command: tuple[str, ...]) -> str: ...
```

### 9.2 `AdapterBundle.from_config` 语义

```python
@classmethod
def from_config(cls, config: RCConfig) -> AdapterBundle:
    """默认返回 Recording*；仅当配置显式启用且真实客户端可用时替换。"""
```

规则：

| 配置 | 行为 |
|------|------|
| 默认 | `Recording*`，只记录，不产生外部副作用 |
| `mcp.server_enabled=True` | **本轮仍 Recording + 一次性 warning**；不返回假 MCP adapter |
| `openclaw_bridge.use_message=True` 且提供 endpoint | 未来方案 B 才启用真实 MessageAdapter |
| 未提供 endpoint | Recording + 一次性 warning |
| `use_web_fetch` | 同上 |

**MUST（D7 裁定后）**：

- CLI/Server 使用默认 `AdapterBundle`；不强制调用 `from_config`；
- 若调用 `from_config`，无真实 endpoint 时必须返回 Recording + warning，禁止假成功；
- 真实适配器异常不得中断流水线，返回降级结果并 warning；
- 文档必须明确「默认录制桩；真实适配器需宿主注入」。

若采用方案 B（真实接线），建议新增：

```python
@dataclass(frozen=True)
class OpenClawBridgeConfig:
    base_url: str = ""                     # 空 = 未接线，使用 Recording
    request_timeout_sec: float = 10.0
    message_endpoint: str = "/message/notify"
    web_fetch_endpoint: str = "/web/fetch"
```

> `base_url` 为空时不得静默假装成功；应 warning 并回退 Recording。

---

## 10. 错误码、日志与并发

### 10.1 错误码（MCP / API 共用）

| code | HTTP/MCP | 含义 |
|------|----------|------|
| `INVALID_ARGUMENT` | -32602 / 400 | 参数缺失或越界 |
| `INVALID_PATH` | -32602 / 400 | 路径非法或越出 artifacts |
| `CONFIG_REQUIRED` | 412 / 400 | 缺少 LLM/服务配置，无法执行 |
| `INVALID_TOOL` | -32602 | 未知工具 |
| `RUN_NOT_FOUND` | 404 | run_id 不存在 |
| `PAPER_NOT_FOUND` | 404 | 论文文件缺失 |
| `NO_RESULTS` | 404 | 实验结果缺失 |
| `RUN_IN_PROGRESS` | 409 | 已有活跃 run |
| `BUDGET_EXCEEDED` | 402/409 | 预算超限 |
| `NOT_IMPLEMENTED` | 501 | 明确未实现 |
| `UPSTREAM_ERROR` | 502 | 外部 API 失败 |
| `INTERNAL_ERROR` | -32603 / 500 | 未分类异常 |

### 10.2 统一错误响应

```python
# FastAPI
raise HTTPException(
    status_code=404,
    detail={"code": "RUN_NOT_FOUND", "message": f"Unknown run: {run_id}"},
)

# MCP
{
    "isError": True,
    "structuredContent": {"code": "RUN_NOT_FOUND", "message": f"Unknown run: {run_id}"},
    "content": [{"type": "text", "text": "RUN_NOT_FOUND: Unknown run"}],
}
```

**MUST**：

- 不得返回 `success: true` 的空结果；
- 错误消息不得包含 API key、完整 prompt、绝对路径；
- FastAPI 路由使用 Pydantic response model 或显式 dict schema，避免字段漂移。

### 10.3 日志

- 新代码禁止裸 `except Exception: pass`；至少 `logger.debug(..., exc_info=True)`；
- 关键失败（MCP 启动、前端缺失、成本 pricing 缺失）用 `warning`/`error`；
- 日志字段包含 `run_id`、`stage`、`tool`（MCP）；
- 不记录 API key、完整 prompt、用户绝对路径。

### 10.4 并发 / 幂等

| 场景 | 规则 |
|------|------|
| 全局成本 tracker | `Lock` 保护；`record()` 幂等追加 |
| MCP run | 默认单活跃；重复 topic 生成新 run_id，不覆盖 |
| Server run | 保持现有单活跃；`stop` 设置 `cancel_event` |
| checkpoint 写入 | 保持 temp + `os.replace` 原子写 |
| event/cost 日志 | 追加写；并发用锁；崩溃最多丢最后一行 |
| Agent 容器 | 每次 run 唯一容器名；`finally` 清理 |

---

## 11. 测试用例设计

### 11.1 测试分层

| 层 | 范围 | 依赖 | 运行频率 |
|----|------|------|----------|
| Unit | 纯函数/数据类/解析 | 无外部 | 每次 |
| Contract | 接口/JSON schema/兼容 | 无外部 | 每次 |
| Integration | FastAPI/MCP/CLI/沙箱 mock | FastAPI/MCP SDK | 每次 |
| E2E | 真实 Docker/LLM/网络 | 可选 | 手动/nightly |

### 11.1.1 通用 fixture 契约

| fixture | 用途 | 关键点 |
|---------|------|--------|
| `run_dir_v1` | checkpoint v1 + fresh ISO heartbeat | 字段来自 `_write_checkpoint()` |
| `run_dir_legacy` | 旧 `stage/stage_name/status` + epoch heartbeat | 兼容测试 |
| `fake_llm` | 返回固定 `LLMResponse` | 可配置 tokens/cost |
| `fake_sandbox` | 记录 `run(prompt)` 参数 | 断言 biology/stat 收到 plan |
| `mcp_server` | 启动真实 stdio server | 清理 task/进程 |
| `api_client` | `TestClient(create_app(...))` | 不启动真实 uvicorn |
| `optional_dep` | `pytest.importorskip` | 无依赖时 skip 而非 fail |

**MUST**：fixture 必须使用真实写入函数生成文件（如 `_write_checkpoint`），不要手写可能与实现漂移的 JSON。

### 11.2 打包测试

| ID | 类型 | 设置 | 操作 | 期望 |
|----|------|------|------|------|
| PKG-01 | Integration | 干净 venv + `build` | `python -m build --wheel` | exit 0 |
| PKG-02 | Contract | 生成的 wheel | `zipfile.namelist()` 计数 | 无重复路径 |
| PKG-03 | Contract | wheel | 查找 `templates/styles`、`skills/builtin`、`domains/profiles` | 均存在 |
| PKG-04 | Integration | wheel | `pip install dist/*.whl` | 成功 |
| PKG-05 | Integration | 安装后 | `researchclaw --help` | exit 0 |
| PKG-06 | Contract | `pyproject.toml` | 解析 `packages` | 不含 `sibyl`/`arc` |

### 11.3 RunState / UI 测试

| ID | 类型 | 设置 | 操作 | 期望 |
|----|------|------|------|------|
| RS-01 | Unit | 真实 checkpoint v1 | `read_run_state` | stage=12,name=EXPERIMENT_RUN |
| RS-02 | Unit | legacy `stage/stage_name/status` | `read_run_state` | 映射正确 + warning |
| RS-03 | Unit | ISO heartbeat fresh | `read_run_state` | `is_active=True` |
| RS-04 | Unit | ISO heartbeat stale + HITL waiting | `read_run_state` | `is_active=False`, status=paused |
| RS-04b | Unit | ISO heartbeat stale + 无 HITL | `read_run_state` | `is_active=False`, status=unknown |
| RS-05 | Unit | epoch heartbeat | `read_run_state` | 正确解析 |
| RS-06 | Unit | 损坏 JSON / 缺失文件 | `read_run_state` | 不崩溃，status=unknown |
| RS-07 | Contract | `/api/projects` | GET | `current_stage` 非 0，字段齐全 |
| UI-01 | Integration | `create_app` | GET `/` | 200 + `<title>ResearchClaw` |
| UI-02 | Integration | 同上 | GET `/static/src/app.js` | 200 |
| UI-03 | Integration | `RESEARCHCLAW_FRONTEND_DIR` | GET `/` | 使用 env 目录 |
| UI-04 | Unit | 无 frontend 目录 | `create_app` | error 日志，不崩溃 |
| UI-05 | Security | `GET /static/../etc/passwd` | 请求 | 404/403，不泄漏 |

### 11.4 MCP 测试

| ID | 类型 | 设置 | 操作 | 期望 |
|----|------|------|------|------|
| MCP-01 | Integration | 官方 SDK client 连接 server | `list_tools` | 返回 6 个工具 |
| MCP-02 | Contract | `tools/list` | 调用 | schema 与 `TOOL_DEFINITIONS` 一致 |
| MCP-03 | Contract | 未知工具 | `tools/call` | -32602 / INVALID_TOOL |
| MCP-04 | Integration | mock `execute_pipeline` | `run_pipeline` | 返回真实 run_id，立即返回 |
| MCP-05 | Integration | mock pipeline 延迟 | `run_pipeline` + status | 状态从 running→completed |
| MCP-06 | Integration | stage-14 fixture | `get_experiment_results` | 返回 metrics |
| MCP-07 | Integration | stage-22 fixture | `get_paper` | 返回 markdown/tex |
| MCP-08 | Unit | mock literature | `search_literature` | 非空结果 / 明确错误 |
| MCP-09 | Unit | 有 LLM / 无 LLM | `review_paper` | 有评审内容，或 `CONFIG_REQUIRED`，非假成功 |
| MCP-10 | Integration | MCPClient | connect/list/call | 真实往返 |
| MCP-11 | Security | 非法 run_id | 请求 | 拒绝，不路径逃逸 |
| MCP-12 | Integration | 服务停止 | shutdown | 无残留 task/进程 |

### 11.5 实验模式测试

| ID | 类型 | 设置 | 操作 | 期望 |
|----|------|------|------|------|
| AG-01 | Unit | `ExperimentConfig(mode="agentic")` | `create_sandbox` | 不抛 Unsupported（或明确移除） |
| AG-02 | Unit | mock `AgenticSandbox` | Stage 12 | 写 run JSON + results |
| AG-03 | Unit | mock timeout | Stage 12 | status=timed_out，不伪造 metrics |
| AG-04 | Unit | mock biology | Stage 12 | `run()` 收到 plan 文本，不含 `def main` |
| AG-05 | Unit | biology results fixture | Stage 12/14 | 指标可解析 |
| AG-06 | Unit | mock stat | Stage 12 | 同 AG-04 |
| AG-07 | Contract | agent mode | Stage 13 | skip refine，复制 `experiment_final/` |
| AG-08 | Integration | 无 Docker | agentic | 可操作错误，不挂起 |

### 11.6 成本 / 可选模块测试

| ID | 类型 | 设置 | 操作 | 期望 |
|----|------|------|------|------|
| COST-01 | Unit | fake LLM usage | `chat` | `cost_log.jsonl` +1 行 |
| COST-02 | Unit | budget=0.01,total=0.02 | `check_budget` | False |
| COST-03 | Unit | `usage.cost=0.003` | `record` | source=provider_usage |
| COST-04 | Unit | 无 pricing | `record` | cost=0，warning 一次 |
| COST-05 | Unit | `CostGuard(run_dir)` | `check` | 与日志求和一致 |
| SPEC-01 | Contract | runner | Stage 9 后 | 不生成 `stage-09/experiment_spec.md` |
| SPEC-02 | Contract | Stage 10 | 运行 | `stage-10/experiment_spec.md` 存在 |
| SPEC-03 | Unit | spec + summary | `validate_results_against_spec` | 合法无违规；缺指标有违规 |
| EVENT-01 | N/A | D6 删除 | 不新增测试；回归检查无 `event_log` 引用 |
| PIT-01 | N/A | D6 删除 | 不新增测试；回归检查无 `pitfall_detector` 引用 |

### 11.7 模拟数据 / 配置测试

| ID | 类型 | 设置 | 操作 | 期望 |
|----|------|------|------|------|
| SIM-01a | Unit | 无 `experiment.mode` | `RCConfig.from_dict` | 默认 `sandbox` + warning |
| SIM-01b | Unit | 显式 `simulated` | 加载配置 | 保留 simulated，不 warning |
| SIM-01c | Unit | 非法 mode | 加载配置 | `ValidationError` |
| SIM-02 | Integration | `mode=simulated` | 运行 | summary.data_origin=simulated |
| SIM-03 | Integration | simulated + `allow_simulated_paper=False` | Stage 20 | 阻断 |
| SIM-04 | Integration | 同上 + True | Stage 20/22 | 放行 + warning + 水印 |
| SIM-05 | Contract | CLI | `--mode` 显示 | 打印 FAKE DATA 警告 |

### 11.8 文档 / 适配器测试

| ID | 类型 | 设置 | 操作 | 期望 |
|----|------|------|------|------|
| DOC-01 | Contract | README 代码块 | 提取 import | `execute_pipeline` 可导入 |
| DOC-02 | Contract | 全文档 | 搜索 `Runner(` | 不存在或已实现 |
| ADP-01 | Unit | `mcp.server_enabled=True` | `AdapterBundle.from_config` | Recording + warning；不返回假 MCP adapter |
| ADP-02 | Unit | 默认配置 | `from_config` | Recording 适配器 |
| ADP-03 | Unit | adapter 抛异常 | `execute_stage` | warning，不中断 |
| ADP-04 | Unit | CLI/Server 启动 | 默认 bundle | Recording；不强制 `from_config` |

### 11.9 回归测试

| ID | 命令 | 期望 |
|----|------|------|
| REG-01 | `pytest tests/ -q` | 全绿 |
| REG-02 | `pytest tests/test_rc_pipeline.py tests/test_rc_runner.py -q` | 核心流水线不回归 |
| REG-03 | `pytest tests/test_hitl*.py -q` | HITL 不回归 |
| REG-04 | `pytest tests/test_mcp.py -q` | 改造后 MCP 测试通过 |
| REG-05 | `python -m build --wheel` | 打包不回归 |
| REG-06 | `researchclaw --help` / `validate` | CLI 不回归 |

---

## 12. TDD 实施顺序

每个 PR 按 **Red → Green → Refactor → Regression**：

| PR | 先写失败测试 | 最小实现 | 重构/回归 |
|----|--------------|----------|-----------|
| PR-1 打包 | PKG-01~06 | 改 `pyproject.toml` | 全量 wheel/安装 |
| PR-2 RunState/UI | RS-01~07、UI-01~05 | `run_state.py` + 接入 | Dashboard/Projects/MCP status |
| PR-3 MCP/OpenClaw | MCP-01~12、ADP-01~04 | SDK v2 `MCPServer` + 工具 | 统一错误码/路径 |
| PR-4 Agent 模式 | AG-01~08、SIM-01~05 | 计划生成 + 分派 | Stage 13/14 兼容 |
| PR-5 成本/可选模块 | COST-01~05、SPEC-01~03 | `cost_tracker.py` + 删除 event/pitfall | 预算/CostGuard 回归 |
| PR-6 文档/测试 | DOC-01~02 | README/导出 | CI/全量回归 |

**MUST**：每个 PR 的测试先于实现提交；不允许先实现再补测试。

### 12.1 接口 ↔ 测试追踪矩阵

| 接口/契约 | 主要测试 |
|-----------|----------|
| `read_run_state` | RS-01~07、RS-04b |
| `CostTracker` / `check_budget` | COST-01~05 |
| MCP tools / 长任务 | MCP-01~12 |
| Agent 计划/分派 | AG-01~08 |
| `EventLog` | N/A（D6 删除） |
| `ExperimentSpec` | SPEC-01~03 |
| `PitfallDetector` | N/A（D6 删除） |
| `AdapterBundle.from_config` | ADP-01~04 |
| packaging/extras | PKG-01~06 |
| simulated guard | SIM-01~05 |
| public API / README | DOC-01~02 |

---

## 13. 接口 ↔ 调用点对照

| 新接口 | 现有调用点 | 必须匹配 |
|--------|------------|----------|
| `EventLog(log_dir=Path)` | `runner.py:464` | N/A（D6 删除；同步删除调用点） |
| `create_event(EventType, **fields)` | `runner.py:465,501,543` | N/A（D6 删除；同步删除调用点） |
| `generate_spec(topic, plan)` | `runner.py:555` | 若保留，必须允许空 plan 不崩溃 |
| `parse_spec(text)` | `runner.py:567` | 读取 Markdown |
| `validate_results_against_spec(spec, results)` | `runner.py:572` | 返回 list，可 JSON 序列化 |
| `PitfallDetector.detect_all(code, results, experiment_config)` | `runner.py:589` | N/A（D6 删除；同步删除调用点） |
| `get_global_tracker().check_budget(budget)` | `runner.py:511` | 返回 bool |
| `get_global_tracker().total_cost_usd` | `cost_guard.py:114` | 返回 float |
| `AdapterBundle.from_config(config)` | 建议 CLI/Server | 返回 `AdapterBundle` |
| `read_run_state(run_dir)` | 建议 Dashboard/Projects/MCP | 返回 `RunState` |

---

## 14. 兼容性与迁移

| 变更 | 兼容性 | 迁移动作 |
|------|--------|----------|
| 删除 `force-include` | 向后兼容 | 无需迁移；重新构建 |
| 增加 `server/mcp/voice` extras | 向后兼容 | 更新安装文档/CI |
| 新增 `RunState` | 向后兼容（只读） | 无需迁移；旧 checkpoint 自动映射 |
| checkpoint `schema_version=1` | 向后兼容 | 旧读取器忽略新字段；新读取器兼容旧字段 |
| 默认 mode 改 `sandbox` | **行为变更** | CHANGELOG + 配置校验；显式 `simulated` 仍可用 |
| biology/stat 改为 plan 产物 | **产物变更** | 旧 run 不可直接 resume 到 Stage 12；文档注明 |
| MCP 输出 schema 变化 | **实验性 API** | 提升 MCP server 版本/README 标注 |
| cost_log 新 schema | 向后兼容 | `CostGuard` 已按 `cost_usd` 读取 |
| OpenClaw 真实 adapter | 行为变更（opt-in） | 默认仍 Recording；启用后记录 warning |

---

## 15. 评审决策（已裁定）

> 完整裁定、证据锚点与迁移影响见 [14-decision-record.md](14-decision-record.md)。本节只保留结论。

| # | 决策 | 裁定 |
|---|------|------|
| D1 | MCP 实现路线 | 官方 `mcp` SDK v2 高层 `MCPServer`；`mcp>=2.1,<3`；不自研协议循环 |
| D2 | `review_paper` | 实现 MVP，复用 Stage 18 评审核心；无 LLM 配置返回 `CONFIG_REQUIRED` |
| D3 | 默认实验模式 | 默认 `sandbox` + warning；`simulated` 必须显式设置 |
| D4 | `simulated` 论文 | 默认阻断；`allow_simulated_paper=True` 才放行，并加水印 |
| D5 | 成本价格 | provider `usage.cost` 优先；否则配置单价；不内置价格表 |
| D6 | `event_log` / `pitfall_detector` | 删除两者；保留 `cost_tracker` |
| D7 | OpenClaw 真实适配器 | 本轮不实现；Recording + 宿主注入；文档改为扩展点 |
| D8 | Python 上界 | 不设上界；`>=3.11`；CI 3.11–3.13 阻断，3.14 非阻断 |

> 本文件以下接口如与 14 号裁定冲突，以 14 号为准；实施时同步修订。

---

## 16. 完成定义（工程侧）

一个 Gap 的修复只有在以下条件全部满足时才算完成：

- [ ] 接口契约已写入本文档或代码 docstring；
- [ ] 版本约束已写入 `pyproject.toml` / CI；
- [ ] 对应测试用例已实现并通过；
- [ ] 负向/回归测试通过；
- [ ] 12 号验收清单对应项 PASS；
- [ ] 文档（README/集成指南/Wiki）与实际行为一致；
- [ ] 无新增裸 `except Exception: pass`；
- [ ] 无新增未声明依赖；
- [ ] 变更可回滚（配置/代码开关或 git revert）。

---

## 17. 公开 API 导出契约（G10）

### 17.1 目标

让 README 的 Python 示例与真实入口一致，同时保持 `pipeline/__init__.py` 轻量、无副作用。

```python
# researchclaw/pipeline/__init__.py
from .runner import execute_pipeline, execute_iterative_pipeline
from .stages import Stage, StageStatus
from ._helpers import StageResult

__all__ = [
    "execute_pipeline",
    "execute_iterative_pipeline",
    "Stage",
    "StageStatus",
    "StageResult",
]
```

**MUST**：

- `import researchclaw.pipeline` 不得触发 LLM/网络/文件系统副作用；
- `execute_pipeline` 保持现有 keyword-only 签名（`run_dir/run_id/config/adapters/...`）；
- README 示例改为：

```python
from pathlib import Path
from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig
from researchclaw.pipeline import execute_pipeline

config = RCConfig.load(Path("config.arc.yaml"))
results = execute_pipeline(
    run_dir=Path("artifacts/my-run"),
    run_id="rc-20261029-120000-abc123",
    config=config,
    adapters=AdapterBundle(),
)
```

**MUST NOT**：

- 为示例新增 `Runner` 类，除非同时提供真实实现、测试和文档；
- 在 `__init__.py` 中导入 `experiment`/`server`/`mcp` 等重模块。

### 17.2 可选 `Runner` facade（不推荐首期）

若产品确需 `Runner(config).run()`，契约如下：

```python
class Runner:
    def __init__(self, config: RCConfig, *, output_root: Path = Path("artifacts"),
                 adapters: AdapterBundle | None = None) -> None: ...
    def run(self, topic: str | None = None, *, from_stage: Stage = Stage.TOPIC_INIT,
            to_stage: Stage | None = None, auto_approve: bool = False) -> list[StageResult]: ...
```

要求：

- 内部创建 run_id/run_dir、复制 config 快照、调用 `execute_pipeline`；
- 不隐藏 HITL/门控语义；
- 必须有独立测试与 README 示例；
- 否则不应出现在文档中。

