---
id: arc-g4-m3-tool-events-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-13
depends: [arc-g4-m3-tool-events-IMPLEMENTATION]
upstream: arc-g4-m3-tool-events-IMPLEMENTATION
---

# 检查清单：G4-M3 tool 事件 + orphan_call + 审批门（P-104）

## 1. 文档一致性（Step 8）

| # | 检查项 | 状态 | 说明 |
|---|---|---|---|
| DC-1 | RESEARCH 结论进入 DESIGN（D-1..D-7） | ✅ | 决策表挂来源 |
| DC-2 | DESIGN 模块在 IMPLEMENTATION 有对应实施 | ✅ | §1 十二项 ↔ DESIGN §1-§7 |
| DC-3 | IMPLEMENTATION 功能点在 CHECKLIST 有验收 | ✅ | §2/§3 |
| DC-4 | 复核 O-10/O-11 有落点 | ✅ | T-13 / T-14/T-19 |
| DC-5 | 术语一致（invoker / orphan_call / approvals / handlers） | ✅ | |

## 2. 验收项（DoR：前置就绪；DoD：可失败判据）

### 2.1 A4-4 tool 事件

| # | 验收项 | DoR | DoD | 证据 |
|---|---|---|---|---|
| A4-4-a | 成功调用成对 | 注入临时 EventLog | `tool.call` 与 `tool.result` 同 `call_id` | T-1 |
| A4-4-b | 字段完整 | 同上 | M0 §4 字段逐项在位 | T-2 |
| A4-4-c | digest 可复算 | 同上 | JCS sha256 相等 | T-3 |
| A4-4-d | 无原始参数 | 哨兵串 | 事件行不含哨兵值 | T-4 |
| A4-4-e | 缺失即 orphan | 完整调用后删 result | `tool.orphan_call` 出现且 call_id 正确 | T-10 |
| A4-4-f | 无孤立不误报 | 完整日志 | 零 orphan | T-11 |
| A4-4-g | 顺序 | summary 锚点 | orphan seq < summary seq | T-12 |

### 2.2 A4-5 审批门

| # | 验收项 | DoR | DoD | 证据 |
|---|---|---|---|---|
| A4-5-a | high 未审批拒绝 | `risk=high+approval=high_only`，无 approvals | `E_APPROVAL_REQUIRED`、`approval.required` 事件、handler 零副作用、无 `tool.result` | T-5 |
| A4-5-b | 审批放行 | `grant` | handler 执行 | T-6 |
| A4-5-c | 畸形文件 fail-closed | 坏 JSON/结构 | 拒绝 | T-7 |
| A4-5-d | never 放行 | `approval=never` | 执行 | T-8 |
| A4-5-e | always 恒拒 | `approval=always` | 拒绝（即使已 grant？见 T-9 定义：未 grant 时） | T-9 |
| A4-5-f | 并发 grant | 多线程 | 文件始终完整 JSON | T-17 |
| A4-5-g | CLI 端到端 | `approvals grant` | 命令后 gate 放行 | T-18 |

### 2.3 复核前置输入（O-10/O-11）

| # | 验收项 | DoD | 证据 |
|---|---|---|---|
| O-10 | 运行时 schema 校验 | 必填 null/类型错误 → `E_INVALID_ARGUMENTS`，handler 未执行 | T-13 |
| O-11 | 无第二 server | invoker 不构造 server；`dispatch_tool`/`_default_server` 已删 | T-14 |
| O-11b | 生命周期归属 | `stop()` 取消实际任务 | T-19 |

## 3. 测试矩阵（先红）

| # | 用例 | 期望 |
|---|---|---|
| T-1 | 正常调用 | call/result 成对 |
| T-2 | 字段完整性 | M0 §4 字段齐 |
| T-3 | digest | JCS sha256 相等 |
| T-4 | 无原始参数 | 哨兵值不出现 |
| T-5 | 审批拒绝 | `E_APPROVAL_REQUIRED` + 事件 + 零副作用 |
| T-6 | 审批放行 | 执行 |
| T-7 | 畸形 approvals | 拒绝 |
| T-8 | `never` | 执行 |
| T-9 | `always` | 拒绝 |
| T-10 | orphan 负向 | 标记出现 |
| T-11 | orphan 对照 | 零标记 |
| T-12 | 顺序 | orphan < summary |
| T-13 | O-10 | `E_INVALID_ARGUMENTS`，handler 未执行 |
| T-14 | O-11 | 无 `dispatch_tool`/`_default_server`；调用不构造 server |
| T-15 | 回归 | registry 25 + dynamic 12 + MCP 42 零失败；CI 全清单 0 failed |
| T-16 | 不越界 | 不注入 sink → `events.jsonl` 零新增 |
| T-17 | 并发 grant | 文件完整 |
| T-18 | CLI grant | 端到端放行 |
| T-19 | 生命周期 | `stop()` 取消实际任务 |

## 4. 回归与门禁

| # | 检查 | 结果 |
|---|---|---|
| R-1 | 3.13.5 五套件（registry 25 + dynamic 12 + MCP 42 + tool_events 19→**21**） | v1.0 **98 passed** → v1.1 **100 passed** |
| R-2 | 3.11.15 同五套件 | v1.0 **98 passed** → v1.1 **100 passed** |
| R-3 | CI 固定清单 41 文件 | v1.0 **623/13skip** → v1.1 **625/13skip，0 failed** |
| R-4 | wheel 三连（P-103 护栏） | v1.0 431 entries 零重复 |
| R-5 | 门禁链（DC/step-enforce/pre-commit） | 已过（见提交） |

### 4.1 复核收敛验收（v1.1）

复核报告：[arc-g4-m3-review-20261113.md](../../docs/arc-g4-m3-review-20261113.md)（2 P2 + 3 P3 + 7 O）。

| # | 复核发现 | 收敛动作 | 验收 | 状态 |
|---|---|---|---|---|
| D-1 P2 | `handle_tool_call` 直调绕过审批门/校验/事件 | 改为 invoker 薄壳（单执行路径） | T-20：直调 high-risk 未审批 → `E_APPROVAL_REQUIRED` 且零副作用 | ✅ |
| D-2 P2 | 非 JSON 结果 digest `TypeError` 逃逸 + 残留未配对 call | `_to_jsonable` 兜底（`default=str` 同口径） | T-21：`Path` 结果 → 成功返回、call/result 成对 | ✅ |
| D-3/D-4/D-5 P3 | handler 签名 / 事件类型运行时校验 / grant 工具名 | 登记不收敛（CHECKLIST §5 U-6..U-8） | — | 登记 |
| O-6..O-12 | approvals 语义口径 / gz E2 / 双错误码统一等 | 随 D-1 收敛自然消解或登记 | — | 登记 |

## 5. 遗留登记

| # | 项 | 处置 |
|---|---|---|
| U-1 | 全局 MCP 调用审计 sink | G4 后续（CloudTrail 模型） |
| U-2 | `approval.required` 在无 sink 时不写 | DESIGN §5 F-4；随 M0 I-5 回边 |
| U-3 | A4-4 生产无生产者 | DESIGN §5 F-5；注入式测试验证 |
| U-4 | approvals 无 revoke/过期 | 后续 |
| U-5 | listChanged 真通知 | P-103 阻塞点延续 |
| U-6 | handler 签名加载期校验（复核 D-3） | P-104 遗留；M4 可顺带 |
| U-7 | `EventLog.append` 类型运行时校验（复核 D-4） | P-104 遗留 |
| U-8 | `grant` 工具名注册表校验（复核 D-5） | P-104 遗留 |

---
