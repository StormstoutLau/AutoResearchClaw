---
id: arc-roadmap-v07-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-roadmap-v07-RESEARCH]
upstream: arc-roadmap-v07-RESEARCH
---

# 设计：总纲 v0.7 编辑图

> 输入：[RESEARCH.md](RESEARCH.md) §2 的 C-1..C-9。

## 1. 不变量

1. **106 计数不变**：不新增/删除验收 ID。
2. **路线不变**：G0a → G-1 → G0b → G2 → G3。
3. **Q3 仍待裁决**：总纲写“P-017 建议”，不写“已裁决”。
4. **只同步 G0b**：不扩散到 G1/G2/G3 的验收。
5. **历史文档不改**：只改总纲与新增 P-018 文档。

## 2. 编辑落点

| # | 节 | 改动 |
|---|---|---|
| E-01 | 头部 | `version: 0.7`、标题 v0.7、新增 v0.7 修订块 |
| E-02 | G0b 标题 | 改“未就绪（调研完成，待实施）” |
| E-03 | G0b 状态注 | 写入 P-017 实测与 S-1/T-1/H-1 |
| E-04 | G0b 交付物 | 加 `spec_map.py`、`blackbox_check.py`、根兼容壳、空 grandfather |
| E-05 | A0 表 | A0-1 明确“必需六 + 两额外”；表后加“机制已存在/负向用例待固化” |
| E-06 | G0b 决策闸门/外锚 | Q3 建议；外锚扩为 Spec Kit/OpenSpec/ISO 29148/SonarQube/pre-commit |
| E-07 | Q3/Q11 | Q3 写 P-017 建议；Q11 写调研确认 |
| E-08 | §11 | 增 P-017 依据行 |

## 3. 影响面

- 文档：`arc-master-roadmap.md` + P-018 四文档/会话。
- 代码：零改动。
- 计数：106 不变；覆盖率 `missing=0`。
- 回滚：单提交 revert；无数据迁移。

## 4. 未决项

沿用 [RESEARCH.md](RESEARCH.md) §5。
