---
id: arc-belief-revision-propagation-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-belief-revision-propagation-DESIGN]
upstream: arc-belief-revision-propagation-DESIGN
---

# 实施记录：回写/回退与多步传播调研落档

> 本批只写文档，不改代码、不改总纲。E-* 为实际落点，V-* 为可重放验证。

## 1. 落点

| # | 动作 | 落点 |
|---|---|---|
| E-1 | 审计场景 A 的回退链与 7 项缺陷 | [RESEARCH.md](RESEARCH.md) §3.1 |
| E-2 | 审计场景 B 的注入通道与 5 项传播缺口 | RESEARCH §3.2 |
| E-3 | 确认项目内无同类调研，列出最近覆盖 | RESEARCH §3.3 |
| E-4 | 建立 13 项外部锚点（Saga/durable/backjump/provenance/HARKing/living review 等） | RESEARCH §4 |
| E-5 | 评估 `F:\Spec_Workflow\spec\academic-writing-workflow` 复用边界 | RESEARCH §5 |
| E-6 | 给出差距矩阵与 R-1/R-2/R-3 路线建议 | RESEARCH §6 |
| E-7 | 设计 revision log、targets、评审响应表与收敛判据 | [DESIGN.md](DESIGN.md) §2-§4 |
| E-8 | 登记 U-1..U-6 未决项 | RESEARCH §8.2 |

## 2. 验证

```bash
# V1 文档契约
python scripts/dc_validator.py spec/arc-belief-revision-propagation/RESEARCH.md \
  spec/arc-belief-revision-propagation/DESIGN.md \
  spec/arc-belief-revision-propagation/IMPLEMENTATION.md \
  spec/arc-belief-revision-propagation/CHECKLIST.md docs/PROGRESS.md docs/CONSOLE.md

# V2 决策流
python tools/spec_runner/spec_runner.py step-gate \
  --session specwf-p014-arc-belief-revision-propagation \
  --expect research design implement verify finalize

# V3 派生视图
python scripts/console_gen.py --check

# V4 私网/密钥
python scripts/private_config_check.py spec/arc-belief-revision-propagation \
  docs/PROGRESS.md docs/CONSOLE.md

# V5 批次声明
python scripts/step_enforce.py --base HEAD \
  spec/arc-belief-revision-propagation/RESEARCH.md \
  spec/arc-belief-revision-propagation/DESIGN.md \
  spec/arc-belief-revision-propagation/IMPLEMENTATION.md \
  spec/arc-belief-revision-propagation/CHECKLIST.md docs/PROGRESS.md \
  tools/spec_runner/sessions/specwf-p014-arc-belief-revision-propagation.jsonl
```

## 3. 结果（2026-11-10）

- V1：`DC 契约校验通过：6 文件，2 结果，0 违规`（PROGRESS/CONSOLE 无 front-matter，按规则 skip）。
- V2：`step-gate[specwf-p014-arc-belief-revision-propagation]: 决策链一致 pass → exit 0`。
- V3：`CONSOLE.md 与源一致`。
- V4：`private_config_check` exit 0。
- V5：`step-enforce: mode=batch pid=P-014 ... exit 0`。

## 4. 未执行 / 边界

- **R-1 未执行**：checkpoint 回滚、`to_stage` 透传、`revision_log.json`、`revision_targets` 均未写代码。
- **R-2 未执行**：Stage 20 拒绝回退、评审响应表、影响集声明未实现。
- **R-3 明确拒绝**：不引入 Saga/Temporal/DAG 引擎。
- **未修改** `arc-master-roadmap.md`、`runner.py`、`stages.py`、`_analysis.py`、`executor.py`、`cli.py`。
- **未做外部过期实测**：Cochrane 三分类、reference rot/撤稿重检仍是 U-4。
- **未复用外部文档正文**：只引用 `academic-writing-workflow` 的概念与模板，未复制其 400KB RESEARCH。
