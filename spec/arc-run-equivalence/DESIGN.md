---
id: arc-run-equivalence-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-run-equivalence-RESEARCH]
upstream: null
---

# 设计：重跑等价性对照实验（P-149）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：1 个新模块、`cli.py` 增一个子命令、1 个测试文件。

---

## 1. 决策

| 决策 | 内容 |
|---|---|
| D-1 | 新模块 `researchclaw/evidence/run_equivalence.py`，只读比较两个 run |
| D-2 | 入口 `compare_runs(left_dir, right_dir) -> dict` |
| D-3 | 8 类检查固定执行，`checks == 8` |
| D-4 | 阶段/工具/参数/状态序列按记录顺序比较，重试不单列 |
| D-5 | 产物以 run 相对路径为键、内容哈希为值；目录外退化为 basename |
| D-6 | 任一侧事件链或动作链损坏 → 判不等价，差异单列 |
| D-7 | 空 run fail-closed；目录缺失抛 `FileNotFoundError` |
| D-8 | CLI `runs compare --left --right [--json]`，退出码 0/1/2 |

## 2. API 与报告结构

```python
compare_runs(left_dir, right_dir) -> {
    "equivalent": bool,
    "checks": 8,
    "differences": [{"kind": ..., "left": ..., "right": ...}],
    "left":  {"run_id", "stages", "actions", "artifacts",
              "event_chain_ok", "action_chain_ok"},
    "right": {...},
}
```

`differences` 为空当且仅当 `equivalent is True`。差异类型见 RESEARCH §5。

## 3. 判据实现

| 类别 | 取值 | 易变项处理 |
|---|---|---|
| `stage_sequence` | `stage.completed` 的 stage 号，按事件顺序 | 重试不产生额外 completed，自然折叠 |
| `stage_failures` | `stage.failed` 的 stage 号 | — |
| `tool_sequence` | 账本 `tool` 列表 | 动作 UUID 不参与 |
| `params_sequence` | 账本 `params_sha256` 列表 | 原始参数不落盘 |
| `status_sequence` | 账本 `status` 列表 | 退出码不单列，由 status 承载 |
| `artifacts` | `outputs` 相对化后的路径 → 哈希 | 绝对前缀被剥离 |
| `event_chain` | `verify_chain()` 布尔与消息 | 不比较具体链哈希 |
| `action_chain` | `verify_chain()` 布尔与消息 | 同上 |

## 4. CLI

```
researchclaw runs compare --left <dir> --right <dir> [--json]
```

退出码：0 等价 / 1 有差异 / 2 输入不可用。文本模式逐条打印差异；`artifacts` 差异单独展开为 changed / missing_in_left / missing_in_right。

## 5. 不变式

| 编号 | 不变式 | 测试 |
|---|---|---|
| J-1 | 判定器只读，不修改两个 run 的任何文件 | `test_is_read_only` |
| J-2 | 易变字段不参与判定 | `test_volatile_fields_are_ignored` |
| J-3 | 任一侧链坏即判不等价 | `test_detects_broken_event_chain`、`test_detects_broken_action_chain` |
| J-4 | 空 run fail-closed | `test_empty_runs_fail_closed` |
| J-5 | 目录缺失显式抛错 | `test_missing_run_dir_raises` |
| J-6 | 报告可 JSON 序列化，差异类型稳定 | `test_compare_reports_equivalent`（`json.loads`） |

## 6. Review 记录（Step 6）

- 判定器放在 `evidence/` 而非 `skills/`：它比较 run 事实，不属于技能导出生命周期。
- 不引入第三个「等价阈值」参数：8 类判据全等即等价，避免可调阈值掩盖差异。
- `checks` 固定 8 而非动态计数：空报告也保留判据数量，杜绝零检查假绿。
- 退出码与 `pipeline-skill verify` 对齐（0/1/2），差异态用 1。

## 7. 非目标

真实 LLM 重跑、prompt 重放、自动修复差异、跨机器环境等价、耗时与成本比较、重试次数比较。
