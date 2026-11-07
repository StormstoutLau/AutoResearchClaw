---
id: arc-roadmap-verdict-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-08
depends: [arc-roadmap-gaps-DESIGN, arc-roadmap-gaps-review-20261107, arc-d1-d2-verdict-analysis-20261108]
upstream: arc-d1-d2-verdict-analysis-20261108
---

# 调研：D-1/D-2 裁决依据确认

> **裁决输入**：[P-004 DESIGN §3](../../spec/arc-roadmap-gaps/DESIGN.md) D-1/D-2；[复核报告](../../docs/arc-roadmap-gaps-review-20261107.md) F-1/F-2；[裁决分析](../../docs/arc-d1-d2-verdict-analysis-20261108.md)（三方案 × 七维 + 9 项锚点）。
> **用户裁决（2026-11-08）**：**D-1 = A**（H-5 移入 C-9）、**D-2 = C**（A2-4/5/6 纯函数化），并授权 D-3..D-7 与复核 F-1..F-8 同批落地。

## 1. 裁决要点（来自分析文档，此处只记录结论）

| 项 | 裁决 | 决定性理由 |
|---|---|---|
| D-1 | A | 生效点=交付阶段成为可推导不变量；方案 C 把箭头歧义固化为制度（复核 F-2）；E-1/E-3/E-6 支撑门禁在交付边界生效 |
| D-2 | C | 与 §1 最小集/§5 声明/106 计数零扰动；判据回归 ClaimRecord 语义（ISO 12207 V&V 层级）；顺带闭环 Stage 22 无归属；方案 A 因"阶段出口 N/A"门禁侵蚀否决 |

## 2. 本批纳入范围

| 来源 | 项 | 本批处置 |
|---|---|---|
| 裁决 D-1 | H-5 → C-9；C-7 收缩；删箭头 | 总纲 §5 |
| 裁决 D-2 | A2-4/5/6 谓词化；G2 交付物 +1；A3-1 扩写；G3 交付物 +Stage 22 等 | 总纲 §4 |
| P-004 D-3 | 验收执行矩阵首批（G0a+G-1 共 **12 条**，修正复核 F-1 的 18 计数） | 总纲 §5.1 |
| P-004 D-4 | 最小集显式定义（A0a×4 + H×8 + A1-1/2/5 + A2-1/2） | 总纲 §1/§6 |
| P-004 D-5 | G1 +7、G3 +4、G5 +2 交付物；G7 归档措辞去重 | 总纲 §4 |
| P-004 D-6 | 覆盖声明补全 + `roadmap_coverage_check.py` + CI job | 总纲 §5 + scripts + ci.yml |
| P-004 D-7 | Q18（vendor/语料 pin）、Q19（API 认证）、Q20（预算统一） | 总纲 §7 |
| 复核 F-1..F-8 | F-1/F-2/F-3/F-8 随 D-3/D-1/D-6 落地；F-4/F-5/F-6/F-7 记勘误 | IMPLEMENTATION §3 |

## 3. 不做

- 不改 106 计数、12 阶段、依赖拓扑（D-2C 的零扰动保证）。
- 不修改 P-004 归档文档（勘误记录于本批 IMPLEMENTATION，沿用 P-002 先例）。
- 不统一预算字段的代码（Q20 裁决前不动 `researchclaw` 配置）。
