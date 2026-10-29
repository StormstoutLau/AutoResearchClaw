# 11 · 实际缺口修复调研（Remediation Research）

> 调研对象：`d:\AutoResearchClaw-main\AutoResearchClaw-main`（`researchclaw` v0.5.0）
> 调研日期：2026-10-29
> 状态：**仅调研与方案设计，本次未修改仓库源码**
> 证据等级：**E1 = 本机复现**；**E2 = 代码路径确认**；**E3 = 从代码推断/待验证**
> 接口契约、版本矩阵与测试用例见 [13-remediation-engineering-spec.md](13-remediation-engineering-spec.md)。
> §15 八项决策已裁定，见 [14-decision-record.md](14-decision-record.md)。

---

## 1. 执行摘要

本轮把 Wiki 中记录的「文档缺口」逐条回到代码验证，并额外发现了若干未被 Wiki 覆盖、但会直接影响可发布性的问题。共整理为 **12 类缺口**：

| ID | 缺口 | 证据 | 严重度 | 结论 |
|----|------|------|--------|------|
| G1 | **标准 wheel 构建失败**（`force-include` 与包目录重复） | E1 | **P0** | 删掉冗余 `force-include` 即可通过；`sibyl`/`arc` 不是构建阻塞项 |
| G2 | **MCP 服务端/客户端基本不可用**（`mcp --start` 立即返回、工具返回假成功、路径错误） | E1 | **P1** | 建议改用官方 MCP SDK + 长任务模式；或至少停止返回假成功 |
| G3 | **Dashboard / Projects 读取的 checkpoint 字段与实际写入不一致** | E1 | **P1** | 当前 stage 永远显示 0、心跳永远不活跃 |
| G4 | **前端目录路径不匹配**（代码找 `frontend/`，实际是 `frontend-legacy/`） | E1 | **P1** | 当前 Web 根路径与 `/static` 完全不挂载 |
| G5 | **服务端/语音依赖未声明**（`fastapi`/`uvicorn`/`voice` extra） | E2 | **P1** | 干净环境安装 `[server]` 不可用；CLI 还提示错误的 `[web]` |
| G6 | **`agentic` 实验模式未接线**（工厂直接抛错） | E1 | **P1** | 需显式 Stage 12 分支或从支持列表移除 |
| G7 | **`biology_agent`/`stat_agent` 缺少 Stage 12 专用分派** | E2 | **P1** | 当前会把「Python 代码」当 prompt 传给领域 sandbox |
| G8 | **4 个可选模块缺失/死代码**（cost/event/spec/pitfall） | E1/E2 | **P1–P2** | cost 应实现；spec 应删除重复逻辑；event/pitfall 可删或最小实现 |
| G9 | **`experiment.mode` 默认 `simulated`**，会生成假数据 | E2 | **P1** | 建议默认改 `sandbox` 或强制显式配置，并让 Stage 20 阻断 simulated 论文 |
| G10 | **README 的 Python API `Runner` 不存在** | E1 | **P2** | 改用 `execute_pipeline`（集成指南已是正确写法） |
| G11 | **测试锁定了错误契约**（旧 checkpoint 字段、MCP stub 成功） | E2 | **P1** | 测试通过反而掩盖真实故障；需改为真实 contract/fixture |
| G12 | **OpenClaw 桥接默认全是录制桩**，`from_config` 未被调用 | E2 | **P2** | 文档声称「自动消费能力」，实际没有真实适配器接线 |

### 最高优先级三件事

1. **G1 打包**：这是发布阻塞项，标准 `python -m build` 直接失败。
2. **G2 + G3 + G4 + G5**：Web/MCP/前端在干净环境下不可用或显示错误状态。
3. **G6 + G7 + G9**：实验模式的能力声明与实际执行不一致，直接影响论文数据真实性。

---

## 2. 调研方法

1. **代码路径复核**：对每个缺口定位写入方/读取方、调用链与异常处理。
2. **本机复现**：对可执行的问题直接运行最小用例（详见 §7 复现日志）。
3. **构建复现**：在临时 venv 中安装 `hatchling`/`build`，分别构建原始仓库与「只改 `pyproject.toml`」的临时副本，隔离根因。
4. **社区检索**：检索 Hatch、FastAPI/Starlette、MCP Python SDK、OpenHands/Claude Code、LiteLLM/OpenRouter、pytest 官方文档与真实 GitHub issue/PR，提取可复用模式。
5. **不修改源码**：所有验证都在临时目录或内存中完成；仓库文件未动。

---

## 3. 逐项调研与修复方案

### G1 · 标准 wheel 构建失败（P0，E1）

#### 现象与复现

原始 `pyproject.toml`：

```toml
[tool.hatch.build.targets.wheel]
packages = ["researchclaw", "sibyl", "arc"]

[tool.hatch.build.targets.wheel.force-include]
"researchclaw/templates/styles" = "researchclaw/templates/styles"
```

在临时 venv 中执行：

```bash
python -m build --wheel --no-isolation --outdir <temp> .
```

构建失败：

```text
ValueError: A second file is being added to the wheel archive at the same path:
`researchclaw/templates/styles/iclr_2025/iclr2025_conference.bst`.
The most likely cause of this is an entry in the
`tool.hatch.build.targets.wheel.force-include` table.
```

#### 根因

Hatchling 默认会递归包含 `researchclaw/` 包目录下的非 Python 文件；`force-include` 又把同一个 `templates/styles` 目录映射到包内同一路径，导致同一路径被加入两次。**这与 `sibyl`/`arc` 是否存在无关**。

为隔离变量，做了两组临时副本构建：

| 副本配置 | 结果 |
|----------|------|
| 保留 `packages = ["researchclaw","sibyl","arc"]`，**只删除** `force-include` | ✅ 构建成功，wheel 内含 `templates/styles/*` |
| 删除 `sibyl`/`arc` **并** 删除 `force-include` | ✅ 构建成功 |

结论：

- `force-include` 是唯一阻塞项；
- `sibyl`/`arc` 是不存在的目录，属于**配置卫生问题**，不会导致构建失败，但会误导维护者；
- `pip install -e .` 在临时 venv 中可以成功（需 `editables`），所以 README 的开发路径可用，但**发布/普通 `pip install .` 会失败**。

#### 社区案例

| 来源 | 可借鉴结论 |
|------|------------|
| [Hatch issue #2301](https://github.com/pypa/hatch/issues/2301) | Hatch 1.30.1 后开始强制阻止 wheel 内重复路径，正是本错误 |
| [Hatch PR #2269](https://github.com/pypa/hatch/pull/2269) | 官方实现对重复文件直接报错，而不是静默覆盖 |
| [jigandmpnn PR #1](https://github.com/nboyd/jigandmpnn/pull/1) | 同类修复：`drop redundant force-include that collides with packages` |
| [obsidian-sync issue #5](https://github.com/alex-furrier/obsidian-sync/issues/5) | 同类修复：`Fix duplicate templates in Hatch wheel build` |
| [Hatch Build 文档](https://hatch.pypa.io/latest/config/build/) | `packages`/`force-include` 的语义与适用场景 |

#### 推荐修复

```toml
[tool.hatch.build.targets.wheel]
packages = ["researchclaw"]
```

删除 `force-include` 块。`templates/styles` 已在包内，会被默认包含。若未来确实需要包含包外资源，使用 `artifacts` 或 `include`，不要 `force-include` 一个已在包内的目录。

#### 验收

```bash
python -m build --wheel
python -m zipfile -l dist/*.whl | grep 'templates/styles'
pip install dist/*.whl
researchclaw --help
```

#### 风险与回滚

- 风险：极低；只影响打包声明。
- 回滚：恢复原 `pyproject.toml` 即可。
- 建议同时加 CI 构建任务，避免再次回归（见 G11）。

---

### G2 · MCP 服务端/客户端/适配器基本不可用（P1，E1）

#### 缺口拆解

| 子问题 | 证据 |
|--------|------|
| `researchclaw mcp --start` 立即返回，不进入服务循环 | `cli.py:647-652` 调用 `asyncio.run(server.start())`；`mcp/server.py:136-144` 的 `start()` 只设置 `_running=True` |
| `run_pipeline` 返回假 run_id | `mcp/server.py:71-79` 返回 `mcp-stub-{topic[:20]}`，不启动流水线 |
| `search_literature` / `review_paper` 是 stub | `mcp/server.py:104-119` 返回空结果/固定字符串 |
| `get_experiment_results` 读错文件 | 读 `run_dir/experiment_results.json`（`mcp/server.py:98`），但仓库从未写该文件；实际是 `stage-12/runs/results.json`、`stage-14/experiment_summary.json` |
| `get_paper` 读错路径 | 读 run 根目录的 `paper_draft.md`/`paper.tex`（`mcp/server.py:123-132`），实际在 `stage-17/paper_draft.md`、`stage-22/paper_final.md` |
| SSE transport 是 stub | `mcp/transport.py:73-99` 的 `receive()` 直接 `NotImplementedError` |
| MCP 客户端是 stub | `mcp/client.py:82-95` 的 `_send_request()` 返回 `{"result": {}}` |
| MCP/OpenClaw 适配器是录制桩 | `adapters.py:101-118` 的 `MCPMessageAdapter`/`MCPWebFetchAdapter` 返回固定字符串 |
| `AdapterBundle.from_config()` 未被调用 | 全仓库无调用；CLI/Server 都用 `AdapterBundle()`（`cli.py:302`、`server/routes/pipeline.py:111`） |

本机复现：

```text
run_pipeline: {'success': True, 'message': 'Pipeline started for topic: demo', 'run_id': 'mcp-stub-demo'}
search_literature: {'success': True, 'query': 'demo', 'results': [], 'message': 'Literature search stub'}
server.start elapsed: 0.0 s, running= True
```

#### 社区案例

| 来源 | 可借鉴结论 |
|------|------------|
| [MCP Python SDK — Handling errors](https://py.sdk.modelcontextprotocol.io/servers/handling-errors/) | 工具失败应抛 `ToolError`（模型可见）或 `MCPError`（协议可见），不要返回「成功但空」的结果 |
| [MCP Python SDK issue #3659](https://github.com/modelcontextprotocol/python-sdk/issues/3659) | 未知工具应以 JSON-RPC `-32602` 返回；当前实现返回普通 `success:false` 并不完全符合协议 |
| [MCP Python SDK PR #3697](https://github.com/modelcontextprotocol/python-sdk/pull/3697) | 官方正在修正 unknown tool 的 invalid params 语义 |
| [MCP Tasks 扩展](https://modelcontextprotocol.io/extensions/tasks/overview) + [Tasks 规范](https://tasks.extensions.modelcontextprotocol.io/specification/2026-07-28/tasks) | 长任务应返回 `taskId`/`pollIntervalMs`，客户端轮询 `tasks/get`，而不是假装同步完成 |
| [FastMCP Quickstart](https://gofastmcp.com/getting-started/quickstart) | 用官方/事实标准 SDK 注册工具，避免手写 JSON-RPC 循环 |
| [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) | 启动流水线应立即返回 `run_id`，后台执行，状态通过查询获得 |
| [asyncio 后台任务陷阱](https://mer.vin/2026/08/why-your-asyncio-background-tasks-vanish-without-a-trace/) | 保存 task 强引用、注册 done callback，避免任务被 GC 或在进程退出时消失 |

#### 推荐方案（两选一）

**方案 A（推荐）：采用官方 MCP SDK + 长任务**

- 新增 `mcp` extra，使用 `mcp` Python SDK（或 FastMCP）注册工具；
- `run_pipeline`：
  1. 校验 topic/config；
  2. 生成 `run_id`；
  3. 用 `asyncio.create_task` + 线程池执行 `execute_pipeline`，保存强引用；
  4. 立即返回 `{run_id, status: "started", output_dir}`；
  5. 如客户端支持 Tasks 扩展，返回 `taskId` 与 `pollIntervalMs`；
- `get_pipeline_status`：复用 G3 的 `RunState` reader；
- `get_experiment_results`：读取 `stage-14/experiment_summary.json`，回退 `stage-12/runs/results.json`；
- `get_paper`：按 `stage-23/paper_final_verified.md` → `stage-22/paper_final.md` → `stage-22/paper.tex` 查找；
- `search_literature`：调用 `literature.search.search_papers()`；
- `review_paper`：要么实现（独立 reviewer LLM + 评审 prompt），要么从 `TOOL_DEFINITIONS` 移除并返回明确的 `not_implemented`，**不要假成功**；
- 删除 stubs `MCPClient` 与 Stub transports，或改用 SDK 客户端。

**方案 B（最小，已由 14 号 D1 否决，仅作备选记录）**：保留自定义 JSON-RPC，但补齐循环与错误语义

- 用现有 `StdioTransport` 实现 `initialize` / `tools/list` / `tools/call` / `notifications/initialized` 循环；
- 未知工具返回 JSON-RPC `-32602`；
- 工具内部失败返回 `isError: true` + 明确错误文本；
- 长任务返回 `run_id`，客户端轮询 `get_pipeline_status`；
- SSE transport 明确标记为未实现并从默认配置中移除。

#### 测试

- 单元：`tools/list` 返回 6 个 schema；未知工具返回 `-32602`；`run_pipeline` 返回真实 `run_id` 且不阻塞。
- 集成：启动服务 → `run_pipeline` → 轮询 `get_pipeline_status` → 完成后 `get_paper` 能读到 `stage-22` 文件。
- 回归：`search_literature` 不再返回空数组；`review_paper` 要么有评审内容，要么明确 `not_implemented`。

#### 风险

- 中高：涉及协议兼容与长任务生命周期。建议单独 PR，先只做 stdio + 本地单用户，不引入 SSE/多租户。

---

### G3 · Dashboard / Projects 的 checkpoint schema 不一致（P1，E1）

#### 现象

写入方（`pipeline/runner.py:83-88`）写的是：

```json
{
  "last_completed_stage": 12,
  "last_completed_name": "EXPERIMENT_RUN",
  "run_id": "...",
  "timestamp": "2026-10-29T00:00:00+00:00"
}
```

读取方却读旧字段：

- `dashboard/collector.py:91-95`：`ckpt.get("stage")`、`stage_name`、`status`、`topic`、`start_time`；
- `server/routes/projects.py:31-32`：`ckpt_data.get("stage")`、`status`；
- `dashboard/collector.py:105-106`：`time.time() - hb.get("timestamp")`，而 heartbeat 的 `timestamp` 是 ISO 字符串（`runner.py:118-120`）。

本机复现（真实 checkpoint + ISO heartbeat）：

```text
{'current_stage': 0, 'current_stage_name': '', 'status': 'running', 'is_active': False}
```

#### 社区案例

| 来源 | 可借鉴结论 |
|------|------------|
| [FastAPI response_model](https://fastapi.tiangolo.com/tutorial/response-model/) | 用显式 schema 约束 API 输出，避免「写入方/读取方各说各话」 |
| 本仓库 `tests/test_rc_checkpoint.py:30`、`tests/test_rc_runner.py:151` | 真实测试已经断言 `last_completed_stage`，说明正确 schema 是已知的 |

#### 推荐修复

新增单一读取器（例如 `researchclaw/run_state.py`）：

```python
@dataclass(frozen=True)
class RunState:
    run_id: str
    current_stage: int
    current_stage_name: str
    status: str
    topic: str
    start_time: str
    is_active: bool

def read_run_state(run_dir: Path) -> RunState:
    # 1. 读 checkpoint：优先 last_completed_stage/last_completed_name
    # 2. 兼容旧键 stage/stage_name（迁移期）
    # 3. status 从 pipeline_summary.json 的 final_status 推导，
    #    运行中则看 heartbeat
    # 4. heartbeat timestamp 用 datetime.fromisoformat 解析，
    #    兼容 epoch 数字
```

替换：

- `DashboardCollector._collect_run()`
- `server/routes/projects.py`
- `mcp/server.py::_handle_get_status`
- `report.py`（如涉及）

并在 `checkpoint.json` 增加 `schema_version: 1`，读取器对未知版本回退并 warning。

#### 测试

- 用 `_write_checkpoint()` 生成真实文件 → 断言 stage/name/status/is_active；
- 旧字段 fixture → 断言兼容；
- ISO 与 epoch 两种 heartbeat → 断言 `is_active` 正确；
- 删除 `tests/test_web_platform.py:293` 的旧 schema fixture（或改为兼容测试）。

#### 风险

低；但会影响 Dashboard/Projects/MCP 三处，建议集中在一个 PR。

---

### G4 · 前端目录路径不匹配（P1，E1）

#### 现象

`server/app.py:121`：

```python
frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if frontend_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")
```

本机验证：

```text
resolved: D:\AutoResearchClaw-main\AutoResearchClaw-main\frontend exists= False
actual:   D:\AutoResearchClaw-main\AutoResearchClaw-main\frontend-legacy exists= True
```

用最小 config 调用 `create_app()`，路由表只有 API/WS，没有 `/` 和 `/static`：

```text
['/openapi.json', '/docs', '/docs/oauth2-redirect', '/redoc',
 '/api/health', '/api/config', '/api/pipeline/start', '/api/pipeline/stop',
 '/api/pipeline/status', '/api/pipeline/stages', '/api/runs',
 '/api/runs/{run_id}', '/api/runs/{run_id}/metrics', '/api/projects',
 '/ws/chat', '/ws/events']
```

#### 社区案例

| 来源 | 可借鉴结论 |
|------|------------|
| [FastAPI StaticFiles 参考](https://fastapi.tiangolo.com/reference/staticfiles/) | `StaticFiles` 目录不存在会抛 `RuntimeError`，应「响亮失败」而不是静默 404 |
| [FastAPI 前端指南](https://fastapi.tiangolo.com/tutorial/frontend/) | 可用 `check_dir=False` 支持「先建 app、后构建前端」 |
| [Starlette staticfiles.py](https://github.com/Kludex/starlette/blob/master/starlette/staticfiles.py) | `check_config()` 负责目录校验 |
| [search_with_lepton issue #71](https://github.com/leptonai/search_with_lepton/issues/71) | 真实案例：`RuntimeError: Directory 'ui' does not exist` |
| [imoji PR #34](https://github.com/KhaledSaleman/imoji/pull/34) | 真实修复：`Fix RuntimeError webapp/static directory does not exist on Render` |

#### 推荐修复

```python
def _resolve_frontend_dir() -> Path | None:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = []
    env = os.environ.get("RESEARCHCLAW_FRONTEND_DIR", "").strip()
    if env:
        candidates.append(Path(env).expanduser())
    candidates += [repo_root / "frontend", repo_root / "frontend-legacy",
                   Path(__file__).resolve().parent.parent / "webui" / "dist"]
    for c in candidates:
        if (c / "index.html").is_file():
            return c
    logger.error("No frontend found; tried: %s", candidates)
    return None
```

- 挂载 `/static` 到解析出的目录；
- 根路径 `/` 返回 `index.html`；
- 若目录缺失，**记录 error 日志一次**，不要静默跳过；
- 保留 `RESEARCHCLAW_FRONTEND_DIR` 便于部署/打包。

#### 测试

- `TestClient` GET `/` 返回 200 且包含 `<title>ResearchClaw`；
- GET `/static/src/app.js` 返回 200；
- 删除/重命名目录时日志出现 error，不崩溃。

#### 风险

低。注意 `frontend-legacy/index.html` 内部引用 `/static/src/...`，挂载到 `/static` 正好匹配。

---

### G5 · 服务端/语音依赖未声明（P1，E2）

#### 现象

`pyproject.toml:15-29` 只有 `anthropic`/`web`/`pdf`/`all`/`dev`，没有：

- `fastapi`、`uvicorn`：`cli.py:713-721` 的 `serve`/`dashboard` 需要；
- `voice`：`server/routes/voice.py:23-27` 明确提示 `pip install researchclaw[voice]`，但该 extra 不存在；
- 若采用 MCP SDK，还需要 `mcp` extra。

`web` extra 的语义是「网页抓取」，不应同时承担「Web 服务」；当前 `serve` 的错误提示却让用户装 `[web]`。

#### 社区案例

| 来源 | 可借鉴结论 |
|------|------------|
| [FastAPI pyproject](https://github.com/fastapi/fastapi/blob/master/pyproject.toml) | FastAPI 自己把 `uvicorn[standard]` 放在 `standard` extra，而不是核心依赖 |
| [PyPA 可选依赖指南](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) | 每个 feature 一个 extra，是最常见的打包模式 |

#### 推荐修复

```toml
[project.optional-dependencies]
server = ["fastapi>=0.115", "uvicorn[standard]>=0.30"]
mcp = ["mcp>=2.1,<3"]
voice = ["httpx>=0.24"]
web = ["scholarly>=1.7", "crawl4ai>=0.2", "tavily-python>=0.3"]
all = [
  "fastapi>=0.115", "uvicorn[standard]>=0.30",
  "mcp>=2.1,<3", "httpx>=0.24",
  "scholarly>=1.7", "crawl4ai>=0.2", "tavily-python>=0.3",
  "PyMuPDF>=1.23", "huggingface-hub>=0.20", "matplotlib>=3.7", "scipy>=1.10",
]
```

同步修改 `cmd_serve`/`cmd_dashboard` 的错误提示为 `pip install "researchclaw[server]"`。

#### 测试

```bash
python -m venv .venv-clean
pip install -e ".[server]"
python -c "from researchclaw.server.app import create_app; print('ok')"
researchclaw serve --help
```

#### 风险

低；只是依赖声明。注意不要把 `fastapi`/`uvicorn` 变成核心依赖，保持 CLI 轻量。

---

### G6 · `agentic` 模式未接线（P1，E1）

#### 现象

- `config.py:98-108` 把 `agentic` 列入 `EXPERIMENT_MODES`；
- `factory.py:18-108` 的 `create_sandbox()` 不处理 `agentic`，会抛：

```text
RuntimeError Unsupported experiment mode for create_sandbox(): agentic
```

本机已复现。

- `create_agentic_sandbox()`（`factory.py:111`）存在但全仓库无调用；
- `AgenticSandbox` 的公开方法是 `run_agent_session(prompt, workspace)`（`agentic_sandbox.py:68`），不是 `SandboxProtocol` 的 `run()/run_project()`；
- 它提供了 `to_sandbox_result()`（`agentic_sandbox.py:165`），说明作者已预留兼容转换。

#### 社区案例

| 来源 | 可借鉴结论 |
|------|------------|
| [OpenHands Runtime Architecture](https://docs.openhands.dev/openhands/usage/architecture/runtime) | Agent 在容器中运行，通过 action/observation 循环驱动 |
| [OpenHands Docker Sandbox](https://docs.openhands.dev/openhands/usage/sandboxes/docker) | 容器即 agent-server，工作区挂载，网络/资源隔离 |
| [Claude Code devcontainer](https://code.claude.com/docs/en/devcontainer) | 官方 devcontainer 示例：CLI + 出口防火墙 + 持久卷 |
| [Docker coding agent sandbox](https://docs.docker.com/get-started/tutorials/run-an-agent/) | 用专用 sandbox 运行 Claude/Codex 等编码 Agent |
| [SWE-agent Docker 环境](https://swe-agent.com/latest/usage/cl_tutorial/) | 推荐自定义镜像 + `post_startup_commands`，与 `AgenticSandbox` 的 `agent_install_cmd` 思路一致 |

#### 推荐修复（方案 A：显式 Stage 12 分支）

1. **Stage 10**：为 `agentic` 生成执行计划（`agent_plan.md`），而不是普通 Python 代码。可把 `_execute_collider_plan_generation()` 泛化为 `_execute_agent_plan_generation(mode, artifact)`，让 collider/agentic/biology/stat 共用。
2. **Stage 12**：在 `mode == "agentic"` 分支：

```python
from researchclaw.experiment.factory import create_agentic_sandbox

workspace = runs_dir / "agentic_workspace"
sandbox = create_agentic_sandbox(
    config.experiment, workspace,
    skills_dir=Path(config.skills.builtin_dir) if config.skills.builtin_dir else None,
)
prompt = _read_prior_artifact(run_dir, "agent_plan.md") or code_text
agentic = sandbox.run_agent_session(prompt, workspace,
                                    timeout_sec=config.experiment.agentic.timeout_sec)
result = sandbox.to_sandbox_result(agentic)
# 写 runs/run-1.json、results.json
```

3. **Stage 13**：把 `agentic` 加入「跳过 Python refine」的 agent 模式集合。
4. 可选：让 `AgenticSandbox` 实现一个 `run(prompt)` 适配器，但不要把它塞进 `SandboxProtocol` 的 `run(code)` 语义里。

#### 方案 B（保守）

如果短期不打算做 Stage 10/12 的接线：从 `EXPERIMENT_MODES` 移除 `agentic`，并在 `create_sandbox()` 报错信息中明确「agentic 尚未实现」；文档删除相关宣传，避免用户踩坑。

#### 测试

- `create_sandbox(mode="agentic")` 不再抛「Unsupported」；
- mock `run_agent_session` 返回 `AgenticResult` → 断言写出 `runs/run-1.json`、`results.json`；
- 无 Docker 时给出可操作错误；
- Stage 13 对 agentic 跳过 refine。

#### 风险

中；涉及 Docker/Agent 生命周期和 prompt 设计。建议单独 PR + 可选 e2e。

---

### G7 · `biology_agent` / `stat_agent` 缺少 Stage 12 专用分派（P1，E2）

#### 现象

- `factory.py:91-101` 能返回 `BiologyAgentSandbox`/`StatAgentSandbox`；
- 两者 `run()` 的第一个参数都是 `prompt_text`（`biology_agent_sandbox.py:80-97`、`stat_agent_sandbox.py:63-71`）；
- 但 Stage 12 只对 `collider_agent` 有显式分支（`_execution.py:163`）；`biology_agent`/`stat_agent` 落入 `else`（`_execution.py:477-497`）：

```python
runner = ExperimentRunner(config.experiment, runs_dir / "workspace")
history = runner.run_loop(code_text, ...)
```

`ExperimentRunner.run_experiment()` 会把 `code_text` 传给 `sandbox.run(code)`（`experiment/runner.py:128-131`），于是**生成的 Python 代码被当作领域 Agent 的 prompt**。

- Stage 13 已经正确跳过这两种模式（`_execution.py:607-655`），说明作者知道它们是 agent 模式，但 Stage 12 没跟上。

#### 社区案例

| 来源 | 可借鉴结论 |
|------|------------|
| [OpenHands Runtime Architecture](https://docs.openhands.dev/openhands/usage/architecture/runtime) | Agent 需要「计划/动作 → 观察 → 结果」的显式循环，不能靠普通代码执行器 |
| [Claude Code devcontainer](https://code.claude.com/docs/en/devcontainer) | 把 Agent CLI 放进受控容器，工作区作为输入/输出边界 |
| 本仓库 `collider_agent` 分支 | 已有「生成计划 → sandbox.run(plan) → 复制 results.json」的成熟模式，可直接复用 |

#### 推荐修复

1. **Stage 10**：为 `biology_agent`/`stat_agent` 增加计划生成分支（与 collider 类似），产出 `biology_plan.md`/`stat_plan.md`；不要生成普通 Python 工程。
2. **Stage 12**：显式分支：

```python
if mode in ("biology_agent", "stat_agent"):
    sandbox = create_sandbox(config.experiment, workspace)
    plan = _read_prior_artifact(run_dir, f"{mode}_plan.md") or exp_plan
    result = sandbox.run(plan, timeout_sec=config.experiment.<mode>.timeout_sec)
    # 读取 workspace/results.json → runs/results.json
```

3. **Stage 13**：保持现有 skip，并把 `runs/` 复制到 `experiment_final/`。
4. 为 `biology_agent`/`stat_agent` 的 `results.json` 增加 schema 校验（复用 `UniversalMetricParser`）。

#### 测试

- Mock sandbox `run(prompt)` → 断言收到的是 plan 文本而不是 Python 代码；
- `results.json` 被复制到 `runs/`，Stage 14 可读取；
- Stage 13 产出 `experiment_final/`。

#### 风险

中；需要与 `external/agents` 的实际输出约定对齐。

---

### G8 · 4 个可选模块：成本、事件、实验规格、陷阱检测（P1–P2）

#### 现状矩阵

| 模块 | 调用方 | 当前行为 | 建议 |
|------|--------|----------|------|
| `researchclaw.cost_tracker` | `runner.py:510-514`、`hitl/cost_guard.py:111-116` | ImportError 被吞；预算检查永远跳过；`cost_log.jsonl` 无人写 | **实现**（README 已宣传 Cost Guardrails） |
| `researchclaw.pipeline.event_log` | `runner.py:463-468,499-549,856-866` | ImportError 被吞；无持久事件日志 | 删除 hook，或最小实现 JSONL |
| `researchclaw.pipeline.experiment_spec` | `runner.py:552-579` | ImportError 被吞；且 Stage 10 已写 `stage-10/experiment_spec.md`，runner 又尝试写 `stage-09`（空 plan）并读 root `results.json` | **删除 runner 这段重复逻辑**；如需校验，移到 Stage 14 读 Stage 10 spec |
| `researchclaw.pipeline.pitfall_detector` | `runner.py:582-599` | ImportError 被吞；`detect_all` 只传 code，results/config 为空 | 删除，或实现最小 AST 检查 |

#### G8a · 成本追踪（建议实现）

证据链：

- README 第 345 行明确宣传「Cost Guardrails … 50%/80%/100%」；
- `CostGuard` 已有 `cost_log.jsonl` 回退读取（`cost_guard.py:118-130`），测试也覆盖了该格式（`tests/test_hitl_advanced.py:136-168`）；
- 但 `LLMClient` 只记录 token，不写成本；`get_global_tracker()` 不存在。

社区案例：

| 来源 | 可借鉴结论 |
|------|------------|
| [LiteLLM Token Usage & Cost](https://docs.litellm.ai/docs/completion/token_usage) | 用 `prompt_tokens`/`completion_tokens` + 模型单价计算 `completion_cost` |
| [OpenRouter Usage Accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting) | 部分 provider 的 `usage.cost` 直接返回真实费用，可直接采集 |

推荐设计：

```python
class CostTracker:
    def reset(self, run_dir: Path | None) -> None: ...
    def record(self, *, model, prompt_tokens, completion_tokens,
               cost_usd: float | None = None) -> None: ...
    @property
    def total_cost_usd(self) -> float: ...
    def check_budget(self, budget_usd: float) -> bool: ...
```

- `execute_pipeline` 启动时 `get_global_tracker().reset(run_dir)`；
- `LLMClient.chat()` 成功后调用 `record()`：
  - 优先用 `resp.raw["usage"]["cost"]`（OpenRouter 等）；
  - 否则用可配置单价表（`llm.input_cost_per_1m` / `output_cost_per_1m`）；
  - 都缺失时记录 token、cost=0，并 warning 一次；
- `record()` 追加 `run_dir/cost_log.jsonl`，格式 `{"cost_usd": ..., "model": ..., "tokens": ...}`，与现有 `CostGuard` 兼容；
- `runner` 的预算检查改用 `tracker.check_budget()`。

测试：

- 假 LLM 返回 usage → `cost_log.jsonl` 行数/金额正确；
- 预算 10、累计 12 → `check_budget` False，pipeline 停止；
- `CostGuard.check(tmp_path)` 读取同一文件，阈值 50%/80% 正确。

#### G8b · `experiment_spec`：删除重复，不要补模块

证据：

- Stage 10 已经生成 `stage-10/experiment_spec.md`（`_code_generation.py:1476-1505`），且契约声明该输出（`contracts.py:101-109`）；
- runner 的 `generate_spec(config.research.topic, "")` 传入空 plan，写入 `stage-09/experiment_spec.md`；但 Stage 9 契约只要求 `exp_plan.yaml`；
- 验证阶段读的也是 `stage-09/experiment_spec.md` 与 root `results.json`，两者都不可靠。

结论：**不要为了满足死代码而新建模块**。推荐删除 `runner.py:551-579` 整段；若确实需要「计划 vs 结果」一致性检查，放到 Stage 14：

```python
spec = parse_spec((run_dir/"stage-10"/"experiment_spec.md").read_text())
summary = json.loads((run_dir/"stage-14"/"experiment_summary.json").read_text())
violations = validate_results_against_spec(spec, summary)
```

并把 `spec_violations.json` 写到 `stage-14`。

#### G8c · `event_log` / `pitfall_detector`：删除或最小实现

- `event_log` 没有在 README/文档中宣传；Dashboard 已有 WebSocket 事件。若不需要审计，删除 hook；若需要，最小实现 `events.jsonl`（JSON Lines，字段：type/run_id/stage/timestamp/status/elapsed/error）。
- `pitfall_detector` 的调用方式只传 code，`results`/`experiment_config` 都是空 dict，即使实现也只能做静态检查。建议删除；若保留，明确只做 AST/字符串规则（如 `synthetic data`、`time guard`、固定 seed、无 baseline），并在 Stage 10/12 后写 `pitfall_report.json`。

#### 风险

- 成本追踪涉及 LLM 调用路径，需确保失败不影响主流程（record 内部 try/except）。
- 删除死代码是低风险，但需同步删除相关测试/文档引用。

---

### G9 · `experiment.mode` 默认 `simulated`（P1，E2）

#### 现象

- `ExperimentConfig.mode` 默认 `"simulated"`（`config.py:585`）；
- 示例配置写的是 `"sandbox"`；
- Stage 12 的 `simulated` 分支生成固定假数据（`_execution.py:451-476`），状态为 `simulated`；
- 防伪造硬门只对 `sandbox/docker` 检查真实指标（`_execution.py:502-566`），simulated 结果可以继续流向写作。

#### 风险

如果用户忘记设置 `experiment.mode`，系统会「成功」产出一篇基于假数据的论文；这是比崩溃更危险的行为。

#### 社区模式

| 来源 | 可借鉴结论 |
|------|------------|
| [PyPA 配置指南](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) | 配置应显式、可验证，不要依赖隐式默认 |
| 本仓库测试 `tests/test_rc_config.py` | 可用配置校验锁定默认行为 |

#### 推荐修复

1. **默认改为 `sandbox`**（与示例/README 一致），同时在 `validate_config()` 中对未知/空 mode 报错；
2. 若保留 `simulated`，增加 `research.allow_simulated_paper: bool = False`；
3. Stage 20 增加硬门：`pipeline_summary.data_origin == "simulated"` 且未允许 → `BLOCKED_APPROVAL` / `FAILED`；
4. `pipeline_summary.json` 写入 `data_origin: real|simulated`；
5. CLI `run` 启动时打印 `Mode: simulated (FAKE DATA)` 警告。

#### 测试

- 不写 `experiment.mode` 时默认 `sandbox`；
- `mode=simulated` + `allow_simulated_paper=False` → Stage 20 阻断；
- `allow_simulated_paper=True` → 放行并记录 warning。

#### 风险

中：改变默认行为可能让现有「调试用 simulated」用户需要显式配置；需在 CHANGELOG 标注 breaking-ish change。

---

### G10 · README 的 `Runner` API 不存在（P2，E1）

#### 现象

README 第 274 行：

```python
from researchclaw.pipeline import Runner
Runner(config).run()
```

本机复现：

```text
ImportError cannot import name 'Runner' from 'researchclaw.pipeline'
```

而 `docs/integration-guide.md:764-779` 已经给出正确写法：

```python
from researchclaw.pipeline.runner import execute_pipeline
results = execute_pipeline(run_dir=..., run_id=..., config=..., adapters=AdapterBundle(), ...)
```

#### 推荐修复

- **优先改 README**，不要为了一个示例新增 facade；`execute_pipeline` 是实际公开入口。
- 可在 `researchclaw/pipeline/__init__.py` 导出 `execute_pipeline`、`execute_iterative_pipeline`、`Stage`、`StageStatus`，方便 `from researchclaw.pipeline import execute_pipeline`。
- 如果确实想要 `Runner`，再实现薄封装：

```python
class Runner:
    def __init__(self, config): self.config = config
    def run(self): ...  # 创建 run_dir/adapters，调用 execute_pipeline
```

但这是额外 API 面积，非必要。

#### 测试

- README 代码块 lint（可用 `pytest --doctest-glob` 或简单脚本提取并 import）。
- 文档链接检查。

---

### G11 · 测试锁定了错误契约（P1，E2）

#### 现象

- `tests/test_web_platform.py:293` 使用旧 checkpoint：`{"stage": 5, "stage_name": ..., "status": "running"}`；`test_collect_run_active_heartbeat` 使用 `time.time()` 作为 heartbeat，而真实 runner 写 ISO 字符串。于是测试通过，真实 Dashboard 却 stage=0、is_active=False。
- `tests/test_mcp.py:78-97` 明确断言 stub 成功、搜索返回空；`test_mcp.py:164-172` 断言 `MCPClient.list_tools()` 返回 `[]`。这些测试把「未实现」锁成了「正确」。
- 没有 wheel 构建测试，所以 P0 打包失败长期未被发现。

#### 社区案例

| 来源 | 可借鉴结论 |
|------|------------|
| [pytest importorskip](https://docs.pytest.org/en/stable/how-to/skipping.html) | 可选依赖测试应显式 skip，而不是把 stub 当实现 |
| [GitHub Actions Python 构建](https://docs.github.com/en/actions/automating-builds-and-tests/building-and-testing-python) | CI 中执行 `python -m build` + 安装产物 |
| [physica PR #9](https://github.com/thebrazenbeard/physica/pull/9) | 真实案例：CI 增加可选依赖与 wheel smoke test |
| 本仓库 `tests/test_rc_checkpoint.py`、`tests/test_rc_runner.py` | 真实 checkpoint schema 已有正确断言，可作为 golden fixture 来源 |

#### 推荐修复

新增/改造：

1. `tests/test_packaging.py` 或 CI 脚本：`python -m build`；检查 wheel 内含 `templates/styles`；安装后 `researchclaw --help`。
2. `tests/test_run_state.py`：用 `_write_checkpoint()` + 真实 heartbeat 生成 fixture；兼容旧字段。
3. `tests/test_mcp_protocol.py`：启动真实 stdio server；`tools/list`、未知工具 `-32602`、`run_pipeline` 返回真实 run_id、`get_paper` 命中 stage-22。
4. `tests/test_frontend_mount.py`：`create_app` 后 GET `/` 与 `/static/src/app.js`。
5. `tests/test_agent_dispatch.py`：mock 领域 sandbox，断言 `biology/stat/agentic` 收到 plan 文本而非 Python 代码。
6. 删除/改写 `tests/test_web_platform.py` 的旧 checkpoint fixture 和 `tests/test_mcp.py` 的 stub 成功断言。

#### 风险

低；测试改造应与对应修复同一个 PR，避免先红后绿。

---

### G12 · OpenClaw 桥接默认是录制桩（P2，E2）

#### 现象

- `AdapterBundle` 默认使用 `RecordingCronAdapter`/`RecordingMessageAdapter`/...（`adapters.py:121-127`）；
- `AdapterBundle.from_config()` 只把 message/web_fetch 换成 MCP stub（`adapters.py:130-139`），而且**全仓库无调用**；
- CLI/Server 都直接 `AdapterBundle()`（`cli.py:302`、`server/routes/pipeline.py:111`）；
- 因此 `openclaw_bridge.use_message/use_memory/use_web_fetch/...` 只是「是否调用录制桩」的开关，并没有连接真实 OpenClaw 能力；
- `MCPMessageAdapter.notify()` 返回 `mcp-notify-{channel}`，`MCPWebFetchAdapter.fetch()` 返回固定文本（`adapters.py:100-118`）。

#### 社区/文档对照

- `docs/integration-guide.md:579` 声称「When OpenClaw provides a capability, the adapter consumes it automatically」；代码没有自动接线。
- 社区模式：依赖注入由宿主显式传入（如 FastAPI `Depends`），或通过入口工厂创建真实 adapter；默认 stub 只用于测试。

#### 推荐修复

二选一：

**A. 明确为扩展点**：在文档中改为「默认录制桩；宿主必须注入真实 adapter」，并提供 `AdapterBundle.with_*()`/`from_runtime()` 接口；删除「自动消费」表述。
**B. 实现真实适配器**：为 OpenClaw 能力定义 HTTP/CLI 端点（config 增加 `openclaw_bridge.endpoint`），实现 `MessageAdapter`/`WebFetchAdapter`/`MemoryAdapter`，并在 CLI/Server 调用 `AdapterBundle.from_config(config)`。

短期推荐 A（文档诚实），中期再 B。

#### 测试

- `AdapterBundle.from_config(config)` 在 `mcp.server_enabled=True` 时返回 MCP adapter；
- `openclaw_bridge.use_message=True` 时，`execute_stage` 确实调用注入的 adapter（用 spy）；
- 默认 bundle 的调用只记录、不产生副作用。

---

## 4. 优先级与实施顺序

| 阶段 | PR | 内容 | 依赖 |
|------|----|------|------|
| **P0** | PR-1 | G1 打包修复 + G5 server/mcp/voice extras + CI wheel smoke | 无 |
| **P1** | PR-2 | G3 共享 `RunState` reader + G4 前端路径 + Dashboard/Projects/MCP status 接入 | PR-1（依赖安装） |
| **P1** | PR-3 | G2 MCP 协议/工具真实实现 + G12 OpenClaw 适配器诚实化 | PR-2（RunState） |
| **P1** | PR-4 | G6 `agentic` + G7 `biology/stat` Stage 10/12 分派 + G9 默认模式/模拟阻断 | PR-1（依赖） |
| **P1** | PR-5 | G8a 成本追踪；G8b 删除 experiment_spec 重复；G8c event/pitfall 删除或最小实现 | PR-1 |
| **P2** | PR-6 | G10 README/公开 API、G11 测试契约改造、文档同步 | PR-2/3/4 |

**不建议**把所有修复塞进一个 PR：G2/G6 涉及协议/子进程生命周期，G1/G5 只改元数据，混合会放大 review 成本。

---

## 5. 验收 Checklist

> 逐缺口的可执行命令、负向/回归检查、发布门与签署表见 [12-remediation-acceptance-checklist.md](12-remediation-acceptance-checklist.md)。

- [ ] `python -m build --wheel` 成功，wheel 内含 `researchclaw/templates/styles/*`
- [ ] 干净 venv `pip install ".[server]"` 后 `researchclaw serve` 可启动
- [ ] `GET /` 返回前端 `index.html`，`GET /static/src/app.js` 返回 200
- [ ] 用真实 run 目录，Dashboard/Projects 显示 `last_completed_stage` 与 `is_active`
- [ ] `researchclaw mcp --start` 保持运行；`tools/list` 返回 6 个工具；`run_pipeline` 返回真实 run_id
- [ ] `get_paper` 能从 `stage-22/paper_final.md` 取到论文
- [ ] `agentic` 模式不再抛 Unsupported；`biology/stat` 收到 plan 文本
- [ ] 未显式配置 `experiment.mode` 时默认 `sandbox`；simulated 结果不能通过 Stage 20
- [ ] 成本超预算时 pipeline 停止，`cost_log.jsonl` 有记录
- [ ] `from researchclaw.pipeline import execute_pipeline` 可用；README 示例可运行
- [ ] 测试不再断言 MCP stub 成功/旧 checkpoint 字段

---

## 6. 社区案例与参考链接

### 打包 / 依赖

- [Hatch Build 配置](https://hatch.pypa.io/latest/config/build/)
- [Hatch Wheel Builder](https://hatch.pypa.io/dev/plugins/builder/wheel/)
- [Hatch issue #2301 — duplicate wheel path](https://github.com/pypa/hatch/issues/2301)
- [Hatch PR #2269 — block duplicate files](https://github.com/pypa/hatch/pull/2269)
- [jigandmpnn PR #1 — drop redundant force-include](https://github.com/nboyd/jigandmpnn/pull/1)
- [obsidian-sync issue #5 — duplicate templates in Hatch wheel](https://github.com/alex-furrier/obsidian-sync/issues/5)
- [PyPA — Writing pyproject.toml / optional dependencies](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [FastAPI pyproject（standard extra 含 uvicorn）](https://github.com/fastapi/fastapi/blob/master/pyproject.toml)

### FastAPI / 静态前端

- [FastAPI StaticFiles reference](https://fastapi.tiangolo.com/reference/staticfiles/)
- [FastAPI Frontend guide](https://fastapi.tiangolo.com/tutorial/frontend/)
- [Starlette staticfiles.py](https://github.com/Kludex/starlette/blob/master/starlette/staticfiles.py)
- [search_with_lepton issue #71 — Directory 'ui' does not exist](https://github.com/leptonai/search_with_lepton/issues/71)
- [imoji PR #34 — static dir RuntimeError fix](https://github.com/KhaledSaleman/imoji/pull/34)
- [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [asyncio background task pitfalls](https://mer.vin/2026/08/why-your-asyncio-background-tasks-vanish-without-a-trace/)

### MCP

- [MCP Python SDK — Handling errors](https://py.sdk.modelcontextprotocol.io/servers/handling-errors/)
- [MCP Python SDK issue #3659 — unknown tool should be -32602](https://github.com/modelcontextprotocol/python-sdk/issues/3659)
- [MCP Python SDK PR #3697 — invalid params for unknown tools](https://github.com/modelcontextprotocol/python-sdk/pull/3697)
- [MCP Tasks extension overview](https://modelcontextprotocol.io/extensions/tasks/overview)
- [MCP Tasks specification](https://tasks.extensions.modelcontextprotocol.io/specification/2026-07-28/tasks)
- [FastMCP Quickstart](https://gofastmcp.com/getting-started/quickstart)

### Agent / Sandbox

- [OpenHands Runtime Architecture](https://docs.openhands.dev/openhands/usage/architecture/runtime)
- [OpenHands Docker Sandbox](https://docs.openhands.dev/openhands/usage/sandboxes/docker)
- [Claude Code devcontainer](https://code.claude.com/docs/en/devcontainer)
- [Docker — run your coding agent in a sandbox](https://docs.docker.com/get-started/tutorials/run-an-agent/)
- [SWE-agent Docker environment](https://swe-agent.com/latest/usage/cl_tutorial/)

### 成本 / 测试 / 可选依赖

- [LiteLLM Token Usage & Cost](https://docs.litellm.ai/docs/completion/token_usage)
- [OpenRouter Usage Accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
- [pytest — skip on missing import](https://docs.pytest.org/en/stable/how-to/skipping.html)
- [GitHub Actions — building and testing Python](https://docs.github.com/en/actions/automating-builds-and-tests/building-and-testing-python)
- [physica PR #9 — wheel smoke test in CI](https://github.com/thebrazenbeard/physica/pull/9)
- [Python importlib — find_spec](https://docs.python.org/3/library/importlib.html)

---

## 7. 本机复现日志（摘要）

### 7.1 wheel 构建失败（原始）

```text
$ python -m build --wheel --no-isolation --outdir <temp> .
...
ValueError: A second file is being added to the wheel archive at the same path:
`researchclaw/templates/styles/iclr_2025/iclr2025_conference.bst`.
```

### 7.2 删除 `force-include` 后构建成功

```text
$ python -m build --wheel --no-isolation --outdir <temp> <temp-copy>
Successfully built researchclaw-0.5.0-py3-none-any.whl

$ python -m zipfile -l <wheel> | grep styles
researchclaw/templates/styles/iclr_2025/iclr2025_conference.bst
researchclaw/templates/styles/iclr_2025/iclr2025_conference.sty
...
```

### 7.3 `pip install -e .`（开发安装）可通过

在临时 venv 中安装 `hatchling` + `editables` 后：

```text
$ pip install --no-deps --no-build-isolation -e .
Successfully installed researchclaw-0.5.0
```

说明：README 的 `pip install -e .` 路径可用，但标准 wheel 分发失败。

### 7.4 UI 读取真实 checkpoint

```text
{'current_stage': 0, 'current_stage_name': '', 'status': 'running', 'is_active': False}
```

输入是真实 schema：`last_completed_stage=12`、`last_completed_name=EXPERIMENT_RUN`、ISO heartbeat。

### 7.5 `create_app` 未挂载前端

```text
['/openapi.json', '/docs', '/docs/oauth2-redirect', '/redoc',
 '/api/health', '/api/config', '/api/pipeline/start', '/api/pipeline/stop',
 '/api/pipeline/status', '/api/pipeline/stages', '/api/runs',
 '/api/runs/{run_id}', '/api/runs/{run_id}/metrics', '/api/projects',
 '/ws/chat', '/ws/events']
```

无 `/`、无 `/static`。

### 7.6 MCP stub

```text
run_pipeline: {'success': True, 'message': 'Pipeline started for topic: demo', 'run_id': 'mcp-stub-demo'}
search_literature: {'success': True, 'query': 'demo', 'results': [], 'message': 'Literature search stub'}
server.start elapsed: 0.0 s, running= True
```

### 7.7 agentic 工厂

```text
RuntimeError Unsupported experiment mode for create_sandbox(): agentic
```

### 7.8 README 的 Runner API

```text
ImportError cannot import name 'Runner' from 'researchclaw.pipeline'
```

---

## 8. 结论与建议

- **先修 G1 + G5 + CI**：这是「能不能发版/能不能在干净环境跑起来」的问题，改动小、收益最大。
- **再修 G3 + G4**：Web 界面是用户第一印象；当前即使 API 能跑，前端也不显示正确状态。
- **G2/G6/G7 单独排期**：涉及协议/Agent 生命周期，属于「功能真实性」问题，不应冒充已完成。
- **G8 按需裁剪**：成本追踪值得实现；`experiment_spec` 应删除重复逻辑而非补模块；event/pitfall 可删。
- **G9 需要产品决策**：默认 `simulated` 是危险默认；建议改为显式配置 + Stage 20 阻断。
- **G11 是长期保障**：把 wheel 构建、MCP 协议、checkpoint schema 纳入 CI，否则同类问题会再次出现。

> 下一步如进入实施，建议按 §4 的 PR 顺序推进，每个 PR 附带对应测试与验收项；本次调研不包含代码改动。
