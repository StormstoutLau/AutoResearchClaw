---
id: arc-roadmap-v07-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-master-roadmap, arc-g0b-governance-base-RESEARCH]
upstream: arc-master-roadmap
---

# 调研：总纲 v0.7 纳入 G0b 调研结论

> **Feature**：把 P-017 的 G0b 调研结论写回总纲，修正状态、交付物、A0-1 口径、Q3/Q11 与外锚。
> **状态**：verified（审计完成；仅状态/方案同步，不改 106 计数）
> **Spec 步骤**：Step 1-2

## 1. 目标

1. P-017 的哪些结论必须进入总纲？
2. 哪些内容会改变 G0b 的验收口径，哪些只是补充？
3. 是否影响 G1/G2/G3 的顺序或 106 计数？

## 2. 需要写入的结论

| # | 结论 | 总纲落点 |
|---|---|---|
| C-1 | G0b 调研完成、实施未开始 | G0b 标题与状态注 |
| C-2 | 当前 `pre-commit run --all-files` exit 0，但组成缺 m7/repo/blackbox | G0b 状态注 |
| C-3 | A0-2..A0-5 机制已存在，缺负向用例 | A0 表后注 |
| C-4 | 推荐 S-1/T-1/H-1：迁移 + 根壳；6 必需 + 2 额外 | G0b 状态注与交付物 |
| C-5 | 交付物需加 `spec_map.py`、`blackbox_check.py`、根兼容壳 | G0b 交付物 |
| C-6 | Q3 建议“新文档立即 + 空 grandfather + 90 天过期” | Q3 行 + G0b 决策闸门 |
| C-7 | Q11 调研确认：G0a 四道足够；G0b 补 m7/repo/blackbox + 两额外 | Q11 行 |
| C-8 | 外锚扩展：Spec Kit/OpenSpec/ISO 29148/SonarQube/pre-commit | G0b 外锚 |
| C-9 | §11 增 P-017 依据 | §11 |

## 3. 不改的部分

- 106 条验收计数；A0-1..A0-6 的 ID 不增删。
- G0a → G-1 → G0b → G2 → G3 的顺序。
- G0b 的决策闸门仍是 Q3；P-017 只给建议，不代替用户裁决。
- C 套件成员与 G1/G2/G3 关系。

## 4. 结论

需要一次 **v0.7 状态/方案同步**：版本、G0b 状态、交付物、A0-1 口径、Q3/Q11、外锚、§11；不改路线与计数。

## 5. 未决项

- **U-1 Q3 裁决**：P-017 建议空 grandfather；仍需用户确认。
- **U-2 G0b 实施**：迁移与钩子新增另开批次。
- **U-3 A0 负向用例**：实施批固化。

## 6. 参考文献

1. [P-017 RESEARCH](../arc-g0b-governance-base/RESEARCH.md)
2. [arc-master-roadmap.md](../../arc-master-roadmap.md)
