# 12 · 修复验收 Checklist（Remediation Acceptance）

> 配套文档：[11-gap-remediation-research.md](11-gap-remediation-research.md)、[13-remediation-engineering-spec.md](13-remediation-engineering-spec.md)
> 用途：把 11 号文档中的每个修复方案转成**可执行、可复核、可签署**的验收项。
> 原则：**主验收 + 负向验收 + 回归验收** 三者都通过，才算 PASS。
> 平台说明：示例以 bash 为主；Windows PowerShell 下可用 `Get-ChildItem dist/*.whl | ForEach-Object { pip install $_.FullName }`，HTTP 检查可用 `curl.exe` 或 `Invoke-WebRequest`。

---

## 0. 使用方式

1. 每个 PR 只覆盖其声明的 Gap，不跨 PR 混验。
2. 所有命令在仓库根目录执行；`<venv>` 表示本次验收专用虚拟环境。
3. 每项验收保留证据：命令输出、wheel 文件列表、JSON 响应、截图、pytest 报告。
4. 任一 `P0/P1` 项失败，不允许合并或发布；`P2` 项可申请 waiver，但必须记录原因。
5. 验收完成后在 §5 签署表中填写状态。

---

## 1. 全局准入条件

在开始逐项验收前，先确认：

- [ ] 当前分支只包含目标 Gap 的改动，`git diff` 无无关文件
- [ ] `python --version` ≥ 3.11
- [ ] 使用**干净虚拟环境**做安装/启动验收，不复用开发环境
- [ ] 验收使用临时 `artifacts/` 或 `--output <temp>`，不污染真实 run
- [ ] 涉及 LLM 的验收使用 mock 或 `--skip-preflight`，避免真实费用
- [ ] 涉及 Docker/Agent 的验收允许 mock；真实 e2e 标为可选
- [ ] 已阅读对应 Gap 的 11 号文档章节

### 干净环境模板

```bash
python -m venv .venv-accept
# Linux/macOS
source .venv-accept/bin/activate
# Windows PowerShell
# .venv-accept\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -e ".[dev]" build hatchling
```

---

## 2. 发布门（Release Gates）

### Gate 0 · 打包与安装

| 检查 | 命令 | 通过标准 |
|------|------|----------|
| 标准 wheel 构建 | `python -m build --wheel --outdir dist` | exit 0；`dist/*.whl` 生成 |
| wheel 无重复路径 | 见下方脚本 | 输出 `duplicates=[]` |
| 模板资源存在 | 见下方脚本 | 包含 `researchclaw/templates/styles/.../*.sty` |
| 干净安装 | `pip install dist/*.whl` | 安装成功 |
| 包可导入 | `python -c "import researchclaw; print(researchclaw.__version__)"` | 输出 `0.5.0` |
| CLI 可用 | `researchclaw --help` | 列出子命令，exit 0 |
| 开发安装不回归 | `pip install -e .` | 成功 |

```bash
python -c "import glob,zipfile,collections; w=glob.glob('dist/*.whl')[0]; n=zipfile.ZipFile(w).namelist(); d=[k for k,v in collections.Counter(n).items() if v>1]; print('files',len(n),'duplicates',d); assert not d"
python -c "import glob,zipfile; w=glob.glob('dist/*.whl')[0]; n=zipfile.ZipFile(w).namelist(); s=[x for x in n if 'templates/styles/' in x]; print('styles',len(s)); assert s"
```

- [ ] Gate 0 全部通过
- 证据：构建日志、wheel 列表输出、`pip show researchclaw`
- 失败判定：仍出现 `A second file is being added to the wheel archive`

### Gate 1 · Web / UI

| 检查 | 命令 | 通过标准 |
|------|------|----------|
| 服务依赖安装 | `pip install -e ".[server]"` | `fastapi`/`uvicorn` 可导入 |
| 服务启动 | `researchclaw serve --config <cfg> --port 18080` | 进程保持运行 |
| 健康检查 | `curl http://127.0.0.1:18080/api/health` | `status: ok` |
| 首页 | `curl -I http://127.0.0.1:18080/` | HTTP 200，返回 HTML |
| 静态资源 | `curl -I http://127.0.0.1:18080/static/src/app.js` | HTTP 200 |
| 项目状态 | `curl http://127.0.0.1:18080/api/projects` | `current_stage` 为真实阶段，不是 0/None |
| Dashboard 快照 | 单元测试或 `/ws/events` | `current_stage_name` 非空、`is_active` 正确 |
| 浏览器烟测 | 打开首页 → Dashboard/Pipeline/Chat | 无 404、无控制台 error |

- [ ] Gate 1 全部通过
- 证据：curl 输出、截图、`/api/projects` JSON
- 失败判定：首页 404、静态资源 404、stage 永远为 0

### Gate 2 · MCP / OpenClaw

| 检查 | 命令/方法 | 通过标准 |
|------|-----------|----------|
| 安装 | `pip install -e ".[mcp]"` | `mcp>=2.1,<3` 可导入 |
| 服务进程 | 启动 `researchclaw mcp --start` 或 SDK server | 进程保持运行，不立即退出 |
| 初始化 | 官方 SDK client 连接（v2 不再要求旧 handshake） | 返回 server info/capabilities |
| 工具列表 | `tools/list` | 返回声明的 tool schema（当前 6 个） |
| 未知工具 | `tools/call` + 不存在名称 | JSON-RPC `-32602` 或明确 `isError` |
| 启动流水线 | `run_pipeline {topic}` | 返回真实 `rc-...` run_id，非 `mcp-stub-*` |
| 状态查询 | `get_pipeline_status {run_id}` | 返回真实 stage/status |
| 结果查询 | `get_experiment_results {run_id}` | 返回 stage-14/12 数据 |
| 论文查询 | `get_paper {run_id, format}` | 返回 stage-22/23 论文 |
| 文献检索 | `search_literature {query}` | 非空结果或明确错误，不返回空成功 |
| 评审 | `review_paper {paper_path 或 run_id}` | 有评审内容；无 LLM 配置时 `CONFIG_REQUIRED` |
| 客户端 | `MCPClient.connect/list_tools/call_tool` | 真实往返，不返回空 `{}` |
| OpenClaw adapter | `use_message/use_web_fetch` | 调用真实适配器或明确扩展点 |

- [ ] Gate 2 全部通过
- 证据：JSON-RPC transcript、run 目录、工具输出
- 失败判定：`mcp --start` 立即退出、`mcp-stub-*`、未知工具返回普通 success

### Gate 3 · 实验模式与数据真实性

| 检查 | 方法 | 通过标准 |
|------|------|----------|
| 默认模式 | 不配置 `experiment.mode` 加载配置 | 默认 `sandbox` 或明确校验错误（按最终设计） |
| 模拟标记 | `mode=simulated` 运行 | `pipeline_summary.data_origin=simulated` |
| 模拟阻断 | Stage 20 | 未授权 simulated 论文被阻断 |
| agentic | `create_sandbox(mode=agentic)` | 不再抛 Unsupported，或该模式已从列表移除 |
| agentic 执行 | mock `run_agent_session` | 写 `runs/run-1.json`、`results.json` |
| biology/stat | mock 领域 sandbox | 收到 plan 文本，不是 Python 代码 |
| 结果落盘 | Stage 12/13 | `runs/results.json`、`experiment_final/` 存在 |
| 数据来源 | 论文数字 | 来自 `VerifiedRegistry`，非 simulated 占位 |

- [ ] Gate 3 全部通过
- 证据：run 目录、mock 调用参数、`pipeline_summary.json`
- 失败判定：默认 simulated 无警告、agentic 抛错、Python 代码被当 prompt

### Gate 4 · 成本与可选模块

| 检查 | 方法 | 通过标准 |
|------|------|----------|
| 成本记录 | 假 LLM 返回 usage | `cost_log.jsonl` 有记录 |
| 累计成本 | `get_global_tracker().total_cost_usd` | 等于日志求和 |
| 预算停止 | budget 小于累计 | pipeline 在下一阶段前停止 |
| CostGuard | `CostGuard.check(run_dir)` | 读取同一日志，阈值正确 |
| spec 重复 | 检查 stage-09/10 | 不再生成空 `stage-09/experiment_spec.md` |
| spec 校验（若保留） | Stage 14 | 违规写入 `stage-14/spec_violations.json` |
| event log（若保留） | `events.jsonl` | 字段完整、可解析 |
| pitfall（若保留） | `pitfall_report.json` | 规则触发/未触发均正确 |
| 死代码清理 | 搜索 `cost_tracker`、`event_log`、`experiment_spec`、`pitfall_detector` 的引用 | 无未解释引用 |

- [ ] Gate 4 全部通过
- 证据：`cost_log.jsonl`、预算停止日志、JSON 报告
- 失败判定：成本日志为空、预算检查仍被跳过、空 spec 仍生成

### Gate 5 · 文档、测试与 CI

| 检查 | 命令 | 通过标准 |
|------|------|----------|
| 单测 | `pytest tests/ -q` | 全绿（允许明确 skip） |
| 新增测试 | 见 §4 | 覆盖 G1/G2/G3/G4/G6/G7 |
| 旧错误契约测试 | 搜索旧字段/stub | 已更新或删除 |
| README 示例 | 提取代码块执行 | `execute_pipeline` 可导入 |
| 文档同步 | 09/10/11/12 | 与实际行为一致 |
| CI wheel | `python -m build` | 成功 |
| CI 安装 | `pip install ".[server,mcp,voice]"` | 成功 |

- [ ] Gate 5 全部通过
- 证据：pytest 报告、CI run、README diff
- 失败判定：测试仍断言 stub 成功、README 仍写 `Runner`

---

## 3. 逐项 Checklist

### G1 · 打包 / wheel

**前置**：已移除冗余 `force-include`，`packages` 只保留存在的包。

- [ ] `python -m build --wheel --outdir dist` exit 0
- [ ] wheel 重复路径检查为 `[]`
- [ ] wheel 内含 `templates/styles` 下 `.sty`/`.bst`
- [ ] `pip install dist/*.whl` 成功
- [ ] `researchclaw --help` 成功
- [ ] `pip install -e .` 仍成功
- [ ] `pyproject.toml` 不再引用 `sibyl`/`arc`
- [ ] CI 存在 wheel 构建 + 内容检查任务

**负向**：

- [ ] 向 `templates/styles` 添加一个临时文件后重新构建，仍无重复路径
- [ ] 不安装可选依赖时，核心包可导入

**证据**：`dist/*.whl`、`zipfile -l` 输出、CI 日志

**PASS**：以上全部；**FAIL**：仍出现 duplicate path 或 wheel 缺 styles。

**验收结果（PR-1，2026-10-29）：Pass**

- 构建：`python -m build --wheel` → `researchclaw-0.5.0-py3-none-any.whl`（隔离环境 hatchling 1.33.0）
- 内容：360 个条目、`duplicates: []`、含 `researchclaw/templates/styles/*/*.sty|.bst`
- 安装：干净 venv `pip install <wheel>` → `researchclaw --help` 正常列出 22 个子命令
- 无 extras：`import researchclaw / researchclaw.run_state / researchclaw.cli` 成功，`fastapi` 不可见
- 自动化：`tests/test_packaging.py` 6 项；CI `packaging` job 构建 + 重复路径检查
- 未单跑：向 `templates/styles` 临时加文件再构建（重复源已由移除 `force-include` 消除）

---

### G2 · MCP / OpenClaw

**前置**：14 号 D1 已裁定使用官方 MCP SDK v2 高层 `MCPServer`；不自研协议循环。

- [ ] `researchclaw mcp --start` 不立即退出
- [ ] SDK client 连接成功（`list_tools` 可用；v2 不再要求旧 handshake）
- [ ] `tools/list` 返回 6 个工具（或最终声明的数量）
- [ ] 未知工具返回 `-32602` / `isError`
- [ ] `run_pipeline` 返回真实 `run_id`，后台执行
- [ ] `get_pipeline_status` 随阶段推进变化
- [ ] `get_experiment_results` 命中 stage-14/12
- [ ] `get_paper` 命中 stage-22/23
- [ ] `search_literature` 返回真实结果或明确错误
- [ ] `review_paper` 有内容；无 LLM 配置时返回 `CONFIG_REQUIRED`
- [ ] `MCPClient` 真实往返
- [ ] 删除 `MCPMessageAdapter`/`MCPWebFetchAdapter` 的假结果；默认 Recording
- [ ] `AdapterBundle.from_config()` 不再返回假成功（若保留）

**负向**：

- [ ] 非法 `run_id` 被拒绝（路径遍历）
- [ ] 工具异常不导致 server 崩溃
- [ ] 服务停止后无残留 asyncio 任务/子进程

**证据**：JSON-RPC 日志、run 目录、client 输出

**PASS**：真实 run_id + 状态/结果/论文可查 + 无假成功；**FAIL**：`mcp-stub-*` 或空成功。

---

### G3 · RunState / checkpoint

**前置**：新增共享 `read_run_state()`，Dashboard/Projects/MCP 接入。

- [ ] 真实 checkpoint → `current_stage=last_completed_stage`
- [ ] `current_stage_name=last_completed_name`
- [ ] ISO heartbeat → `is_active` 正确
- [ ] epoch heartbeat → `is_active` 正确（兼容）
- [ ] 旧字段 `stage/stage_name/status` → 兼容或明确迁移
- [ ] `/api/projects` 返回真实 stage/status
- [ ] DashboardCollector 结果与 reader 一致
- [ ] `pipeline_summary.final_status=completed` → status 正确
- [ ] `schema_version` 缺失/未知 → 回退 + warning

**负向**：

- [ ] 损坏 JSON → 不崩溃
- [ ] 缺失 heartbeat → `is_active=False`
- [ ] 未来时间戳 → 不误判活跃

**证据**：单元测试、`/api/projects` JSON、Dashboard 截图

**PASS**：stage/name/is_active 正确；**FAIL**：stage=0 或 `is_active=False` 恒真。

**验收结果（PR-2，2026-10-29）：Pass**

- 单元测试：`tests/test_run_state.py` 15 个函数 / 17 个用例通过（v1 与 legacy checkpoint、ISO/epoch/未来 heartbeat、stale+HITL、损坏 JSON、topic 回退、artifacts、`to_dict`）
- 集成：`tests/test_frontend_mount.py::test_projects_endpoint_reads_real_checkpoint` 断言 `/api/projects` 返回 `current_stage=12`
- 真实 run 目录：`_write_checkpoint(12)` + `_write_heartbeat` 后，reader 与 `DashboardCollector` 均得到 `12 / EXPERIMENT_RUN / running / True`（修复前 `0 / "" / running / False`）
- 兼容策略：`schema` 缺失按 0 处理、legacy `stage/stage_name` 回退、`stale_after_sec` 可配（Dashboard 60s、默认 300s）

---

### G4 · 前端挂载

**前置**：`_resolve_frontend_dir()` 支持 env + `frontend` + `frontend-legacy` + packaged dist。

- [ ] `create_app()` 路由表包含 `/` 与 `/static`
- [ ] `GET /` 200 且包含 `<title>ResearchClaw`
- [ ] `GET /static/src/app.js` 200
- [ ] `GET /api/health` 200
- [ ] `RESEARCHCLAW_FRONTEND_DIR` 覆盖生效
- [ ] 目录缺失时 error 日志，不崩溃
- [ ] 浏览器加载 Dashboard 无 404/console error

**负向**：

- [ ] `/static/../` 等路径遍历被 StaticFiles 拒绝
- [ ] 前端文件缺失时 API 仍可用

**证据**：curl 输出、浏览器截图、日志

**PASS**：首页与静态资源 200；**FAIL**：首页 404 或路由表无 `/static`。

**验收结果（PR-2，2026-10-29）：Pass**

- `_resolve_frontend_dir()` 顺序：`RESEARCHCLAW_FRONTEND_DIR` → `<repo>/frontend` → `<repo>/frontend-legacy` → `researchclaw/webui/dist`，要求存在 `index.html`
- 测试：`tests/test_frontend_mount.py` 5 项通过（`GET /` 200 含 `ResearchClaw`、`/static/src/app.js` 200、env 覆盖、目录缺失时 API 仍 200、`/api/projects` 读真实 checkpoint）
- 目录缺失时记录 `logger.error`，不阻断应用创建
- 未覆盖：浏览器端 console 无 error、`/static/../` 遍历（由 Starlette `StaticFiles` 行为保证，未单独断言）

---

### G5 · 依赖 / extras

**前置**：`pyproject.toml` 增加 `server`、`mcp`、`voice` extras；错误提示同步。

- [ ] 干净 venv `pip install -e ".[server]"` 成功
- [ ] `python -c "import fastapi, uvicorn"` 成功
- [ ] `researchclaw serve --help` 成功
- [ ] 服务启动 + `/api/health` 200
- [ ] `pip install -e ".[voice]"` 成功
- [ ] `python -c "import httpx"` 成功
- [ ] `pip install -e ".[mcp]"` 成功（若采用 SDK）
- [ ] `pip install -e ".[all]"` 成功
- [ ] 核心 `pip install -e .` 不强制安装 FastAPI

**负向**：

- [ ] 未装 `[server]` 时，`serve` 给出可操作错误，而不是 ImportError 堆栈

**证据**：pip 输出、`pip list`、health 响应

**PASS**：extras 可安装、serve 可启动；**FAIL**：提示 `[web]` 或 ImportError。

---

### G6 · agentic

**前置**：已选择「接线」或「移除模式」；接线时 Stage 10/12/13 同步。

- [ ] `create_sandbox(mode=agentic)` 不再抛 Unsupported（或模式已移除且有清晰错误）
- [ ] Stage 10 产出 `agent_plan.md`（接线方案）
- [ ] Stage 12 调用 `run_agent_session(prompt, workspace)`
- [ ] 写出 `runs/run-1.json`、`results.json`
- [ ] Stage 13 跳过 refine 并填充 `experiment_final/`
- [ ] Docker 不可用 → 可操作错误
- [ ] timeout → 收集部分结果
- [ ] 容器清理（无残留 `docker ps`）
- [ ] skills 挂载/网络/GPU 参数按配置生效

**负向**：

- [ ] Agent 崩溃 → `status=failed`，不伪造指标
- [ ] 空输出 → 不产生假 `results.json`

**证据**：mock 调用参数、run JSON、容器列表

**PASS**：真实执行链路可跑通；**FAIL**：仍抛 Unsupported 或仍走 Python code 路径。

---

### G7 · biology_agent / stat_agent

**前置**：Stage 10 生成专属 plan；Stage 12 显式分派。

- [ ] Stage 10 产出 `biology_plan.md` / `stat_plan.md`
- [ ] Stage 12 sandbox 收到 plan 文本，不含 Python 代码特征
- [ ] `runs/results.json` 生成
- [ ] Stage 13 复制到 `experiment_final/`
- [ ] Stage 14 可解析指标
- [ ] 外部 Agent 目录缺失 → 清晰错误
- [ ] timeout/失败 → 不伪造成功

**负向**：

- [ ] plan 为空 → 不调用 sandbox，返回 upstream 错误
- [ ] results.json 非法 → Stage 14 报错/降级，不崩溃

**证据**：mock 调用参数、plan 文件、results JSON

**PASS**：plan→agent→results 链路正确；**FAIL**：仍把 `main.py` 当 prompt。

---

### G8 · 可选模块与成本

#### 成本

- [ ] 假 LLM 返回 usage → `cost_log.jsonl` 写入
- [ ] 累计成本 = 日志求和
- [ ] budget 超限 → pipeline 停止
- [ ] `CostGuard.check(run_dir)` 读取同一日志
- [ ] provider 返回 `usage.cost` → 采用真实费用
- [ ] 无定价 → cost=0 + 一次性 warning

#### experiment_spec

- [ ] 删除 runner 的 `stage-09` spec 生成（若采用删除方案）
- [ ] Stage 10 `stage-10/experiment_spec.md` 仍存在
- [ ] 若保留校验：读取 stage-10 spec + stage-14 summary
- [ ] 违规写 `stage-14/spec_violations.json`
- [ ] 合法结果不产生假违规

#### event_log / pitfall_detector（裁定 D6：删除）

- [ ] 删除 runner 中的 `event_log` / `pitfall_detector` 调用
- [ ] 不创建 `pipeline/event_log.py` / `pipeline/pitfall_detector.py`
- [ ] 全仓库搜索无未解释引用
- [ ] `cost_tracker` 保留并实现

**证据**：`cost_log.jsonl`、budget 停止日志、spec JSON

**PASS**：成本可计量、spec 不重复生成；**FAIL**：预算仍被跳过或空 spec 仍写入。

---

### G9 · 默认模式 / simulated 阻断

**前置**：D3 已裁定：默认 `sandbox` + warning。

- [ ] 不配置 mode → 默认 `sandbox`，并记录 warning
- [ ] 显式 `mode=simulated` → 保留，不 warning
- [ ] 非法 mode → `ValidationError`
- [ ] `mode=simulated` → `pipeline_summary.data_origin=simulated`
- [ ] CLI 打印 `FAKE DATA` 警告
- [ ] Stage 20 在 `allow_simulated_paper=False` 时阻断
- [ ] `allow_simulated_paper=True` 时放行 + warning + 水印
- [ ] `deliverables/` 不出现未授权 simulated 论文

**负向**：

- [ ] 显式 `sandbox`/`docker` 行为不变
- [ ] 旧配置 `simulated` 仍可运行（但被标记/阻断）

**证据**：配置测试、`pipeline_summary.json`、Stage 20 日志

**PASS**：假数据不能静默成论文；**FAIL**：默认 simulated 仍产出论文。

---

### G10 · README / Python API

**前置**：README 改为 `execute_pipeline`，或实现 `Runner` facade。

- [ ] README 代码块可导入
- [ ] `from researchclaw.pipeline import execute_pipeline` 可用（若导出）
- [ ] 文档不再出现不存在的 `Runner`（除非已实现）
- [ ] integration-guide 与 README 一致

**负向**：

- [ ] 文档代码块 lint/import 检查通过

**证据**：README diff、import 输出

**PASS**：示例可执行；**FAIL**：仍 ImportError。

---

### G11 · 测试与 CI

- [ ] `pytest tests/ -q` 全绿
- [ ] 新增 `test_packaging` / `test_run_state` / `test_mcp_protocol` / `test_frontend_mount` / `test_agent_dispatch`
- [ ] 旧 checkpoint fixture 已更新
- [ ] MCP stub 成功断言已删除/改写
- [ ] CI 执行 wheel build + install + `researchclaw --help`
- [ ] 可选依赖测试使用 `pytest.importorskip` 或 markers
- [ ] 网络测试标记为 integration，不阻塞单测

**证据**：pytest 报告、CI run

**PASS**：测试能捕获 G1/G2/G3 回归；**FAIL**：测试仍锁定旧契约。

---

### G12 · OpenClaw 适配器（裁定 D7：扩展点）

- [ ] 文档改为「默认录制桩，宿主注入真实适配器」
- [ ] 提供 `AdapterBundle.with_*()`/`from_runtime()` 或等价接口
- [ ] 默认 bundle 只记录、无副作用
- [ ] 删除 `MCPMessageAdapter`/`MCPWebFetchAdapter` 的假结果
- [ ] 若保留 `from_config`，无 endpoint 时返回 Recording + warning

**证据**：adapter 调用记录、文档 diff

**PASS**：文档与行为一致；**FAIL**：`use_*` 仍是 no-op 但文档声称生效。

---

## 4. 自动化测试映射

| Gap | 新增/更新测试 | 命令 |
|-----|---------------|------|
| G1 | `tests/test_packaging.py` 或 CI script | `pytest tests/test_packaging.py` |
| G2 | `tests/test_mcp_protocol.py` | `pytest tests/test_mcp_protocol.py` |
| G3 | `tests/test_run_state.py` | `pytest tests/test_run_state.py` |
| G4 | `tests/test_frontend_mount.py` | `pytest tests/test_frontend_mount.py` |
| G5 | CI/`test_server_extras.py` | `pytest tests/test_server_extras.py` |
| G6 | `tests/test_agent_dispatch.py` | `pytest tests/test_agent_dispatch.py` |
| G7 | `tests/test_agent_dispatch.py` | 同上 |
| G8 | `tests/test_cost_tracker.py`、`tests/test_spec_validation.py` | 对应文件 |
| G9 | `tests/test_simulated_guard.py` | `pytest tests/test_simulated_guard.py` |
| G10 | 文档示例 lint | CI script |
| G11 | 全量 | `pytest tests/ -q` |
| G12 | `tests/test_adapters.py` | `pytest tests/test_adapters.py` |

> 若本次不新增某些测试文件，可在 PR 说明中标注「由 CI/手工验收覆盖」，但不允许长期缺失。

---

## 5. 发布签署表

| Gap | PR | 验收人 | 主验收 | 负向 | 回归 | 证据链接 | 状态 |
|-----|----|--------|--------|------|------|----------|------|
| G1 | PR-1 | — | ☑ | ☑ | ☑ | `tests/test_packaging.py`；wheel 360 项 / `duplicates=[]` | Pass |
| G2 | | | ☐ | ☐ | ☐ | | Not started |
| G3 | PR-2 | — | ☑ | ☑ | ☑ | `tests/test_run_state.py`（15 函数 / 17 用例） | Pass |
| G4 | PR-2 | — | ☑ | ☐ | ☑ | `tests/test_frontend_mount.py`（5 项） | Pass |
| G5 | PR-1 | — | ☐ | ☐ | ☐ | extras 已加；逐条验收未跑 | In progress |
| G6 | | | ☐ | ☐ | ☐ | | Not started |
| G7 | | | ☐ | ☐ | ☐ | | Not started |
| G8 | | | ☐ | ☐ | ☐ | | Not started |
| G9 | | | ☐ | ☐ | ☐ | | Not started |
| G10 | | | ☐ | ☐ | ☐ | | Not started |
| G11 | PR-1 | — | ☐ | ☐ | ☐ | `.github/workflows/ci.yml` 已建；因仓库无 `.git` 未实际触发 | In progress |
| G12 | | | ☐ | ☐ | ☐ | | Not started |

状态取值：`Not started` / `In progress` / `Pass` / `Fail` / `Waived（原因）`。

---

## 6. 常见验收失败判定

| 现象 | 对应 Gap | 判定 |
|------|----------|------|
| `A second file is being added to the wheel archive` | G1 | FAIL |
| wheel 列表无 `templates/styles` | G1 | FAIL |
| `mcp --start` 3 秒内退出 | G2 | FAIL |
| `run_pipeline` 返回 `mcp-stub-*` | G2 | FAIL |
| `/api/projects` 的 `current_stage` 为 0/None | G3 | FAIL |
| Dashboard `is_active` 恒 False | G3 | FAIL |
| `GET /` 404 | G4 | FAIL |
| `GET /static/src/app.js` 404 | G4 | FAIL |
| `pip install ".[server]"` 后 `import fastapi` 失败 | G5 | FAIL |
| `create_sandbox(mode="agentic")` 仍抛 Unsupported | G6 | FAIL |
| biology/stat sandbox 收到 `import ...`/`def main` | G7 | FAIL |
| `cost_log.jsonl` 为空 | G8 | FAIL |
| Stage 20 放行未授权 simulated 论文 | G9 | FAIL |
| `from researchclaw.pipeline import Runner` 仍 ImportError | G10 | FAIL |
| 测试仍断言 MCP stub 成功 | G11 | FAIL |
| `openclaw_bridge.use_*` 仍无真实适配器却文档声称生效 | G12 | FAIL |

---

## 7. 回归清单（每个 PR 都要跑）

- [ ] `pytest tests/ -q`
- [ ] `python -m build --wheel`
- [ ] `pip install -e .`
- [ ] `researchclaw --help`
- [ ] `researchclaw validate --config <example>`（若配置有改动）
- [ ] `create_app()` 最小冒烟
- [ ] 若改 `llm`：`preflight` + fake chat
- [ ] 若改 `runner`：checkpoint/resume 测试
- [ ] 若改 `experiment`：`create_sandbox` 各模式工厂测试
- [ ] 若改 `mcp`：协议 + client 往返
- [ ] 若改 `server`：health + projects + runs

---

## 8. 文档同步清单

- [ ] `README.md`：Python API、安装 extras、MCP/成本能力描述与实际一致
- [ ] `docs/integration-guide.md`：Python API、OpenClaw bridge、MCP
- [ ] `code_wiki/09-interfaces-and-ops.md`：已知缺口状态更新
- [ ] `code_wiki/10-module-reference.md`：模块/依赖/已知缺口更新
- [ ] `code_wiki/11-gap-remediation-research.md`：方案状态更新（已修复/延后）
- [ ] `CHANGELOG`（如有）：行为变更、默认值变更、迁移说明
- [ ] 若修改默认 `experiment.mode`：明确标注 breaking change 与迁移方式

---

## 9. 最小可发布验收集（时间有限时）

如果只能做一轮验收，至少完成：

1. **Gate 0**：wheel 构建 + 安装 + CLI。
2. **Gate 1**：server 安装 + `/` + `/static` + `/api/projects` 真实 stage。
3. **Gate 3**：默认模式 + agentic/biology/stat 不再走错路径。
4. **Gate 5**：`pytest tests/ -q` + 新增 packaging/run_state 测试。

MCP（Gate 2）若本轮不修，必须在 README/CLI 中明确标记为「实验性/未实现」，不能继续宣传为可用功能。
