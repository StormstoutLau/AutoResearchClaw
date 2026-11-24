---
id: arc-reuse-verify-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-reuse-verify-RESEARCH, arc-pipeline-skill-DESIGN]
upstream: null
---

# 设计：账本查询 CLI 与复现性校验（P-147）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：1 个新模块、2 个既有文件最小接入（`action_ledger.py` 加纯函数、`cli.py` 加两条命令）、1 个测试文件。

---

## 1. 决策

| 决策 | 内容 | 依据 |
|---|---|---|
| D-1 | 新模块 `researchclaw/skills/reproducibility.py`：`verify_reproducibility(manifest, run_dir)` | RESEARCH §4 方案 A |
| D-2 | `query_actions(run_dir, *, tool=None, status=None, limit=None)` 加入 `action_ledger.py` | R1；账本域归账本模块 |
| D-3 | CLI 命令 `actions` 与 `pipeline-skill`，接入既有分发链 | R4；`audit` 范式 |
| D-4 | 校验四项：产物哈希、动作归属、事件链、readpoint | R3 |
| D-5 | 退出码 0/1/2，语义同 `audit` | R4 |
| D-6 | 全程只读 | R5 |
| D-7 | 不实现重执行；U-1 登记 | RESEARCH §2 |

## 2. API

```python
# researchclaw/runtime/action_ledger.py（新增纯函数）
query_actions(run_dir, *, tool=None, status=None, limit=None) -> list[dict]

# researchclaw/skills/reproducibility.py（新模块）
verify_reproducibility(manifest, run_dir) -> dict
# {"reproducible": bool, "checks": [...], "missing_outputs": [...],
#  "hash_mismatches": [...], "unresolved_actions": [...], "chain_ok": bool,
#  "readpoint_failures": [...]}
```

## 3. CLI 形态

```
researchclaw actions --run-dir <dir> [--tool <t>] [--status <s>] [--limit <n>] [--json]
researchclaw pipeline-skill verify --skill-dir <dir> --run-dir <dir> [--json]
```

- `actions`：默认人读摘要（seq、tool、status、approver、inputs/outputs 计数）；`--json` 输出全量记录。
- `pipeline-skill verify`：先 `load_pipeline_skill`（复用 P-146 的 fail-closed 校验），再逐项核对。
- 退出码：0 复现 / 1 有差异 / 2 输入不可用（目录不存在、manifest 加载失败、账本不可读）。

## 4. 校验语义

| 检查 | 判定 | 失败归类 |
|---|---|---|
| `stages[].outputs` 的文件存在且 `hash_path` 一致 | 每个文件一项 | `missing_outputs` / `hash_mismatches` |
| `stages[].actions` 的 `action_id` 在账本中 | 每个动作一项 | `unresolved_actions` |
| `EventLog.verify_chain()` | 整体一项 | `chain_ok=false` |
| `readpoints[].digest` 与现文件一致 | 每个 readpoint 一项 | `readpoint_failures` |
| 无限定的空 manifest（无 stages） | 判为不可复现（空路径无可验证成功） | `checks` 为空 |

`reproducible = chain_ok and all lists empty and checks non-empty`。

## 5. 不变式

| 编号 | 不变式 | 测试 |
|---|---|---|
| J-1 | 校验只读，不写任何文件 | `test_verify_is_read_only` |
| J-2 | 产物被篡改 → 不可复现且指出具体文件 | `test_verify_detects_hash_mismatch` |
| J-3 | 动作缺失 → 不可复现且指出 action_id | `test_verify_detects_unresolved_action` |
| J-4 | 事件链坏 → 不可复现 | `test_verify_detects_broken_chain` |
| J-5 | 完整成功 run → `reproducible=true` | `test_verify_passes_on_intact_run` |
| J-6 | `actions` 过滤正确且 `--json` 机读 | `test_actions_cli_filters` |

## 6. Review 记录（Step 6）

- API 复核：`verify_reproducibility` 输入是已加载的 manifest dict（非路径），避免校验逻辑二次耦合。
- 退出码复核：`audit` 用 1 表示「业务差异」、2 表示「输入不可用」；本批对齐，`manifest 加载失败`归 2 而非 1。
- 边界复核：空 manifest 显式判不可复现，防止「零检查 = 通过」的假绿。
- 修正一处：初稿把 `query_actions` 放进新模块，违反账本域归属；移入 `action_ledger.py`。

## 7. 兼容性

- `action_ledger.py` 只增函数；`ActionLedger` 类零改动。
- `cli.py` 增两个子命令与两个分发分支；`--help` 黑盒冒烟不受影响。
- 无新依赖。

## 8. 非目标

- 重执行（U-1 / P-148 候选）、聚合统计、跨 run 查询、表格美化、shell 补全。
