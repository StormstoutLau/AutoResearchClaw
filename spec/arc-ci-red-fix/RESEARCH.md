---
id: arc-ci-red-fix-RESEARCH
type: design
version: 1.2
status: draft
date: 2026-11-15
depends: [arc-ci-cd-research, arc-g4-m4-sandbox-limits, arc-g4-m3-tool-events]
upstream: null
---

# 调研文档：CI 红面归因与修复面（P-115 立项调研批）

> **Feature**：P-115，CI 红面修复批的立项调研（T3 Layer-0，零生产代码改动）。
> **Spec 步骤**：Step 1-2。
> **结论先行**：CI 红面不是单一原因，而是**三类性质不同的缺陷**叠加：①1 个真实生产回归（`run_id` 传参使默认 sandbox 模式的 iterative refine 全崩，本地可复现 14 failed）；②1 个 CPython 版本相关的私有属性遮蔽（`_TtlWatcher._stop` 覆盖 `threading.Thread._stop()`，≤3.12 崩、3.13 绿）；③3 处「实现与测试/配置漂移」（前端事件常量缺项、web 默认绑定值、spec-gates 缺 `mcp` extra）。**其中仅 ① 是阻断真实用户路径的缺陷，②③ 属门禁与对齐问题**。本批不动代码，产出修复面清单与裁决点供 DESIGN 批。

## 1. 调研目标

1. 把 CI 失败面**逐条落到文件行**，区分真实缺陷、环境差异、配置缺口。
2. 明确每条缺陷的**触发条件与生产影响**，排出修复优先级。
3. 识别需在 DESIGN 批裁决的真值冲突（尤其 web 默认绑定值）。
4. 界定本批修复半径，明确哪些红面**不修**（环境性/第三方）。

## 2. 调研方法与证据通道

| 通道 | 用途 | 结果 |
|---|---|---|
| 本地实跑（py3.13.5） | 复现四个失败文件 | ✅ 三类红面本地可现（见 §3） |
| CI 日志（run 43635083591） | 取 3.11/3.12 与 3.13/3.14 两档失败读数 | ✅ 22 vs 16 |
| 仓内读码 | 签名比对、调用点、fixture、workflow 安装段 | ✅ 全部落到行号 |
| 版本机制推演 | `threading.Thread._stop` 在 3.13 的行为变更 | ✅ 与 22−16=6 的差额互相印证 |

未使用：远端 3.11/3.12 本机复现（本机无该解释器），以 CI 日志替代。

## 3. 失败面清点

### 3.1 总表

| ID | 现象 | 本地读数 | CI 读数 | 性质 |
|---|---|---|---|---|
| R-1 | `ExperimentSandbox.run_project() got an unexpected keyword argument 'run_id'` | **14 failed / 193 passed**（test_rc_executor.py，114.58s） | 3.11/3.12/3.13/3.14 四矩阵均红（CI 记 13 条，与本地差 1，见 U-2） | **真实生产回归** |
| R-2 | `test_frontend_event_types_match_runtime` 集合不相等，缺 `tool.orphan_call` | 1 failed（test_event_stream.py） | 全矩阵红 | 实现/文档漂移 |
| R-3 | `test_server_config_defaults`：`assert '127.0.0.1' == '0.0.0.0'` | 1 failed（test_web_platform.py） | 全矩阵红 | 真值冲突（待裁决） |
| R-4 | `TypeError: 'Event' object is not callable`（`_Recorder` repr 即抛） | **0 failed**（test_sandbox_boundary.py 19 passed，TtlWatcher 子集 5 passed） | **仅 3.11/3.12 红 6 条** | CPython 版本相关 |
| R-5 | spec-gates job：pytest 收集 ImportError（`mcp` 与 `fastapi` 导入链）→ `ci_coverage_check --check` 判红 | 本机有 `mcp`/`fastapi`，不复现 | spec-gates job 红 | CI 配置缺口 |

合并读数：本地 `test_event_stream.py + test_web_platform.py` = **2 failed / 56 passed / 10 skipped / 4.48s**。

### 3.2 R-1：`run_id` 透传缺口（阻断级）

**证据链**

- 调用点无条件传参：[`_execution.py#L1644-L1648`](../../researchclaw/pipeline/stage_impls/_execution.py#L1644-L1648) `sandbox.run_project(version_dir, timeout_sec=..., run_id=stage_dir.name)`。
- `DockerSandbox` 支持该参数：[`docker_sandbox.py#L255-L264`](../../researchclaw/experiment/docker_sandbox.py#L255-L264) 有 `run_id: str | None = None`（P-105 批次加的）。
- 但 `SandboxProtocol` 与 `ExperimentSandbox` 都没有：[`sandbox.py#L301-L309`](../../researchclaw/experiment/sandbox.py#L301-L309)（Protocol）、[`sandbox.py#L358-L366`](../../researchclaw/experiment/sandbox.py#L358-L366)（实现），签名止于 `env_overrides`。
- traceback 显示实际类型为 `ExperimentSandbox`（`create_sandbox` 在 `mode="sandbox"` 下返回它）。

**触发条件**：`config.experiment.mode in ("sandbox", "docker")` 且 `validation.ok`，即 **iterative refine 的每一次重跑**。`mode="sandbox"`（本地 subprocess，默认路径）必崩；`mode="docker"` 正常。

**影响**：默认本地 sandbox 模式下 refine 循环完全不可用，异常在 `_execution.py` 内抛出后被外层捕获成失败迭代——用户侧表现为「实验永远不收敛」。这是 P-105 引入 `run_id` 时**只改了 Docker 后端与调用点，漏改协议与本地后端**造成的回归。

**修复候选**（裁决留 DESIGN）：

| 方案 | 内容 | 代价 |
|---|---|---|
| A | `SandboxProtocol` + `ExperimentSandbox.run_project` 增 `run_id: str \| None = None`，忽略或用于日志 | 3 行；语义最小 |
| B | 调用点按后端能力探测后再传 `run_id` | 引入运行时探测，违 Protocol 意图 |
| C | 回退调用点的 `run_id` | 丢失 P-105 的容器归因能力 |

倾向 A：`run_id` 在本地后端无容器语义，接受并忽略即可，但须在 DESIGN 明确「接受但不用」的口径，避免误以为有归因效果。

### 3.3 R-4：`_TtlWatcher._stop` 遮蔽 `Thread._stop()`

**证据链**

- [`docker_sandbox.py#L47`](../../researchclaw/experiment/docker_sandbox.py#L47) `class _TtlWatcher(threading.Thread)`。
- [`docker_sandbox.py#L72`](../../researchclaw/experiment/docker_sandbox.py#L72) `self._stop = threading.Event()` —— **实例属性名与 `threading.Thread._stop()` 私有方法同名**。
- CPython ≤3.12 的 `Thread.join()` → `_wait_for_tstate_lock()` 内部调用 `self._stop()`；3.13 重构 threading 后不再调用。
- 本地 3.13.5：`test_sandbox_boundary.py` 19 passed、`-k TtlWatcher` 5 passed。
- CI：仅 3.11/3.12 出现 6 条 `'Event' object is not callable`，且 pytest 展示上下文均为 `_watcher_log = [...]`（该 fixture 专属，见 [`test_sandbox_boundary.py#L95-L107`](../../tests/test_sandbox_boundary.py#L95-L107)）。
- 数量吻合：CI 两档失败 22（3.11/3.12）− 16（3.13/3.14）= **6**。

**性质**：不是产品逻辑缺陷（TTL 行为本身正确），而是**与解释器私有实现的命名冲突**。在 3.11/3.12 的受支持矩阵内属真实红面，必须修。

**修复候选**：改名为 `self._stop_event`（内部私有，无外部引用）；或改用 `threading.Event` 但遮蔽 `Thread._stop` 的风险仍在，改名是唯一根治。需全仓 grep 确认无测试直接读 `_watcher._stop`（本批已验证 `_stop` 仅在类内使用）。

### 3.4 R-2：前端事件常量缺 `tool.orphan_call`

- 后端真值：[`event_log.py#L40`](../../researchclaw/runtime/event_log.py#L40) `EVENT_TYPES` 已含 `"tool.orphan_call"`。
- 前端真值：`frontend-legacy/src/services/api.js` 的 `const EVENT_TYPES = [...]`（test 用 `split("const EVENT_TYPES = [")` 提取）缺该项。
- 守卫：[`test_event_stream.py#L102-L109`](../../tests/test_event_stream.py#L102-L109) 做双向集合相等。
- 归属：P-104（arc-g4-m3-tool-events）新增后端类型时，实施清单只列 `event_log.py`，未列前端常量（见该 feature IMPLEMENTATION 第 6 行）。
- 修复：前端补 1 项。风险近乎零（纯常量）。

### 3.5 R-3：web 默认绑定值真值冲突

- 实现：[`config.py#L757`](../../researchclaw/config.py#L757) `host: str = "127.0.0.1"`，`cors_origins` 为显式两项（:759-762），`auth_token=""  # loopback only`（:763）。
- 测试：[`test_web_platform.py#L33`](../../tests/test_web_platform.py#L33) 断言 `"0.0.0.0"`，**同函数 :35 还断言 `cors_origins == ("*",)`——两条均与实现相反**。
- 安全守卫：[`config.py#L772-L782`](../../researchclaw/config.py#L772-L782) `validate_server_security` docstring 为 "Fail closed on unsafe server defaults (Q19 / H-8)"；[`test_cors_default.py`](../../tests/test_cors_default.py) 三向锁定（无 token 的 0.0.0.0 必抛错 / 有 token 通过 / 默认构造通过）。
- 历史：[arc-cli-agent-seam/IMPLEMENTATION.md](../arc-cli-agent-seam/IMPLEMENTATION.md) 已记为既有失败；`127.0.0.1` 与 `_LOOPBACK_HOSTS` 同由 `00df470`（P-006 Q19/H-8 安全加固）引入。
- **已裁决：以实现为真值、改测试**，依据与反证见 §8.2。

### 3.6 R-5：spec-gates 缺 `mcp` 与 `server` extras

- [ci.yml#L166](../../.github/workflows/ci.yml#L166) spec-gates 安装 `".[dev]"`，而 Tests job 安装 `".[dev,server,mcp]"`（L121）、Packaging 用 `".[server,mcp,voice]"`（L89）。
- `dev` extra 仅含 pytest/pytest-asyncio/httpx/jsonschema/build/hatchling（`pyproject.toml:42-L49`）——**既无 `mcp` 也无 `server`（fastapi/uvicorn）**。
- 收集失败面共 **3 个文件**（v1.2 审查补正，原只识别 2 个）：
  - `test_mcp_dynamic_tools.py:17` 模块级 `from mcp.server import MCPServer`（mcp SDK 直连）；
  - `test_tool_events.py:14` 模块级 `from researchclaw.mcp.server import ...` → [`researchclaw/mcp/server.py#L27-L28`](../../researchclaw/mcp/server.py#L27-L28) 守卫导入抛 `ImportError: MCP support requires the 'mcp' extra`（CI 日志实证）；
  - `test_events_api.py:11-12` 模块级 `from fastapi import FastAPI` / `from fastapi.testclient import TestClient`——其前哨 `importorskip("httpx")`（:9）在 `.[dev]` 下可通过（dev 含 httpx，`pyproject.toml:45`），随后 fastapi 导入即失败。
  - 对照组（收集安全，不计入）：`test_web_platform.py` 与 `test_frontend_mount.py` 的 server 导入全部为函数内懒导入或 `pytest.importorskip("fastapi")`。
- 后果：任一收集失败即 `pytest --collect-only` 非零退出，[`ci_coverage_check.py#L80`](../../scripts/spec/ci_coverage_check.py#L80) 抛 RuntimeError 判红。CI 日志 tail 只见 mcp 守卫错误，是因为 :80 只回显输出尾部，fastapi/直连 mcp 的报错被截去。
- 性质：**fail-closed 语义正确生效**（守卫把收集失败当红），错在 job 的环境声明。修复 = 安装串改为 `".[dev,server,mcp]"`（与 Tests job L121 对齐；**v1.2 更正：仅补 `mcp` 不够**，fastapi 链同样会红）。

## 4. 环境差异分析

| 版本档 | 失败数 | 组成 |
|---|---|---|
| 3.11 / 3.12 | 22 | R-1(13) + R-4(6) + R-2(1) + R-3(1) + 其他环境性(1) |
| 3.13 / 3.14 | 16 | R-1(13) + R-2(1) + R-3(1) + 其他环境性(1) |

> 差额 6 全部由 R-4 解释。R-1 在 CI 记 13 而本地记 14，差 1 条待查（U-2），不影响根因判断。

**排除项（本批不修）**：keras3/transformers 相关 4 条、bash 缺失 2 条、hitl shell 1 条——均为第三方或宿主环境依赖，与本次红面归因无关，登记为本批边界外。

## 5. 修复面与批次切分建议

| 优先级 | 项 | 文件 | 预估半径 |
|---|---|---|---|
| P0 | R-1 `run_id` 纳入协议面 | `sandbox.py`（Protocol 2 + ExperimentSandbox 2）、`ssh_sandbox.py` / `colab_sandbox.py` / `collider_agent_sandbox.py` / `biology_agent_sandbox.py` / `stat_agent_sandbox.py`（各 `run` + `run_project`） | **14 处签名**（Protocol 2 + 6 后端各 2；docker 已有，不改） |
| P0 | R-4 `_stop` 改名 | `docker_sandbox.py`（:72 定义 + 7 处使用） | 纯重命名 |
| P1 | R-2 前端常量补项 | `frontend-legacy/src/services/api.js` | 1 行 |
| P1 | R-5 spec-gates 补 extras | `.github/workflows/ci.yml`（:166 `".[dev]"` → `".[dev,server,mcp]"`） | 1 行 |
| P2 | R-3 对齐陈旧断言 | `test_web_platform.py`（:33 `host`、:35 `cors_origins`） | 2 行 |

建议**单批交付**：五项互不冲突，总半径 = **10 个修改文件 + 1 个新增契约测试 = 11 文件**（R-1 六文件 + R-4/R-2/R-5/R-3 各一；原估 5 文件偏低，因 `run_id` 崩溃面覆盖 6 个后端）。R-3 按 §8.2 裁决只改测试，不动 `config.py`。

## 6. 未决问题（供 DESIGN 裁决）

- ~~**U-1**~~：**已裁决（§8.1）**——协议面统一可选参数，非容器后端 no-op。
- **U-2**：R-1 CI 13 条 vs 本地 14 条的差异条目待定位（疑似某用例依赖 bash 或外部工具在 CI 跳过）。
- ~~**U-3**~~：**已裁决（§8.2）**——以 `ServerConfig` 为真值，修正测试两条陈旧断言。
- **U-6（v1.2 已收窄）**：全仓 `*.md` 检索 `0.0.0.0`——**README.md 无任何默认 host 声明**；命中均为历史记录性质（`arc-master-roadmap.md:754` Q19 行、`spec/arc-roadmap-gaps/{RESEARCH,CHECKLIST}.md`、`docs/arc-g1-readiness-research-20261108.md:120`），记录的是 P-006 加固前的状态，**无需订正**。
- **U-4**：R-5 是否同时给 `ci_coverage_check` 增加「收集阶段失败」专属提示（增强，非必需）。
- **U-5**：修复后是否需要回填 [arc-ci-cd-research/CHECKLIST.md](../arc-ci-cd-research/CHECKLIST.md) 中「CI 连续两次全绿」前置（影响分支保护执行时点）。

## 7. 结论

1. CI 红面**不是**「CI 配置坏了」这一层的问题：其中 R-1 是会阻断默认执行路径的真实回归，优先级最高。
2. R-4 是版本相关命名冲突，本地 3.13 绿会制造「本地绿、CI 红」的假象，必须按 3.11/3.12 矩阵判定，不能以本地读数结案。
3. R-2/R-3/R-5 属对齐与配置层面，风险低但必须一并收口，否则「CI 连续两次全绿」永远无法达成，分支保护无法启用。
4. 本批建议一次修完五项、单提交交付；U-1/U-3 已在 §8 裁决，DESIGN 批可直接消费，无需再开裁决轮。

## 8. U-1 / U-3 补充调研与裁决（2026-11-15 补，v1.1）

> 本节只记录**可在仓内逐行核对**的证据；凡无法用文件/行号/命令支撑的推断均已剔除。

### 8.1 U-1：`run_id` 的真实语义与崩溃面

**取证**

| # | 事实 | 位置 |
|---|---|---|
| 1 | `run_id` 只有两个用途：TTL 守卫门控 `if run_id and effective_ttl > 0`；容器标签 `--label rc.run={run_id}` | `docker_sandbox.py:419`、`:579-L580` |
| 2 | 全 `experiment/` 目录内，`run_id` 形参只出现在 `docker_sandbox.py`（`run` :238、`run_project` :263、`_execute` :394、`_run_container` :544） | grep `run_id` 全目录 |
| 3 | 其余 6 个后端的 `run` / `run_project` **均无**该形参；`ssh_sandbox.py:189` 的 `run_id` 是其内部 `uuid` 局部变量，不接收外部传参 | `ssh/colab/collider_agent/biology_agent/stat_agent` 各文件 |
| 4 | pipeline 内 `sandbox.run*`/`run_project` 调用点共 **8 处**（v1.2 补全）：**4 处传参**——`_execution.py:551`（`run_project`）、`:557`（**`run`，单文件路径**）、`:1644`、`:1770`；**4 处不传**（良性不崩溃）——`experiment_repair.py:811`、`_execution.py:289`、`:472`、`pipeline/code_agent.py:1394` | 各自行号 |
| 5 | 调用点注释原文：`# run_id ties the container to this run (rc.run label + TTL scope).` | `_execution.py:548-L549` |
| 6 | `create_sandbox` 有 7 条分支，且 **docker 分支在 daemon 不可达时回退 `ExperimentSandbox`** | `factory.py:18-L108`（回退 :29-L34） |
| 7 | `ExperimentConfig.mode` 默认 `"sandbox"`（注释称 safe default） | `config.py:608` |

**由取证得出的三个硬结论**

1. **崩溃面远大于原估**：不止 `run_project` 一处，`run()` 单文件路径同样崩（取证 4）；且覆盖默认 `sandbox` 模式、docker 回退、以及 ssh/colab/collider/biology/stat 五个显式模式（取证 3、6、7）。
2. **「按 `config.mode` 条件传参」不成立**：`mode="docker"` 仍可能实际运行在 `ExperimentSandbox` 上（取证 6），条件判断会漏掉回退路径。
3. **`run_id` 对非容器后端无任何可承载语义**：它只驱动 Docker 的 TTL 与标签（取证 1、5），本地 subprocess / SSH / 各 agent 后端没有对应机制。

**裁决：D1（采用）——协议面统一可选形参、非容器后端 no-op**

`SandboxProtocol.run` / `run_project` 及全部后端的同名方法增加 `run_id: str | None = None`；除 Docker 外不读取，docstring 注明「仅 docker 后端用于 `rc.run` 标签与 TTL 门控」。

| 备选 | 否决理由 |
|---|---|
| D2 调用点 `isinstance(sandbox, DockerSandbox)` 后传参 | 破坏 `SandboxProtocol` 抽象；新增后端需回溯改调用点；4 处调用点重复判断 |
| D3 回退调用点的 `run_id` | 直接废掉 P-105 的容器归因与 TTL 清理能力，属功能倒退 |
| D4 按 `config.mode` 条件传参 | 取证 6 证明 `mode=docker` 可回退本地后端，条件不可靠 |
| D5 运行时 `inspect.signature` 探测 | 隐式契约、不可静态检查，且掩盖签名漂移 |

**验收**：`pytest tests/test_rc_executor.py` 由 14 failed → 0（2026-11-15 审查复核实测 **14 failed / 193 passed，151.42s**，14 条全部为 `run_id` TypeError）；新增契约测试断言 Protocol 与 **7 个实现**的 `run`/`run_project` 形参名集合逐项一致（防再次漂移）。7 个实现范围（v1.2 注明）：`experiment/` 目录内 ExperimentSandbox、Docker、SSH、Colab、collider、biology、stat；`agentic_sandbox.py` 与 `experiment/code_agent.py` 不实现 `run`/`run_project`，`pipeline/code_agent.py:91-98` 的 `_SandboxLike` 是本地窄 Protocol，均不在契约面。

### 8.2 U-3：web 默认绑定的真值归属

**取证**

| # | 事实 | 位置 |
|---|---|---|
| 1 | `host: str = "127.0.0.1"`；`cors_origins` 为 `("http://localhost:3000", "http://127.0.0.1:3000")`；`auth_token: str = ""  # empty = no authentication (loopback only)` | `config.py:757`、`:759-L762`、`:763` |
| 2 | `validate_server_security` docstring：**"Fail closed on unsafe server defaults (Q19 / H-8)"**；cors 含 `*` 抛错；host 非 loopback 且无 token 抛错 | `config.py:772-L782` |
| 3 | `ServerConfig(cors_origins=("*",))` → 抛错；`ServerConfig(host="0.0.0.0")` → 抛错；`ServerConfig(host="0.0.0.0", auth_token="token")` → 通过；**`ServerConfig()` 默认构造 → 通过** | `test_cors_default.py:20`、`:25`、`:29`、`:33` |
| 4 | `127.0.0.1` 与 `_LOOPBACK_HOSTS` 同时由提交 `00df470 feat(g1): close the eight first-aid gaps and land Q18/Q19/Q20 verdicts` 引入 | `git log -S` 双查同结果 |
| 5 | CLI 可覆盖：`host = args.host or config.server.host` | `cli.py:762`、`:788` |

**反证（关键）**：若把默认值改为 `0.0.0.0`，则 `ServerConfig()` 默认构造立即违反取证 2 的守卫，`test_cors_default.py:33` 必然转红——即「改实现」方案会直接制造一条新的红面，与 Q19 的 fail-closed 裁决冲突。故 `127.0.0.1` 是**被双向测试锁定的真值**，`test_web_platform.py` 是加固前遗留断言。

**裁决：D1（采用）——以实现为真值，修正测试两条断言**

- `test_web_platform.py:33`：`"0.0.0.0"` → `"127.0.0.1"`
- `test_web_platform.py:35`：`("*",)` → `("http://localhost:3000", "http://127.0.0.1:3000")`（原 RESEARCH 只识别出 host 一条，此处更正为两条）

不改 `config.py`；**不新增**「0.0.0.0 正向用例」——`test_cors_default.py:29` 已是该用例，重复无价值。

**残留**：README/其他文档若声明默认 `host` 为 `0.0.0.0`，须在实施批一并订正（登记为 U-6，本批不执行）。

### 8.3 对 §5 的修正

原 §5 将 R-1 估为「2 处签名 + 1 处透传」，实际为 **14 处签名**（Protocol 2 + 6 个非 Docker 后端各 2）；R-3 由「1 行 + 用例调整」收紧为「测试 2 行」。总半径 5 文件 → **11 文件**。

## 9. 独立性审查记录（2026-11-15，v1.2）

> 对 v1.1 全部证据链做独立复核：每条声明重新取证（逐行读码 + 实测复跑 + CI 日志重取），不依赖本文档自述。

**复核通过（零幻觉）**

| 声明 | 复核方式 | 结果 |
|---|---|---|
| R-1 本地 14 failed / 193 passed | 复跑 `pytest tests/test_rc_executor.py`（151.42s） | ✅ 完全一致；14 条全部为 `ExperimentSandbox.run_project() got an unexpected keyword argument 'run_id'` |
| R-1 签名/调用点/factory 回退/mode 默认 | 逐行读码（docker_sandbox/sandbox/_execution/factory/config 5 文件） | ✅ 行号全部吻合 |
| R-2 前后端常量差 | 读 `event_log.py:37-44` 与 `api.js:86-93` + 复跑 | ✅ 前端数组确缺 `tool.orphan_call` |
| R-3 双陈旧断言 | 读 `config.py:752-782`、`test_web_platform.py:28-37`、`test_cors_default.py` 全文 + 复跑 | ✅ `:33`/`:35` 均与实现相反 |
| R-4 `_stop` 定义+7 使用 | grep 全文件（恰 8 行命中）+ 读码 :40-150 | ✅ |
| §8.1 取证 1-7、§8.2 取证 1-5 | 逐条重新定位 | ✅ 全部吻合 |
| CI 定量读数 | `gh run view 43635083591 --log-failed` 逐 job 统计 FAILED 行 | ✅ 总 76 = 22+22+16+16；`run_id` 52 = 13×4 矩阵；`not callable` 12 = 6×2（仅 3.11/3.12）；R-2/R-3 各 4 = 1×4；job 结论 failure、head=b135b4f |
| spec-gates 根因 | CI 日志 grep ImportError | ✅ `MCP support requires the 'mcp' extra`（守卫文案，出 `researchclaw/mcp/server.py:27-28`） |

**v1.2 订正（2 处，均不改变 D1 裁决）**

1. **R-5 文件清单 + 修复行**（§3.6/§5）：补 `test_events_api.py:11-12`（模块级 fastapi 导入，`.[dev]` 下收集失败）；修复由「补 `mcp`」更正为 `".[dev,server,mcp]"`。CI 日志 tail 只见 mcp 错误系 `ci_coverage_check.py:80` 只回显尾部所致。
2. **§8.1 取证 4 调用点清单**：由「4 传 + repair 不传」补全为「4 传 + 4 不传」（另 3 处良性：`_execution.py:289`、`:472`、`pipeline/code_agent.py:1394`）；契约测试范围注明排除 `_SandboxLike` 本地 Protocol 与未实现 `run`/`run_project` 的 `agentic_sandbox.py`、`experiment/code_agent.py`（§8.1 验收段）。

**U-6 收窄**：README 无 `0.0.0.0` 声明，命中均为历史记录文档，无需订正（见 §6）。
