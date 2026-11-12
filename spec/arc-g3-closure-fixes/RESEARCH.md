---
id: arc-g3-closure-fixes-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g3-closure-review]
upstream: arc-g3-closure-review
---

# 调研文档：G3 收口缺口修复（P-089）

> **Feature**：P-089，P-088 复核的 2 项 P2 + 1 项 P3 修复。
> **Spec 步骤**：Step 1-2。
> **输入**：[P-088 收口复核](../../docs/arc-g3-closure-review-20261113.md)；[M0 §7](../arc-g3-m0-design/DESIGN.md)。

## 1. 调研目标

1. **A3-7**：如何在不改 37 个调用点的前提下做到「每次 LLM 请求记录 prompt_version」，并把版本持久化到 claim 导出？
2. **A3-8**：哪个真实暂停场景可以产出 handback，且不改变既有暂停语义？
3. **A3-6**：如何用最小测试证明「配置变更不撤销已接受 run 的 mandate」？
4. **D-3**：A3-7/A3-8 编号以哪一侧为准？

## 2. 调研方法

| 通道 | 用途 | 结果 |
|---|---|---|
| 仓内读码 | `manager.for_stage`、`LLMClient.chat`、`_write_paper_sections`、Stage 17 阻断分支、`runner` | ✅ 一手定位 |
| P-088 报告 | 缺口原文与证据 | ✅ E1/E2 |

**降级链记录**：缺陷修复批，事实源为仓内代码（E1）与 P-088 探针（E2）；无外部文献。

## 3. 调研发现

| # | 事实 | 位置 | 影响 |
|---|---|---|---|
| R-1 | `for_stage` 已计算并返回 `RenderedPrompt.version` | `prompts/manager.py` | 版本真值已在手，只差请求侧与持久化 |
| R-2 | `LLMClient.chat` 是所有请求的最终入口（含直接调用） | `llm/client.py` L257 | 在此记录可覆盖全部请求 |
| R-3 | `ContextVar` 可按执行上下文传递版本，无需改 37 个调用点 | stdlib | 低侵入 |
| R-4 | `_write_paper_sections` 已调用 `for_stage("paper_draft")`，但只取 `.system` | `_paper_writing.py` L368 | 可顺手取 `.version` |
| R-5 | Stage 17 两个 PAUSED 分支（模拟数据/无指标）是真实暂停场景 | `_paper_writing.py` L1756/L1815 | 适合作为 handback 生产者 |
| R-6 | runner 的 handback 校验逻辑内联在循环中 | `runner.py` | 抽出函数即可单测路由 |
| R-7 | 总纲定义 A3-7=prompt_version、A3-8=StageHandback | `arc-master-roadmap.md` L419-L420 | 以总纲为准，修 P-087 文档 |

## 4. 综合分析

1. **ContextVar + `LLMClient.chat` 单点日志**是覆盖全部请求的最小方案（R-2/R-3）。[★★★★★]
2. **Stage 17 侧车 `claim_prompt_versions.json`** 让 claim 导出携带版本，不改 C4 schema（R-1/R-4）。[★★★★★]
3. **Stage 17 阻断分支产出 handback** 是真实、低风险的 A3-8 生产者（R-5）。[★★★★☆]
4. **抽出 `_apply_handback_guard`** 可单测「越界 → FAILED」路由（R-6）。[★★★★★]
5. **编号以总纲为准**（R-7），P-087 文档需受控回边。[E1]

## 5. 幻觉抑制审查（Step 2 Review）

| 声明 | 来源 | 状态 |
|---|---|---|
| `LLMClient.chat` 是所有请求最终入口 | R-2 读码 | ✅ E1 |
| `ContextVar` 为 stdlib | Python 3.11 文档/运行 | ✅ |
| Stage 17 两分支是真实 PAUSED | R-5 读码 + 既有测试 | ✅ E1 |
| runner 校验逻辑可抽出 | R-6 读码 | ✅ E1 |

## 6. 对设计的输入

- 不改 C4 schema、不改既有错误码。
- 无 sidecar 时 claim_export 保持原样（向后兼容）。
- handback 写入 best-effort；越界仍由 runner 判 FAILED。
- 日志只增不减。

## 7. 参考文献

- P-088 收口复核：`docs/arc-g3-closure-review-20261113.md`。
- M0 治理设计：`spec/arc-g3-m0-design/DESIGN.md` §7。

---

**Review 签字**: 自查（单视角）+ 机械核验 日期: 2026-11-13
