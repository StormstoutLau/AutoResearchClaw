---
id: arc-roadmap-verdict-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-08
depends: [arc-roadmap-verdict-RESEARCH]
upstream: arc-roadmap-verdict-RESEARCH
---

# 设计：总纲 v0.4 编辑图

> 输入：[RESEARCH.md](RESEARCH.md) §2 的七组改动。本文件给出精确落点与不变量。

## 1. 设计不变量

1. **106 计数不变**：D-2C 只改断言文本与交付物，不增删验收 ID。
2. **成员生效点 = 交付阶段**：§5 全部套件行去掉箭头注记后，生效起点列 = 各成员交付阶段的 max；N/A 规则自动处理分段生效。
3. **声明即真值**：`roadmap_coverage_check.py` 只认 §5 套件行（`| C-*`）与声明段两个来源，§5.1 矩阵不参与覆盖判定。
4. **勘误不改档**：P-004 四文档保持 `verified/accepted` 原样，勘误在本批 IMPLEMENTATION §3 记录。

## 2. 编辑落点（总纲 v0.3 → v0.4）

| # | 节 | 改动 |
|---|---|---|
| E-01 | 头部 | version 0.4；修订块 |
| E-02 | §1 | 最短路径显式最小集（A0a×4 + H×8 + A1-1/2/5 + A2-1/2），N/A 语义 |
| E-03 | §4 G1 | 交付物 +7（A1-5/6/7/9/10/11/12 对应） |
| E-04 | §4 G2 | 交付物 +1（三谓词 + fixture）；A2-4/5/6 改写为谓词断言 |
| E-05 | §4 G3 | 交付物 +4（Stage 22 接线、RunMandate、prompt_version、StageHandback）；A3-1 扩写含 Stage 22 |
| E-06 | §4 G5 | 交付物 +2（SkillPack 校验、read_position） |
| E-07 | §4 G7 | "事件日志轮转/归档"改"跨 run 归档（承接 G1 单 run 滚动）" |
| E-08 | §5 表 | C-1 +A1-6；C-4 生效起点 G4、删箭头；C-7 收缩 FC/FA、G7；C-8 生效起点 G8b、删箭头；C-9 覆盖 H-1..H-5、名称"可信执行（G-1）" |
| E-09 | §5 规则 | 新增"生效点由交付阶段推导 + CI 强制"条 |
| E-10 | §5 声明 | 重写：35 条未归属 + A3-5 有意 N/A + I-1 归属待登记 |
| E-11 | §5.1 | 新增执行矩阵首批 12 条（ID/判定方式/平台/证据落点） |
| E-12 | §6 | 串行约束限定"完整路线"；最小集引用 §1 |
| E-13 | §7 | 标题 17→20；新增 Q18/Q19/Q20 |
| E-14 | §11 | +2 行（复核报告、裁决分析） |
| E-15 | scripts | 新增 `roadmap_coverage_check.py`（只读、零依赖、fail-closed） |
| E-16 | CI | 新增 `roadmap-coverage` job 跑 `--check` |

## 3. 影响面

- **代码**：仅新增 1 个校验脚本 + ci.yml 1 个 job；`researchclaw/` 零改动。
- **计数**：§3 阶段总表 106 条与各段计数（G2 7、G3 17）不变。
- **机检**：覆盖率门禁期望 `accept=106 missing=0`；dc/step/console 照常。
- **回滚**：`git revert` 单提交 + 重跑 `console_gen`；无数据迁移。
