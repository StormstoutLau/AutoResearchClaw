# P-104 对 P-104「G4-M3 tool 事件 + orphan_call + 审批门」的独立异构复核（2026-11-13）

> **性质**：Layer-0 独立异构复核（T3 轻批，零生产代码/零门禁写入）。不采信 [P-104 实施](../spec/arc-g4-m3-tool-events/IMPLEMENTATION.md) 的任何结论，全部一手重验：HEAD `9bb829a` + **22 文件暂存（+1176/−69）**，以 INDEX 为准；五套件复跑、CI 固定清单全量复跑、wheel 独立构建、session digest 逐文件复算、**18 组对抗探针**（临时目录，零仓内残留）。
> **异构性**：实施会话为 **DeepSeek-V4.1-Flash**（`specwf-p104-arc-g4-m3-tool-events.jsonl` model 字段），本复核为 **GLM-5.3-Flash**——RULE-5 交叉成立。
> **编号**：复核**并入 P-104 不占号**（沿用 P-103 先例）；M4=P-105 不变。
> **单向权限**：只标记问题，不改实现；本报告为唯一新增文件。

## 1. 一手复验（V 表）

| # | 声明 | 方式 | 结果 |
|---|---|---|---|
| V-1 | 新增 19 用例 | `pytest tests/test_tool_events.py -q` | ✅ 19 passed |
| V-2 | 五套件 98 passed | 复跑 | ✅ 98 passed（registry 25 + dynamic 12 + MCP 42 + tool_events 19） |
| V-3 | 3.11.15 98 passed | `uv run --python 3.11 --with …` | ✅ 98 passed |
| V-4 | CI 41 文件 623/13skip | 固定清单全量复跑 | ✅ **623 passed / 13 skipped，0 failed** |
| V-5 | wheel 431 entries 零重复 | 独立 `uv build --wheel` + zip 检查 | ✅ 431 / 零重复；invoker/approvals/handlers/registry 均在包内 |
| V-6 | digest | 本地 sha256 复算（CRLF 规范化） | ✅ P-104 8 文件零 mismatch；P-099 rebind 5 文件零 mismatch |
| V-7 | session 追加式 | `--numstat` | ✅ P-104 +5/0、P-099 +2/0 |
| V-8 | 单例已删 | `hasattr` 探针 | ✅ `dispatch_tool`/`_default_server` 均不存在 |

## 2. 对抗探针（X 表实测）

### 2.1 缺陷

| # | 探针 | 实测 | 判定 |
|---|---|---|---|
| X-1/X-2 | 临时 registry `risk=high+approval=high_only`（无 approvals）→ `server.handle_tool_call` 直调 vs `_dispatch_tool` | **直调：`{"success": true}`，handler 已执行**；协议路径：`E_APPROVAL_REQUIRED` | **D-1 P2：公开 API `handle_tool_call` 完全绕过审批门**（O-10 校验与事件同样被绕过）。现有 6 工具 `approval=never` 故生产休眠，但 M0 I-5 语义「未审批 high-risk 零副作用」在直调路径被打破；既有测试全部走直调路径，因此从未暴露 |
| X-4 | handler 返回含 `Path` | `TypeError: Object of type WindowsPath is not JSON serializable` 从 `invoke` 冒出；**事件链残留 `['tool.call']` 无 result** | **D-2 P2：非 JSON 结果（a）异常逃逸 `invoke`（MCP 路径由 SDK 兜成 ToolError，直调路径直接抛）；（b）产生未配对 call，污染 A4-4 不变式**。现有 handler JSON-safe，属错误路径，但 `_digest` 无 `default=str` 兜底是确定性炸点 |
| X-12 | handler 签名 `(args)` 而非 `(server, args)` | strict load 通过；调用期 `TypeError` → `INTERNAL_ERROR` | **D-3 P3：handler 形态在加载期不校验**（V-5b 只证可调用） |
| X-14 | `EventLog.append` 是否校验类型 | 否（`EVENT_TYPES` 无运行时检查） | **D-4 P3：事件类型真值无运行时校验**，新增类型靠文档+测试锁定 |
| X-15 | `grant` 任意工具名 | `{"../../etc/passwd": {...}}` 原样写入 | **D-5 P3：grant 不校验工具名**（仅写文件，无提权面；gate 按注册表查） |

### 2.2 通过项

| # | 探针 | 结果 |
|---|---|---|
| X-3 | sink vs None | ✅ 注入：call/result 成对 1/1；None：**零事件**（不越界写，D-Q1 成立） |
| X-5 | `approvals_path` 目录 vs 文件 | ✅ 目录模式 fail-closed（`E_APPROVAL_REQUIRED`，无误放行；O-7 记录语义歧义） |
| X-6 | `"true"` / `1` 宽松审批值 | ✅ 均拒绝，仅 `is True` 放行 |
| X-7 | `ValueError` vs `RuntimeError` | ✅ `INVALID_ARGUMENT` / `INTERNAL_ERROR` 分流正确 |
| X-8/X-9 | orphan 扫描 | ✅ 标记 1 次且幂等（第二次零新增）。⚠️ gz 分段分支 E2 未触发（探针无 roll 场景），由 `read_all`/`_iter_lines` 读码 E3 佐证 |
| X-10 | summary 锚点顺序 | ✅ T-12 覆盖（orphan seq < summary seq） |
| X-11 | append 失败语义 | ✅ call 阶段失败 → `E_EVENT_LOG_UNAVAILABLE` 且 handler 零执行；result 阶段失败 → handler 已执行、仅告警 |
| X-13 | 生产 `ToolInvoker(` 构造点 | ✅ 仅 `mcp/server.py`，且 `event_log=None` |
| X-16 | CLI 非法输入 | ✅ 坏 run_id / 缺 run_dir 均 exit 2 |

## 3. 缺陷

### D-1（P2）公开 API `handle_tool_call` 绕过审批门与事件层

- **根因**：P-104 只把 invoker 接到 `_dispatch_tool`（MCP 协议路径）；`handle_tool_call` 保留为「unit-test friendly」直调，**不经 schema 校验、审批门、事件**。
- **影响**：① A4-5 在直调路径失效（X-1 实证 high-risk 未审批 handler 已执行）；② O-10 同样失效；③ 直调不产生事件 → orphan 检测覆盖不到该路径的调用。
- **修复建议（供收敛批吸收）**：`handle_tool_call` 改为 `self._invoker.invoke(name, arguments)` 的薄壳（保留 `INVALID_TOOL` 语义与日志），或将方法改名 `_legacy_direct` 并在 DESIGN 声明仅供测试。推荐前者——单执行路径。
- **回归护栏**：X-1 形态固化为用例（直调 high-risk 未审批必须 `E_APPROVAL_REQUIRED`）。

### D-2（P2）非 JSON 结果使 `_digest` 抛 `TypeError`：异常逃逸 + 未配对 call

- **根因**：`canonical_json`（`json.dumps(..., sort_keys, separators)`）无 `default=` 兜底；`tool.result` 的 digest/摘要在 handler 执行**之后**计算。
- **影响**：① handler 已执行但事件链只剩 `tool.call` → run 收尾必产 orphan 标记（误导运维）；② 异常从 `invoke` 冒出，直调方直接崩。
- **修复建议**：`_digest`/`_result_summary` 用 `default=str` 兜底（与 `server._as_result` 的 `json.dumps(..., default=str)` 同口径）；或对 `_emit("tool.result", ...)` 整体 try/except（与现有 `_emit` 一致——当前 `_emit` 已兜，但 **`_digest(result)` 在构造 payload 时调用，位于 `_emit` 之外**，这才是逃逸点）。
- **回归护栏**：X-4 形态固化为用例。

### D-3（P3）handler 签名在加载期不校验
`resolve()` 只证可调用；`partial(fn, self)` 把签名错误推迟到调用期（X-12 → `INTERNAL_ERROR`）。建议 strict 解析时 `inspect.signature` 校验首参可注入（或 handler 形态约定 `(server, args)` 写入 DESIGN）。

### D-4（P3）事件类型无运行时校验
`EventLog.append` 不检查 `event_type ∈ EVENT_TYPES`；`tool.orphan_call` 的「新增类型」真值仅由文档+测试锁定。建议 append 首行加断言或 `if event_type not in EVENT_TYPES: raise`（成本一行，fail-closed 口径一致）。

### D-5（P3）`grant` 不校验工具名
任意字符串（含 `../../` 形态）原样写入 approvals。无提权面（gate 按注册表查），但键应为注册表内工具名或显式通配；建议 grant 时校验 `tool` 在注册表中存在（或至少非路径形态）。

## 4. 观察项（O 表）

| # | 内容 | 处置 |
|---|---|---|
| O-6 | `approvals_path` 参数名指文件、实现取 `.parent`；传目录静默 fail-closed（X-5），DESIGN §3 未写明口径 | DESIGN 补一句「传 `run_dir/approvals.json` 文件路径」 |
| O-7 | X-5 目录模式行为 = 静默拒绝（fail-closed 成立，无误导放行） | 记录 |
| O-8 | gz 分段 orphan 识别由读码 E3 佐证，E2 探针未构造出 roll 场景 | 后续补 E2 |
| O-9 | `handle_tool_call` 与 invoker 双错误码体系（`INVALID_ARGUMENT` vs `E_INVALID_ARGUMENTS`）并存 | 收敛 D-1 后自然统一 |
| O-10 | `grant` 并发写依赖 `.locks/approvals.lock`；T-17 已覆盖 | 记录 |
| O-11 | A4-4 生产可观察性为零（F-5）：X-13 证实唯一构造点 `event_log=None` | 声明充分，按机制验收口径通过 |
| O-12 | `summary_check` 校验不要求 summary 为末事件（orphan/后续事件可安全追加） | 与 P-104 设计假设一致，记录 |

## 5. 取证矩阵（RULE-6）

| 手段 | 覆盖 | 结果 |
|---|---|---|
| pytest（E1） | V-1..V-4 | 19 / 98 / 98 / 623+13skip |
| digest 复算 + numstat（E1） | V-6/V-7 | ✅ 零 mismatch、追加式 |
| wheel 构建（E2） | V-5 | ✅ 431 entries |
| 运行时探针（E2，16 组） | X 全表 | **2 P2 + 3 P3** |
| 读码（E3） | X-8 gz 分支、X-14、D-1 根因、D-2 逃逸点 | ✅ |
| 盲区扫描（E4） | 单例残留、生产构造点、handler 形态、grant 输入 | ✅ |

## 6. 结论与处置

- **主线成立**：A4-4 正负向（成对/orphan/幂等/顺序）、A4-5 正负向（协议路径拒绝/放行/零副作用）、O-10（协议路径）、O-11（单实例 + `stop()` 生命周期）、I-3（哨兵不泄漏）、D-Q1 边界（None 零事件）、fail-closed 全链（畸形审批/宽松值/CLI 输入）均一手复验为真。
- **2 项 P2 不阻塞主线，但须收敛后才能关闭 A4-5**：
  - **D-1**：`handle_tool_call` 绕过审批/校验/事件（公开 API 与协议路径双轨）；
  - **D-2**：非 JSON 结果 digest 崩溃 → 异常逃逸 + 未配对 call。
- **3 项 P3**（D-3/D-4/D-5）+ **O-6..O-12** 登记。
- **P-104 暂不能验收关闭**（同 P-103 先例：主线成立 + P2 待收敛）。建议收敛批沿用「并入 P-104 不占号」模式，修 D-1/D-2 并把 X-1/X-4 形态固化为回归用例，随后 M0 §9 M3 行改「已完成」。
- 按 RULE-5 单向权限，本复核未改任何实现文件；探针与 wheel 产物已清理，工作树仅保留实施方暂存集与本报告。

## 7. 收敛复验（2026-11-13，同一复核子批）

> **范围**：仅复验 D-1/D-2 的关闭主张（实施方 v1.1 修复），不重开主线验收。**方式**：先红（T-20/T-21 **2 failed**）→ 修复 → 绿。

| # | 主张 | 复验方式 | 结果 |
|---|---|---|---|
| V2-1 | D-1 关闭 | T-20：直调 high-risk 未审批 | ✅ `E_APPROVAL_REQUIRED`，handler 零执行——公开 API 与协议路径统一走 invoker |
| V2-2 | D-2 关闭 | T-21：handler 返回 `Path` | ✅ 成功返回、call/result 成对、digest/摘要在位——`TypeError` 不再逃逸 |
| V2-3 | 回归 | 五套件复跑 | ✅ **100 passed**（tool_events 19→21） |
| V2-4 | CI 全清单 | 41 文件复跑 | ✅ **625 passed / 13 skipped，0 failed** |
| V2-5 | 登记 | 读 CHECKLIST §4.1/§5、IMPLEMENTATION §5.1 | ✅ U-6..U-8 登记；读数诚实（含 T-20 测试注入方式留痕） |

### 7.1 结论

- **D-1/D-2（P2）关闭**；A4-5 现在在**两条执行路径**上均成立，A4-4 配对不变式在错误路径保持。
- D-3/D-4/D-5（P3）+ O 表登记（U-6..U-8），不阻塞验收。
- **复核意见：v1.1 收敛后 P-104 验收通过**；A4-4/A4-5 达成（机制验收口径，生产可观察性边界见 DESIGN §5 F-5）。M4（P-105）可开工。
