---
id: arc-stage10-tooling-and-skills-RESEARCH
type: design
version: 0.1
status: draft
date: 2026-11-27
depends: [arc-stage10-generation-budget-contract]
upstream: arc-master-roadmap
---

# 调研（草案）：Stage 10 生成链的外部工具与技能接入（B-35）

> **状态**：**仅登记**。本文件是 B-35 的立项依据与后续分析入口，不是最终方案；DESIGN / IMPLEMENTATION / CHECKLIST 待立项实施时补齐。
> **证据来源**：[postmortem §F-7b.11](../../docs/arc-b-site-stage10-postmortem-20261126.md)（三步现状表 + 三缺口读数）。

## 1. 问题

蓝图规划、实验对齐、方法设计三步目前**无 skill / 无 MCP / 无 tool-calling 循环**，只有静态文本注入。用户判断「仅依靠模型自身推理解决问题不现实」。

## 2. 三条已核缺口

| # | 缺口 | 读数 | 代码锚点 |
|---|---|---|---|
| G-1 | 唯一外部检索在 B 站返回 0 条 | 运行 F：`GitHub API error 401` ×4、`0 repos`；B 站无 `GITHUB_TOKEN`，配置无 `code_search` 键 | [`github_client.py` L65-70](../../researchclaw/agents/code_searcher/github_client.py#L65-L70) |
| G-2 | skills 标注适用 Stage 10 却未进入 CodeAgent | overlay 只在旧单发分支调用（`_code_generation.py` L1195）；CodeAgent 构造无 skills 参数 | [`code_agent.py` L230-254](../../researchclaw/pipeline/code_agent.py#L230-L254)、[`data-loading/SKILL.md`](../../researchclaw/skills/builtin/tooling/data-loading/SKILL.md) |
| G-3 | MCP 方向相反且无工具循环 | `mcp/server.py` 是 ARC 对外暴露 6 工具；`mcp/client.py` 未被管线引用；`LLMClient.chat` 无 `tools=` | [`mcp/server.py`](../../researchclaw/mcp/server.py)、[`client.py` L302-316](../../researchclaw/llm/client.py#L302-L316) |

## 3. 分级处置（待进一步分析）

| 级别 | 动作 | 验收（必须可测量） |
|---|---|---|
| P0 | 配置只读 `GITHUB_TOKEN` | `Code search complete: N repos`，N>0 |
| P1 | skills overlay 接入 CodeAgent（蓝图 + 单文件 prompt） | skill 命中率 / prompt 含 skill 正文 |
| P1 | 对齐门增加 AST 符号表 + 蓝图文件清单等确定性证据 | 判词纠正次数（LLM 否决 → 结构证据支持/推翻） |
| P2 | Stage 4–6 文献/知识摘要注入蓝图；或经 `MCPServerRegistry` 调 `search_literature` | 蓝图 prompt 中可追溯条目数 |
| P3 | CodeAgent 内 tool-calling 循环（sandbox / 检索） | 独立批次设计 |

## 4. 非目标（本文件）

- 不做实现、不做配置变更。
- 不宣称工具一定提升质量：每级都须以可测量指标验证，否则只是 prompt 膨胀。

## 5. 后续分析入口

1. 度量当前蓝图 prompt 的 token 构成（topic / exp_plan / 域 profile / code search / 蓝图本体）。
2. 评估 P0 的真实收益（同一 topic 配 token 前后 code search 命中数）。
3. 评估 P1 的 skill 命中率与对生成结果的影响（对齐门通过率、证据门失败码分布）。
