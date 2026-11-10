---
id: arc-g1-review-fixes-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1-cross-review-20261110]
upstream: arc-g1-cross-review-20261110
---

# 调研：G1 异基座复审三缺陷的复现与修法边界

> **Feature**：P-040，修复 P-039 登记的 D-1/D-2/D-3。
> **Spec 步骤**：Step 1-2（T1：改 `researchclaw/`、`frontend-legacy/` 与 `tests/`）

## 1. 缺陷复现（一手）

| ID | 复现 | 结果 |
|---|---|---|
| D-1 | 追加 2 条事件后篡改**末行** payload（`payload_sha256` 字段保持原值），再 `verify_chain()` | 返回 `(True, "ok (2 events)")` —— 末行无后继，指针链查不出 |
| D-1b | 同上，并先 `write_summary()` | `summary.chain_tail` 与当前末行哈希**不一致**（篡改事实可证），但全仓无运行时比对方 |
| D-2 | `outbox.mark_started()` | 真实写入 `effect.started`；`EVENT_TYPES`（17 类）与 `api.js` 常量均无此类型 |
| D-3 | SSE/WS 请求不存在的 run | `read_page` → `EventLog.__init__` 执行 `mkdir(parents=True)`，**创建空目录**；SSE 返回 200 后无限空轮询 |

## 2. 修法边界

| 方案 | 评价 |
|---|---|
| **A `verify_chain` 增 payload 摘要校验 + summary 尾闭合；事件类型补登记；流端点预检** | 单点修复，改动集中在 4 个文件；负向用例可红 |
| B 只比对 `chain_tail`，不加 payload 校验 | 只覆盖「summary 当前」场景；中间行仍依赖指针，且 live 中 summary 常落后 → 覆盖不稳 |
| C 让 `EventLog` 变只读、不 mkdir | 影响面大（写入路径也走同一构造器），超出本批 |

**裁决 A**。

## 3. 关键约束

- **summary 落后是合法中间态**：运行中 summary 只在上次收尾时写；尾闭合只能在 `summary.last_seq == 当前末行 seq` 时生效，否则活 run 会被误判篡改。
- **归档后链只能部分校验**：`apply_retention` 删除最老段后 seq 从中间开始，`verify_chain` 会报 gap。本批不改变该行为，登记为观察项 O-1。
- **`effect.started` 是设计内事件**：P-028/P-029 DESIGN 明确规定执行前写它，因此修法是补登记，不是改 outbox 行为。
- **前端常量必须机械化对齐**：此前只有人工 `node --check` 与目测，本批补 Python 侧解析 `api.js` 的对齐用例。

## 4. 未决

- **U-1 运行时自动校验**：`verify_chain` 目前由测试/运维显式调用，不在 resume 热路径。触发 = 需要「启动即验链」时；障碍 = 归档删段会误报 seq gap，需先定义部分校验语义。
- **U-2 末端非 payload 字段在 summary 缺失时不可检**：属链表方向的固有性质，接受。

## 5. 引用

1. 仓内：[P-039 复审](../../docs/arc-g1-cross-review-20261110.md) §3 D-1..D-3。
2. 代码：`researchclaw/runtime/event_log.py:324`、`researchclaw/server/routes/events.py`、`frontend-legacy/src/services/api.js`。
3. 探针：本批 §1 表（末行 payload 篡改、summary 指纹不一致、mkdir 副作用），均为一手执行。
