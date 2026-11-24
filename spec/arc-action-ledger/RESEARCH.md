---
id: arc-action-ledger-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-science-workbench-reuse-RESEARCH, arc-g1-readiness-research-DESIGN]
upstream: null
---

# 调研：动作级证据账本（P-143）

> **Feature**：P-143。承接 P-140 §4 的 P0-1「统一证据/动作账本」，本批只做账本本体与一个生产者，不做查询 CLI。
> **性质**：T1 实施批；新增 1 个运行时模块、1 个测试文件，修改 1 个既有模块。
> **结论先行**：① 现有 `events.jsonl` 记录的是「观察」而非「动作」，缺少参数、环境、种子、产物哈希与审批人；② 独立 `actions.jsonl` 比把动作塞进事件流更干净，且可复用事件链的 canonical JSON 与哈希约定；③ 以 `ToolInvoker` 作为唯一生产者，避免死代码。

## 1. 问题

| 维度 | `events.jsonl` 现状 | 动作账本需要 |
|---|---|---|
| 记录对象 | 运行/阶段/工具调用的观察点 | 一次具体执行动作 |
| 参数 | `args_digest` + 键名摘要 | 参数哈希（可校验，不落明文） |
| 环境 | 无 | `env`（如 `CUDA_VISIBLE_DEVICES`） |
| 随机性 | 无 | `seed` |
| 产物 | 事件 payload 里的摘要 | 输入/输出文件的 `sha256:<hex>` |
| 审批 | `approval.required` 事件 | 审批人身份（`approvals.json` 的 `by`） |
| 关联 | 自身 seq | 同时记录 `tool.call` / `tool.result` 的 seq |

P-140 §4 的 P0-1 要求「工具、参数、环境、随机种子、输入/输出产物哈希、审批人」六项齐备，现有事件流只能覆盖其中两项。

## 2. 现有接缝

| 接缝 | 可复用点 |
|---|---|
| `runtime/event_log.py` | `canonical_json`、sha256、seq 单调、`prev_sha256` 链式校验的实现范式 |
| `tools/invoker.py` | 已有 `tool.call` / `tool.result` 配对、`call_id`、审批门禁 |
| `tools/approvals.py` | `approvals.json` 的 `by` 字段即审批人 |
| `evidence/artifact_node.py` | `sha256:<hex>` 内容寻址约定 |

## 3. 方案空间

| 方案 | 内容 | 判断 |
|---|---|---|
| A（采用） | 独立 `actions.jsonl`，链式哈希，`ToolInvoker` 为生产者 | 观察与动作分离；可独立离线校验；改动面最小 |
| B | 把动作字段塞进 `tool.call` payload | 事件类型最小集被破坏；观察与动作语义混杂；单行体积不可控 |
| C | 只扩 `artifact_node` 的 DAG | 有产物血统但无动作语义（参数/种子/审批） |
| D | 先做 CLI 查询与时间线 | 超出「只做账本」范围；账本本体未稳定前做视图会返工 |

## 4. 范围边界

- 做：账本模块、链式校验、`ToolInvoker` 生产者、单元与集成测试。
- 不做：CLI 查询、dashboard 时间线、跨 run 聚合、事件 schema 迁移、Python/R 持久内核。
- 非目标：替代 `events.jsonl`；两者互补，账本只回答「做了什么」。

## 5. 结论

- 采用方案 A；`actions.jsonl` 与 `events.jsonl` 同目录、同 run 生命周期。
- 生产者只接入 `ToolInvoker`，不触碰 23 个阶段。
- 账本写入失败不阻断已完成的工具执行（与 `tool.result` 的告警策略一致），但失败会被记录日志。
