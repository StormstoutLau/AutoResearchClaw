---
id: arc-roadmap-fix-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-06
depends: [arc-roadmap-review-20261106]
upstream: arc-roadmap-review-20261106
---

# 调研：总纲审查结论的修复范围界定

> **审查来源**：[docs/arc-roadmap-review-20261106.md](../../docs/arc-roadmap-review-20261106.md)（P-002，`verified`，证据绑定 v0.1 / `7d0e70a`）。
> **本批目标**：只修"会让验收判据失真或让门禁自相矛盾"的项；不改阶段划分、不改 106 条计数。

## 1. 纳入范围的项

| 原编号 | 问题 | 本批处置 |
|---|---|---|
| P1-01 | L296 称「H-4 已落地」，与 L165 待做项矛盾 | 改措辞为「待 G-1 的 H-4 落地」，并声明未落地前 A3-5 记 `N/A` |
| P1-02 | §5 C 套件未覆盖 H-1..H-4，G-1 无回归闸门 | 新增 C-9，并为全部 C 套件加「生效起点」 |
| P3-03 | C-3 漏 A3-5、C-4 漏 A1-8、C-5 漏 A0a-4 | 随 C-9 与「生效起点」一并订正 |
| P2-07 | A2-3「65 项 verdict 测试」口径不可复现 | 重定为可冻结口径，不沿用 65 或 77 |
| P3-01 | §7 标题「10 项」实为 Q1–Q16 | 改标题为 16 项 |
| P3-02 | Q11/§10 写「3 道钩子」，实际已装 4 道 | 改为 4 道并列出名称 |

## 2. 三处范围再裁决

### 2.1 P1-02：新增 C-9，而不是把 H-1..H-4 塞进 C-3/C-4

- 事实一：[§5](../../arc-master-roadmap.md) 的规则是「每阶段结束必须全绿」。
- 事实二：阶段顺序是 `G0a → G-1 → G0b`，即 **G0a 结束早于 G-1 交付**。
- 推论：若按审查报告 §6 直接把 H-1/H-2 写进 C-3，G0a 出口时 C-3 必然为红——「全绿」在数学上不可满足，门禁变成死锁。
- 事实三：H-3（死代码调用点）、H-4（降级标记）属于**数据正确性**，不在 C-4「边界、配额与密钥」的主题内。
- 结论：新增 **C-9「可信执行」** 承载 H-1..H-4；同时给所有套件加「生效起点」，成员未落地记 `N/A` 不计红。

### 2.2 P2-01：剔除出本批交付物

- 涉及的 3 个文件（`academic-reasoning-base-fusion.md`、`clawsgo-research-orchestration-landscape.md`、`orchestration-capability-matrix.md`）均在 `.gitignore` 内、**已脱离跟踪**。
- 改动不会进入提交、CI 与门禁均不可见；`dc_validator` 本身也不校验 `depends` 可解析性（即 P3-06）。
- 结论：修它只会制造"已修复"的错觉。本批不修，登记为本地维护备注。

### 2.3 P2-07：不把 65 改成 77

- 复核命令：统计含 `verdict` 的 4 个测试文件中的 `def test_`，合计 **77**。
- 但分布是 `tests/e2e_real_llm.py` 0、`tests/test_code_agent.py` 28、`tests/test_rc_prompts.py` 35、`tests/test_tournament_engine.py` 14——这些文件只是**出现了 verdict 这个词**，与"判定内核"无关。
- 推论：把 65 换成 77 会把一个错误的口径固化下来，比原来的错误更难发现。
- 结论：改为**可冻结口径**——G2 开工时用 `pytest --collect-only` 冻结用例清单与数量；冻结前该项记 `N/A`。

## 3. 明确不修的项

- P2-02..P2-06、P2-08..P2-10：留待对应阶段 `RESEARCH.md` 登记（不改本版正文）。
- `A2-2..A2-7`、`A4-1/A4-4/A4-5/A4-6/A4-10`、`A5-6`、`GQ-1..GQ-5`、`OB-1..OB-5` 的 C 套件归属：本版只做范围声明，不补齐。
- 106 条验收数量、12 阶段、依赖拓扑：不变。
- **总纲纳入版本控制**（2026-11-06 用户裁决，取代本文初稿的"只改本地副本"）：从 `.gitignore` 移除 `/arc-master-roadmap.md` 并随本批提交；其余调研文档仍保持"不入库"。
- 已发现但不在本批处理的归档缺陷：P-002 `CHECKLIST.md` §2 写「裸跑 `dc_validator` 退出码 0」，实测为 **141 条违规**（P1=59 / P2=82，全部来自 `.claude/`、`external/`、第三方 `SKILL.md` 的 front-matter 与 `SPEC_PROCESS.md` 的历史链接）。本批不改 P-002 归档件，登记为待办。

## 4. 环境

Windows 11 / PowerShell / Python 3.13.5；仓库 HEAD `7d0e70a`（父 `3e82bf0` = `origin/main`）。本批为纯文档修改，无运行时依赖。
