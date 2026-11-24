---
id: arc-node-equivalence-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-node-equivalence-RESEARCH]
upstream: null
---

# 设计：产物节点等价性与 summary digest（P-150）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：`run_equivalence.py` 扩展 + 测试扩展；CLI 与签名不变。

---

## 1. 决策

| 决策 | 内容 |
|---|---|
| D-1 | 产物投影保持单一来源：账本有动作 → `ledger`；无动作 → `node_index`；皆无 → `none` |
| D-2 | 节点索引复用 `artifact_node.load_nodes`，投影为 `locator → content_hash`，同 locator 后写覆盖 |
| D-3 | 新增第 9 类检查 `run_summary`：比较 `pipeline_summary.json` 的 canonical digest |
| D-4 | `checks` 固定为 9；差异类型新增 `run_summary` |
| D-5 | 报告 `left`/`right` 增加 `artifacts_source` 与 `summary_digest`，其余字段不变 |
| D-6 | 节点索引或 summary 解析失败 → `ValueError`，CLI exit 2（fail-closed） |
| D-7 | 账本非空但 `outputs` 为空时不回退，仍标 `ledger` |
| D-8 | CLI 命令与退出码不变（0 等价 / 1 差异 / 2 输入不可用） |

## 2. API 与报告结构

```python
compare_runs(left_dir, right_dir) -> {
    "equivalent": bool,
    "checks": 9,
    "differences": [{"kind": ..., "left": ..., "right": ...}],
    "left":  {"run_id", "stages", "actions", "artifacts", "artifacts_source",
              "summary_digest", "event_chain_ok", "action_chain_ok"},
    "right": {...},
}
```

`run_summary` 差异形如：

```json
{"kind": "run_summary",
 "left": "sha256:40c6bd70...",
 "right": "sha256:02fbc377..."}
```

一侧缺失时对应值为 `null`。

## 3. 判据实现

| # | 类别 | 来源 | 本批变化 |
|---|---|---|---|
| 1-5 | 阶段/失败/工具/参数/状态序列 | 事件与账本 | 不变 |
| 6 | `artifacts` | 账本 `outputs`，无动作时 `artifacts/nodes.jsonl` | **新增回退** |
| 7-8 | `event_chain` / `action_chain` | 两个 `verify_chain` | 不变 |
| 9 | `run_summary` | `pipeline_summary.json` canonical digest | **新增** |

节点索引投影规则：`locator` 保持索引中的原值（已为 run 相对路径）；同一 `locator` 多行时按文件顺序后写覆盖；无 `locator`/`content_hash` 的行不可能通过 `load_nodes`（缺字段直接报错）。

## 4. CLI

命令、参数、退出码均不变。JSON 报告新增两个摘要字段，文本模式仍只打印判定与差异。

## 5. 不变式

| 编号 | 不变式 | 测试 |
|---|---|---|
| J-1 | 判定器只读 | `test_is_read_only` |
| J-2 | 账本非空时节点索引不参与 | `test_ledger_preferred_over_node_index` |
| J-3 | 账本为空时节点索引差异可被识别 | `test_node_index_fallback_detects_change` |
| J-4 | 节点索引相同则判等价（回退可用） | `test_node_index_fallback_equivalent` |
| J-5 | summary 差异或单侧缺失即判不等价 | `test_detects_summary_difference`、`test_detects_missing_summary` |
| J-6 | 损坏的索引/summary 显式抛错 | `test_malformed_node_index_raises`、`test_malformed_summary_raises` |

`checks` 固定 9 由 `test_identical_runs_are_equivalent` 断言。

## 6. Review 记录（Step 6）

- 复用 `load_nodes` 与 `summary_digest`，不复制 schema 与哈希规则，避免两套实现漂移。
- 不把节点索引与账本合并：冲突无法裁定，静默覆盖会制造新的假绿。
- `run_summary` 作为独立差异类型，而不是塞进 `artifacts`：summary 是整体指纹，定位粒度不同。
- `checks` 8→9 是公开契约变更，在 RESEARCH §4 与 PROGRESS 显式记录。

## 7. 非目标

真实 LLM 再跑、目录全量扫描、节点树完整性校验（`verify_tree` 职责）、差异自动修复、summary 内容级 diff。
