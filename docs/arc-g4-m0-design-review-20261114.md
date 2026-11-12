# P-100 对 P-099「G4 M0 设计冻结」的独立异构复核（2026-11-14）

> **性质**：Layer-0 独立异构复核（T3，零生产代码/零门禁）。不采信 [P-099 设计](../spec/arc-g4-m0-design/IMPLEMENTATION.md) 的任何结论，全部一手重验：HEAD `eec472b` 读码、现状断言 11 项逐项复核（E1/E3）、SDK 探针复验（E2）、session digest 逐文件复算、**12 组设计对抗审查**（审批门组合矩阵/依赖面/沙箱语义/守卫可实现性/批次集成点）。**异构性**：实施会话为 **DeepSeek-V4.1-Flash**（`specwf-p099-arc-g4-m0-design.jsonl` model 字段），本复核为 **GLM-5.3-Flash**——G4 阶段延续 G3 的 RULE-5 交替交叉（P-095 DeepSeek 复评 GLM、P-097 GLM 复评 DeepSeek、P-099 DeepSeek 实施 → 本批 GLM 复核）。**单向权限**：只标记问题，不改任何设计文档；探针零残留。
> **编号说明**：本批占用 **P-100**；G4-M1..M5 编号**顺延为 P-101..P-105**（P-084/P-086 让位先例）；设计文档中 `P-100..P-104` 的旧编号引用以本报告 §6 为准，M1 批（P-101）落地时在设计受控回边中订正。

## 1. 一手复验（V 表）

| # | 声明 | 方式 | 结果 |
|---|---|---|---|
| V-1 | A4-1 现状：registry 无、6 工具硬编码 | `Test-Path tools/registry.yaml` → False；`server.py` grep `@mcp.tool(name=` 2 处装饰器 + `_handlers` 6 项 | ✅ 成立 |
| V-2 | A4-4 现状：`EVENT_TYPES` 含 `tool.call`/`tool.result`，**无生产者** | `event_log.py` L40 + 全仓 grep 生产者 = 0 | ✅ 成立 |
| V-3 | A4-7 现状：`build_subprocess_env` 3 文件 | grep 计数 = `experiment/sandbox.py`、`mcp/client.py`、`utils/env.py`（定义处） | ✅ 3 文件成立 |
| V-4 | A4-8 现状：`safe_join` 2 文件 | grep 计数 = `pipeline/stage_impls/_execution.py`、`utils/paths.py`（定义处） | ✅ 2 文件成立 |
| V-5 | A4-9 现状：无 HostProfile；全仓 `shell=True` = 0 | grep = 0 / 0 | ✅ 成立 |
| V-6 | A4-10 现状：无 `GET /api/tools`；SDK `MCPServer` 类无 list_changed | routes grep = 0；`dir(MCPServer)` 无该项 | ✅ 成立 |
| V-7 | A4-10 可行性：`send_tool_list_changed` 在位 | `session.py:461`、`connection.py:441`、`subscriptions.py` 含 `tools_list_changed` | ✅ 复现（E2） |
| V-8 | **A4-3 现状：`docker_sandbox.py` 无 `--memory`** | 读码 L383-391 | ❌ **不成立**——`--memory={cfg.memory_limit_mb}m` **已存在**（默认 8192MB）+ `--shm-size`；缺失的是 `--pids-limit/--cpus/--label/TTL/137` → **D-7** |
| V-9 | A4-2 引用精度：「`--gpus all`（L225）」 | 读码 L220-234 | ⚠️ L225 是 `check_nvidia_runtime()` **探测命令**，非执行路径；主执行路径（L383+）无 `--gpus` → O-5 |
| V-10 | 依赖面：`jsonschema` 仅 dev extras（L43） | 读 `pyproject.toml` | ✅ 成立 |
| V-11 | session digest 与 HEAD 一致 | 本地 sha256 逐文件复算 | ✅ 5 行、1 次 finalize、5 文件零 mismatch |
| V-12 | 零生产代码变更 | `git show --stat eec472b` | ✅ 9 文件全部为文档/登记/派生视图 |

## 2. 设计对抗审查（X 表，12 组）

> 设计复核的对抗面 = **组合矩阵完备性 / 依赖一致性 / 语义精度 / 可实现性 / 与仓内现实耦合**。每项发现均给修复输入（审查者不改设计）。

| # | 探针 | 推演与证据 | 定级 |
|---|---|---|---|
| X-1 | **审批门组合矩阵**：`approval=never` × `risk=high` | DESIGN §5 拒绝分支 = `always` ∨（`high_only` ∧ `high`）。`never` + `high` 不落任何拒绝分支 → **高危工具可被配置为永久免审批**。A4-5 负向用例「`risk=high` 未审批拒绝」被注册表自身配置绕过（**fail-open 设计漏洞**） | **D-1 P2** |
| X-2 | **依赖一致性**：`registry.py` 位于核心包 vs `jsonschema` 在 optional extras | DESIGN §2 说「缺失时 `E_REGISTRY_DEP`」——两种互斥解读：①报错退出 = 纯 CLI/pipeline 用户（不装 server/mcp extras）被 extras 依赖绑架启动；②降级跳过 = 弱化 fail-closed。**核心启动路径依赖 optional 包**的结构性矛盾未裁决 | **D-2 P2** |
| X-3 | **137 语义精度**：「资源超限 → 退出码 137」 | Docker 中 `--memory` OOM 与 `--pids-limit` 超限 → kill（137）；**`--cpus` 超限是 CFS throttling（降速），不产生 137**。A4-3 断言若按「任何超限 → 137」实现会无法构造 cpu 类用例；且 memory 配额**已存在**（V-8），M4 的 137 范围须限定为 memory/pids 两类 | **D-3 P3** |
| X-4 | **TTL 语义**：「TTL 到期被回收，产物已落盘」 | 容器 **hang** 场景下产物未落盘，TTL kill 后「产物已落盘」断言不可能成立。A4-6 正向断言须限定「可落盘产物」；`tool.result.reason=ttl_timeout` 标记未定义 | **D-4 P3** |
| X-5 | **SDK schema 注入**：「注册表 schema 为真值源 + CI 断言一致」 | SDK 2.x `@server.tool()` 从**函数签名**生成 inputSchema；设计未说明注册表 schema 如何注入 SDK（生成 wrapper 签名？绕过 decorator 用底层 API？）。「一致」的判定基准未定义。M2 有实现卡点风险，需先 spike | **D-5 P3** |
| X-6 | **AST 守卫精度**：「所有 `subprocess.*(env=...)` 的 env 必须来自 `build_subprocess_env`」 | AST 层面判定「env 来自 build_subprocess_env」需变量数据流追踪（`env = build(); run(env=env)` 的中间变量）；「用户可控文件名」的静态判定同理。纯 AST（无类型/流分析）会漏报或误报爆炸。M5 需降级为「注册制白名单 + AST 扫描兜底」或引入保守规则并诚实登记误报率 | **D-6 P3** |
| X-7 | **现状断言复核**：A4-3「无 --memory/--pids-limit/--cpus」 | V-8 证伪：memory 已有。G-7 缺口范围须收窄为「pids/cpus/label/TTL/137 五项」；M4 工作量估计相应修正；`DockerSandboxConfig.memory_limit_mb`（config.py L317/L340，默认 8192）应作为 profile `memory` 的既有默认 | **D-7 P3** |
| X-8 | **审批机制复用**：`approvals.json` vs 既有 `hitl/` | `researchclaw/hitl/` 已有 `escalation.py`（`auto_action: approve/abort`）、`intervention.py`、`hooks.py` 等；DESIGN §5 新建 `approvals.json` 未提及复用/共存关系。M3 应先评估复用 `hitl.escalation` 或显式声明不兼容原因 | O-1 |
| X-9 | **事件摘要脱敏**：`args_summary ≤200 字符` | 参数可能含 `api_key`/token 等敏感值；截断摘要会把前 200 字符（含密钥前缀）写入 events.jsonl（永久留存）。设计未声明脱敏规则（键名黑名单剔除 or 摘要仅取结构形状） | O-2 |
| X-10 | **gpu 与 profile**：主执行路径无 `--gpus`，`sandbox_profiles` 无 gpu 字段 | 既有行为（实验沙箱默认不加 GPU？需 M4 读全 run() 方法确认）；注册表 profile 冻结的六要素未含 gpu → GPU 工具无法表达 | O-3 |
| X-11 | **fail-closed 启动范围**：「应用启动路径最前调用」 | 全入口（含纯 pipeline CLI）失败 vs 仅 server/MCP/invoker 入口——设计未裁决。前者把工具子系统故障传导给纯研究流程用户 | O-4 |
| X-12 | **批次集成点**：M2 adapter 何时接入 invoker | M2 的 `_wrapped` 直调 handler，M3 才补事件/审批——若 M2 把调用路径写死，M3 需回改 adapter。DESIGN §9 已标依赖顺序但未声明「M2 须预留 invoker 接缝」 | O-5 |

## 3. 缺陷

### D-1（P2）审批门组合漏洞：`approval=never` + `risk=high` 绕过 A4-5

- **根因**：DESIGN §5 拒绝谓词 `always ∨ (high_only ∧ high)` 是**配置驱动**的，而 A4-5 是**风险驱动**的断言——两者在 `never`+`high` 组合上冲突。
- **若照设计实现**：注册表写 `approval: never, risk: high` 的工具将永久免审批执行 → A4-5 负向用例在该配置下**失败**（验收不可达）。
- **修复输入（供 M1/M3 吸收）**：① 注册表校验新增规则——`risk=high ⇒ approval ∈ {always, high_only}`（V-8，`E_REGISTRY_APPROVAL`）；**且** ② 审批门谓词加保险分支——`risk=high ∧ 无有效审批 → 拒绝`（与 approval 字段解耦，双保险）。①② 并用后 fail-open 面关闭。

### D-2（P2）核心启动路径依赖 optional extras：registry 校验的 `jsonschema` 矛盾

- **根因**：`researchclaw/tools/registry.py` 属核心包；`jsonschema` 在 dev extras（V-10），Q-1 建议并入 `server`/`mcp` extras。若 registry 由 CLI/pipeline 路径加载 → `ImportError`；若按「缺失时 `E_REGISTRY_DEP`」报错退出 → 不装 extras 的用户**无法启动任何入口**（fail-closed 被依赖面绑架）；若降级跳过 → 违反 A4-1。
- **修复输入（供 M1 裁决，三选一）**：① `jsonschema>=4.20` 升**核心依赖**（~2 个间接依赖，体积代价小，语义最干净——**建议**）；② 校验器分两级：结构性校验（手写、零依赖、fail-closed）+ JSON Schema 全量校验（jsonschema 在位时启用，缺失记 warning）；③ registry.py 整体移入 `mcp/` 子包（仅 MCP/REST 消费）。②与 fail-closed 有张力，①最简。

### D-3（P3）137 语义：cpu 超限是 throttling 非 kill

A4-3 的 137 断言仅对 **memory OOM / pids 超限**可构造；`--cpus` 超限产生 CFS 降速。M4 须把「资源超限 → 137」实现限定为这两类，cpu 配额只作防降速护栏（其负向用例改测 throttling 生效或从 A4-3 剥离）。

### D-4（P3）TTL 回收与产物落盘的不可兼得场景

容器 hang 时产物未落盘，A4-6 正向断言在该场景不可满足。M4 须把 A4-6 实现为「TTL 到期 → 先尽最大努力落盘（docker cp）→ kill → `tool.result.reason=ttl_timeout`」，负向用例断言「容器无残留」而非「产物必存在」。

### D-5（P3）MCP schema 注入机制未定

`@server.tool()` 从函数签名生成 schema；「注册表为真值源 + CI 断言一致」缺注入机制与判定基准。**M2 开工前须 spike**：确认 SDK 2.x 是否支持外部 inputSchema（decorator 参数或底层 `add_tool` API）；若不支持，则 wrapper 按注册表 schema 程序化构造签名，或改用 SDK 低层注册 API 并以注册表为唯一 schema 来源。

### D-6（P3）AST 覆盖守卫的实现精度风险

「env 来源」与「用户可控路径」的静态判定需数据流追踪。M5 建议改为：**注册制白名单**（显式登记每个 subprocess 调用点及其 env 策略/路径策略，缺失即红）+ AST 扫描兜底新调用点（保守规则：任何 `subprocess.*(` 与任何 `Path(a) / var` 组合命中即要求登记），并诚实登记误报率。纯「智能判定」设计在 M5 有返工风险。

### D-7（P3）RESEARCH A4-3 现状断言错误：`--memory` 已存在

`docker_sandbox.py` L389 `--memory={cfg.memory_limit_mb}m`（默认 8192，`DockerSandboxConfig` L317）+ `--shm-size` 在位；RESEARCH §3.1 判「无 `--memory`」不成立。G-7 缺口收窄为 **pids/cpus/label/TTL/137 五项**；M4 的 memory 工作变为「把既有全局配置接入注册表 profile」（非从零新建）。现状表 A4-3 应由 ❌ 改 ⚠️ 半接线。**该错误不推翻设计**（配额/TTL/137 仍需做），但影响诚实口径与 M4 估算。

## 4. 观察项（O 表）

| # | 内容 | 处置 |
|---|---|---|
| O-1 | `hitl/escalation.py` 等既有审批基础设施未纳入 §5 设计考量 | M3 评估复用或声明不兼容 |
| O-2 | `args_summary` 无脱敏规则，敏感参数可能入永久事件 | M3 定义（键名黑名单剔除 / 仅结构形状摘要） |
| O-3 | `sandbox_profiles` 无 gpu 字段；主执行路径无 `--gpus`（L225 为探测命令） | M4 裁决 gpu 是否进 profile |
| O-4 | registry fail-closed 启动范围未裁决（全入口 vs server/MCP/invoker） | M1 裁决（建议：server/MCP/invoker 强制，纯 CLI 延迟加载） |
| O-5 | RESEARCH A4-2 引用 L225 为探测命令而非执行路径 | 引用精度，随 D-7 一并订正 |
| O-6 | M2/M3 集成点未声明（M2 须预留 invoker 接缝） | M2 DESIGN 吸收 |
| O-7 | 顶层 `version: 1` 类型未定义（int vs str） | M1 裁决（建议 int） |
| O-8 | 编号顺延：复核占 P-100，M1..M5 = **P-101..P-105** | 总纲 v1.4l 声明；M1 批设计订正旧编号 |

## 5. 取证矩阵（RULE-6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| 读码 + grep 计数（E1/E3） | V-1..V-6、V-8..V-10、X-7 | **11 项断言 10 项成立、1 项证伪（D-7）** |
| SDK 探针（E2） | V-7 | ✅ 复现 |
| git show / sha256 复算（E1） | V-11/V-12 | ✅ 零代码、digest 零 mismatch |
| 设计对抗推演（E3，12 组：组合矩阵/依赖/语义/可实现性/集成） | X-1..X-12 | **2 项 P2 + 5 项 P3 + 5 项 O** |
| 测试基线（E1） | claim spine 33 passed（零代码变更，无新测试） | ✅ |

## 6. 结论与处置

- **P-099 主线成立**：架构方向（单一真值源 / fail-closed / 事件 digest 化 / Docker 单档 / AST 守卫）、批次拆分与验收映射、八接口冻结均可用；现状断言 11 项中 10 项成立。
- **2 项 P2 须在 M1（P-101）开工前吸收**：D-1（审批组合漏洞——M1 注册表校验加 V-8 规则 + M3 审批门加保险分支）、D-2（jsonschema 依赖矛盾——建议升核心依赖）。**吸收方式**：M1 的 DESIGN 以「设计修正输入」显式引用本报告并落修正；或先出小修正批改 M0 文档（走受控回边）——**建议前者**（避免为改文档而出批，修正随实现落地时验证）。
- **5 项 P3 为对应批次的设计修正输入**：D-3/D-4 → M4；D-5 → M2 前置 spike；D-6 → M5；D-7 现状表订正随 M1 受控回边一并落。
- **编号顺延**：M1..M5 = **P-101..P-105**（总纲 v1.4l 声明）。
- **G4 仍可开工**：D-1/D-2 均为 M1 可吸收的修正输入，不阻塞；若用户偏好「先修设计文档再施工」，则先出 P-101 文档修正小批（T2 两件套先例），M1 顺延 P-102。
- 按 RULE-5 单向权限，复核未改任何实现；探针零残留；登记 P-100（T3：Layer-0 独立异构复核，零代码/零门禁，同型先例 P-097/P-095/P-090）。
