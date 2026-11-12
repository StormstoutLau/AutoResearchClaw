---
id: arc-spec-gate-strict-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-12
depends: [arc-spec-gate-strict-RESEARCH]
upstream: arc-spec-gate-strict-RESEARCH
---

# 设计：Spec 门禁严格模式（P-082）

> 基于 [RESEARCH.md](RESEARCH.md)。把 G-4（档位词）与 G-3（阈值提前）落为门禁。

## 1. 加固矩阵

| ID | 缺口 | 修法 | 生效面 |
|---|---|---|---|
| FIX-1 | 档位只查「变更 feature 的 owner」 | 新增 `_require_tiers(d, rows)`：对 `d.pids` 中 P≥82 的行要求档位非空；batch / session / batch-registration 三处调用 | P ≥ 82 的声明行 |
| FIX-2 | 阈值 129/137 未覆盖当前批次 | `BATCH_BINDING_MIN_P = 82`、`EVIDENCE_MIN_P = 82`；`DOC_COMPLETENESS_MIN_P` 保持 81 | P ≥ 82 |
| FIX-3 | 本批自证 | session finalize 写 `evidence_digest`（四文档 sha256 文件表） | 本批 |

## 2. 判定

```text
GATE_STRICT_MIN_P = 82
BATCH_BINDING_MIN_P = GATE_STRICT_MIN_P
EVIDENCE_MIN_P = GATE_STRICT_MIN_P

_require_tiers(d, rows):
  for pid in d.pids:
    if pid < 82: continue
    row = rows.get(pid)
    if row is None: continue        # 已由「不在 PROGRESS」报
    if row_tier(row) is None:
      error(f"{pid} 缺批次档位（依据列须含 T1 或 T3）")
```

- 调用点：`_resolve_declared`（batch）、batch-registration 分支、session-progress 分支。
- **不**在 maintenance 分支调用（whitespace-only，无新声明）。
- `_resolve_declared` 内保留 T1 四文档检查；删除重复的「缺档位」分支。

## 3. digest 绑定（FIX-3）

本批 session 的 finalize 必须携带：

```json
"evidence_digest": {"algorithm": "sha256", "files": {"spec/arc-spec-gate-strict/RESEARCH.md": "<hex>", ...}}
```

生成方式：`python scripts/spec/step_enforce.py --doc-digest arc-spec-gate-strict`。
操作顺序（不可颠倒）：**四文档定稿 → stage → 生成 digest → 写 session**；此后不再改四文档。

## 4. 关键决策与被拒绝方案

| # | 决策 | 被拒绝方案 | 拒绝理由 | 代价 |
|---|---|---|---|---|
| D-1 | 档位检查覆盖三模式 | 只查 batch | G-4 要求「PROGRESS 行」而非「含文档改动的 P 行」；纯登记批同样需要档位 | 纯登记批需补 T1/T3 |
| D-2 | 阈值三者统一 82、doc 保持 81 | 全部统一 81 | 81 已生效；82 是本批编号，保持「从引入批次起生效」先例 | 81 与 82 两个边界并存（语义不同） |
| D-3 | digest 立即对 P≥82 生效 | 继续 137，另开批次自证 | 用户裁决「提前到当前批次」；自我适用是最强证据 | 每次 finalize 后改文档需 rebind |
| D-4 | 档位缺失判红 | 默认 T1 | 默认 T1 会让未标注历史行大面积误报；判红给出明确修复 | 需显式标注 |

## 5. 不变式

- I-1 历史 P 行不回溯（只检查 `d.pids`）。
- I-2 T3 轻批合法（档位存在即可，不要求四文档）。
- I-3 既有覆盖/会话/digest 判据不弱化。
- I-4 档位解析仍只在 `spec_map.row_tier`（I-10）。
- I-5 digest 文件集只含本批 feature 的四文档。

## 6. 边界

- **职责外**：档位理由的语义核验；全仓历史 P 行补标。
- **能力边界**：阈值下调后，P≥82 的批次必须走「digest → session」顺序；这是流程成本，不是自动检查能消除的。

## 7. 验收映射

| ID | 验收 |
|---|---|
| FIX-1 | 单测：batch-registration 缺档位红；session 模式缺档位红；P<82 不报 |
| FIX-2 | 单测：常量 = 82；P-082 行 feature 绑定生效 |
| FIX-3 | 本批 pre-commit 通过 `verify_digests`（digest 匹配） |
