---
id: arc-stage10-repair-minimal-edit-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-blueprint-integrity, arc-stage10-symbol-recheck]
upstream: arc-master-roadmap
---

# 调研：Stage 10 修复的作用域与最小改动（P-231）

> **档位**：S2 探索型（§2.3）。既有两条修复路径的目标互相抵消，且截断与过度编辑两条失效模式需要外部工程实践对照。

## 1. 问题

运行 O（B 站，P-230 快照）两个 attempt 都在同一处失败：

```
21:06:55 Stage 10: entrypoint contract unmet (missing __main__ block; never prints METRIC_DEF)
21:13:30 Stage 10: entrypoint generated on attempt 1 (7227 chars)
21:13:30 Stage 10: symbol contract broken after late rewrite:
          data.py: DataPipeline; main.py: ExperimentRunner, compute_detection_metrics
21:35:24 Stage 10 repair: ignoring main.py that breaks the entrypoint contract
21:37:44 Stage 10: symbol contract broken after late rewrite:
          main.py: ExperimentRunner, compute_detection_metrics, main
```

同一 attempt 里两个契约轮流被破坏：入口重生成修好 guard/METRIC_DEF，同时丢掉蓝图声明的符号；符号修复又交回一个没有 guard 的 main.py。

## 2. 本地事实

| # | 事实 | 锚点 |
|---|---|---|
| L-1 | 模块生成阶段产出的 main.py 是 362 行、符号齐全（无 `still missing` 记录） | 现场日志 `p230-stage10.log#L223` |
| L-2 | 入口 prompt 只列「其他模块」的名字，不列蓝图给 main.py 的符号；且规则 4/5 要求「thin driver、≤150 行」 | [entrypoint_contract.py#L171](../../researchclaw/pipeline/entrypoint_contract.py#L171) |
| L-3 | 修复 prompt 要求 `Output ALL files`；5 文件约 60 KB 输出 | [code_agent.py#L1704](../../researchclaw/pipeline/code_agent.py#L1704) |
| L-4 | 修复 prompt 的「蓝图」只是前 4 000 字符；实测 54 KB 蓝图前 4 000 字符全是 config.py，`main.py` 不出现 | [code_agent.py#L1694](../../researchclaw/pipeline/code_agent.py#L1694) |
| L-5 | 符号修复一次请求贴出所有受影响文件、要求回完整文件；截断只升级一次后不再区分 | [\_code_generation.py#L370](../../researchclaw/pipeline/stage_impls/_code_generation.py#L370) |
| L-6 | 对齐重生成写入后只查符号、不查入口契约，101 行空壳就是这样落盘的 | [\_code_generation.py#L2300](../../researchclaw/pipeline/stage_impls/_code_generation.py#L2300) |
| L-7 | `_extract_multi_file_blocks` 会把单文件回复改名为 `main.py`，按文件名取回时拿不到 | [\_helpers.py#L705](../../researchclaw/pipeline/_helpers.py#L705) |

## 2.3 档位与最小来源

- **档位**：S2。两条失效模式（多文件整写截断、过度编辑回滚）都有外部实证可对照。
- **外部来源**：12 条，其中 T1 六条（aider 官方文档 ×3、Claude Code 工具文档、OpenAI Codex `apply_patch` 提示词原文、Python Packaging 指南），T1 论文四篇（arXiv 2609.04061 / 2611.34875 / 2601.19106、Agentless FSE 2025），T2 一条（aider 博客），T3 两条（Claude Code 源码笔记、LLM API 错误手册）。
- **降级链**：MCP 学术检索（本轮未用，直接命中 arXiv）→ WebSearch → 运行 O 现场日志 → 仓内代码。

## 3. 外部结论（与方案强相关）

| 结论 | 来源层 | 对方案的约束 |
|---|---|---|
| 生产级 Agent 走「定位 → 最小编辑 → 写前预校验」，不整仓重写 | T1（Codex apply_patch 提示词、Claude Code `Edit` 文档） | 入口修复应打补丁而非重生成 |
| `whole` 格式在单文件装得下时最可靠，成本与截断随文件数线性增长 | T1（aider 编辑格式文档与基准） | 保留整文件格式，但一次只回一个文件 |
| 符号/签名地图（repo map）注入是标准做法 | T1（aider repo map 文档） | 修复 prompt 用结构化符号契约，替代蓝图截断 |
| 截断后不得重发同一 prompt；顺序是「升额度 → 拆小/续写 → 报错」 | T3（Claude Code 源码笔记、LLM API 错误手册） | 二次截断改按文件拆分 |
| 过度编辑是独立失效轴；一条 preservation 指令即可显著降低超额改动 | T1（arXiv 2609.04061；MSR 2026 回滚原因研究） | 加 preservation 规则与改动面读数 |
| 确定性 AST 后处理可修掉多数 API/标识符冲突 | T1（arXiv 2601.19106） | 机械能修的优先机械修 |
| 补丁验证是独立阶段（localization → repair → validation） | T1（Agentless FSE 2025；EviACT） | 写前校验 + 编译/导入冒烟 |

## 4. 结论

四条改动即可闭环：入口缺 guard 时确定性补丁；所有 prompt 共享结构化符号契约；修复一次只回一个文件；所有晚写入点先过统一契约校验再写盘。截断与过度编辑各补一条出口与读数。

## 5. 来源

- [Edit formats | aider](https://aider.chat/docs/more/edit-formats.html)（T1，2026-11-28 读）
- [Repository map | aider](https://aider.chat/docs/repomap.html)（T1）
- [GPT code editing benchmarks | aider](https://aider.chat/docs/benchmarks)（T1）
- [Tools reference — Claude Code Docs](https://code.claude.com/docs/en/tools-reference)（T1）
- [Codex `apply_patch` 提示词原文](http://raw.githubusercontent.com/openai/codex/87f7226cca12df04596938f58625de84e976309a/codex-rs/core/gpt_5_2_prompt.md)（T1）
- [Python Packaging User Guide — CLI entry points](https://packaging.python.org/en/latest/guides/creating-command-line-tools/)（T1）
- [When Models Edit Too Much: On the Fidelity of Minimal Code Edits（arXiv:2609.04061）](https://arxiv.org/html/2609.04061v1)（T1）
- [How Much Do Coding Agents Over-Edit?（arXiv:2611.34875）](https://arxiv.org/html/2611.34875v1)（T1）
- [Detecting and Correcting Hallucinations via Deterministic AST Analysis（arXiv:2601.19106）](https://web3.arxiv.org/pdf/2601.19106)（T1）
- [Demystifying LLM-Based Software Engineering Agents（Agentless, FSE 2025）](http://lingming.web.illinois.edu/publications/fse2025.pdf)（T1）
- [12、错误处理与自动恢复：Claude Code 源码学习笔记](https://cc.windliang.wang/12-production-agent-recovery-observability-and-testability.html)（T3）
- 运行 O 现场：B 站 `~/arc-runs/g7-baseline/p230-stage10.log`（21:06:55–21:37:44）
