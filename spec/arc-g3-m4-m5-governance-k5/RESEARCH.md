---
id: arc-g3-m4-m5-governance-k5-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g3-m0-design-DESIGN]
upstream: arc-g3-m0-design-DESIGN
---

# 调研文档：G3 M4+M5 合并批（治理 / K5 / retrieval）

> **Feature**：P-087（按用户裁决将 M4 与 M5 合并为单批）。
> **Spec 步骤**：Step 1-2。
> **输入**：M0 设计冻结 [DESIGN §7/§8/§9](../arc-g3-m0-design/DESIGN.md)；P-086 复审 [报告](../../docs/arc-g3-m3-claim-fixes-review-20261112.md)。

## 1. 调研目标

1. **M4 三个对象的落点**：RunMandate、StageHandback、prompt_version 在现有 runner/prompt 结构中各接到哪里？
2. **M5 两个对象的取数**：`tb:`/`paper:` 的解析源是什么？Stage 22/23 的阻断点在哪？
3. **不破坏既有语义**：如何在零回归前提下加入治理与 K5 严格检查？

## 2. 调研方法

### 2.1 通道与降级链

| 通道 | 用途 | 结果 |
|---|---|---|
| 仓内读码（`Read`/`Grep`） | runner、prompt manager、KB、references.bib、Stage 22/23 | ✅ 一手定位 |
| P-086 复审（E1/E2） | 上一批回归基线 | ✅ 401 项回归可复用 |

**降级链记录**：本批为 Layer-1 实现，事实源为仓内代码（E1）与既有测试；未引入外部文献。

### 2.2 范围

- 时间：P-083..P-086 之后。
- 排除：外部锚点/签名（G7）、工具注册表（G4）。

## 3. 调研发现（读码，E1）

| # | 事实 | 位置 | 影响 |
|---|---|---|---|
| R-1 | 无 `runtime/mandate.py`；`execute_pipeline` 是唯一阶段循环入口，run_dir 由调用方传入 | [`runner.py`](../../researchclaw/pipeline/runner.py) | mandate 在循环前写一次最自然 |
| R-2 | `_runtime_begin` 返回 `owns`，嵌套 PIVOT/REFINE 复用同一 run_dir | `runner.py` | mandate 必须幂等、不可覆盖 |
| R-3 | 既有 `PAUSED` 结果来自循环护栏、模拟数据阻断等；无 handback 生产者 | `runner.py`、`_paper_writing.py` | handback 校验只能「有文件才校验」，不能强制所有暂停都写 |
| R-4 | `PromptManager.for_stage` 统一渲染 system/user；无版本属性；`export_yaml` 硬编码 `"1.0"` | [`prompts/manager.py`](../../researchclaw/prompts/manager.py) | 版本应在渲染点计算并随 `RenderedPrompt` 返回 |
| R-5 | KB 条目落在 `<root>/<category>/<entry_id>.md` | [`knowledge/base.py`](../../researchclaw/knowledge/base.py) | `tb:<entry_id>` 可按文件名 stem 解析 |
| R-6 | `references.bib` 由 `parse_bibtex_entries` 解析，条目含 `key` | [`literature/verify.py`](../../researchclaw/literature/verify.py) | `paper:<key>` 可用 BibTeX key 解析 |
| R-7 | `retrieval_status.json` 由 Stage 4 写入 stage-04 | [`_literature.py`](../../researchclaw/pipeline/stage_impls/_literature.py) | summary 与 Stage 22 均可读取 |
| R-8 | Stage 22 有多个早退分支；Stage 23 在 no-bib 分支前有独立流程 | [`_review_publish.py`](../../researchclaw/pipeline/stage_impls/_review_publish.py) | K5 检查必须放在早退之前，且写入报告 |

## 4. 综合分析

1. **mandate 的幂等写入**是唯一不破坏嵌套执行的方案（R-1/R-2）。[★★★★★]
2. **handback 采用「文件存在才校验」**，不改变既有暂停语义（R-3）。[★★★★☆]
3. **prompt 版本在渲染点计算**可覆盖所有阶段，无需改 37 个调用点（R-4）。[★★★★★]
4. **K5 解析源稳定**：KB 文件名 stem + BibTeX key（R-5/R-6）；语法需处理句末标点。[★★★★☆]
5. **retrieval 有稳定取数**（R-7），可在 summary 与论文注记两处显式化。[★★★★★]

## 5. 幻觉抑制审查（Step 2 Review）

| 声明 | 来源 | 状态 |
|---|---|---|
| runner 为唯一阶段循环入口 | R-1 读码 | ✅ E1 |
| 嵌套执行复用 run_dir | R-2 读码 | ✅ E1 |
| PromptManager 无版本属性 | R-4 读码 | ✅ E1 |
| KB 条目文件名即 entry_id | R-5 读码 | ✅ E1 |
| BibTeX 条目含 key | R-6 读码 | ✅ E1 |
| Stage 4 写 retrieval_status.json | R-7 读码 + 既有测试 | ✅ E1 |

## 6. 对设计的输入

### 6.1 约束

- 不改 C4/AR/claim 判定；不新增门禁脚本。
- mandate/handback 失败不得使 run 失败（治理写入 best-effort；handback 越界除外）。
- K5 默认严格：Stage 22 预检 + Stage 23 终检均阻断；检查内部失败也阻断（fail-closed）。
- retrieval 不阻断，但必须显式（summary 字段 + 论文注记 + 报告文件）。

### 6.2 未决项

- **U-1 handback 生产者**：当前无阶段写 handback；校验仅在文件存在时生效。触发：首个 handback 场景。
- **U-2 prompt 请求日志**：版本写入 `logger.info`（渲染点），无独立请求日志文件。触发：需要逐请求审计时。
- **U-3 tb 解析性能**：`rglob` 全树扫描；KB 规模大时需索引。触发：KB 文件数 > 10k。

## 7. 参考文献

- M0 设计冻结：`spec/arc-g3-m0-design/DESIGN.md` §7/§8/§9。
- P-086 复审：`docs/arc-g3-m3-claim-fixes-review-20261112.md`。

---

**Review 签字**: 自查（单视角）+ 机械核验 日期: 2026-11-13
