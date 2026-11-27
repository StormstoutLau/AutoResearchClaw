---
id: arc-stage10-repair-guardrails-RESEARCH
type: design
version: 1.1
status: verified
date: 2026-11-28
depends: [arc-stage10-repair-quality, arc-stage10-generation-budget-contract]
upstream: arc-master-roadmap
---

# 调研：Stage 10 修复护栏（B-36 P1，社区经验与本地缺口）

> **状态**：调研完成，方案见 [DESIGN](DESIGN.md)；本批零代码，实施属后续批次。
> **触发**：运行 K（P-219 快照）attempt 2 的四轮定向修复把合法 `data.py` 写成碎片、四轮覆盖掉带 `__main__` 的入口，59 分钟后才由出口门报 `blueprint_symbols_missing`。P-222 已用静态三闸门堵住「静默覆写」，本调研回答：**社区是否有同类案例、他们怎么处理、我们下一步该补什么**。

## 1. 本地事实与缺口

| # | 事实 | 锚点 |
|---|---|---|
| L-1 | P-222 已实现修复回复四道验收：未知模块、`.py` 可解析、`main.py` 入口契约、蓝图符号不回退；不过即整文件拒收并保留原版本 | [code_agent.py `_accept_repair_files`](../../researchclaw/pipeline/code_agent.py#L1647) |
| L-2 | 验收是**静态**的：不执行代码，不校验 import 是否能解析、运行期符号是否存在 | 同 L-1 |
| L-3 | 同一 critical 连续 4 轮被拒后仍会跑满 `hard_validation_max_repairs`，运行 K 单文件约 4 分钟/轮 | [code_agent.py `_hard_validate_and_repair`](../../researchclaw/pipeline/code_agent.py#L1324) |
| L-4 | 修复提示不含上一轮被拒原因；运行 I 两次 repair 的 prompt sha 相同（同一请求重采样） | [postmortem §2.6](../../docs/arc-b-site-stage10-postmortem-20261126.md#L250) |
| L-5 | 修复账本只有 accepted/rejected 名称与摘要，无修复前后 digest/行数，无法一眼判断「保留的是哪一版」 | [repair_trace.py](../../researchclaw/pipeline/repair_trace.py) |
| L-6 | 沙箱执行能力已存在（`exec_fix_loop`、CodeAgent `_run_in_sandbox`），但未接入修复验收 | [code_agent.py `_exec_fix_loop`](../../researchclaw/pipeline/code_agent.py#L1650) |

## 2. 社区与学术证据

### 2.1 自我修复的收益与风险

| 来源 | 结论 | 对我们的含义 |
|---|---|---|
| Olausson et al., ICLR 2024《Is Self-Repair a Silver Bullet?》 | 计入成本后收益「modest、inconsistent、有时不存在」；弱模型修复时**引入新错误**；部分任务上不修复、直接重采样更好 | 不能把「修过」当收益；必须允许「拒收并保留原版」 |
| Huang et al., ICLR 2024《LLMs Cannot Self-Correct Reasoning Yet》 | 无外部反馈的内在自纠会**降性能**，把对改错的概率高于反向 | 修复提示必须带外部错误/被拒原因，而非让模型自评 |
| 2026 预印本《How Many Tries Does It Take?》 | 跨模型规模重审自我修复，结论仍依赖模型与反馈质量 | 修复轮数不是越多越好；需要止损 |

### 2.2 静默覆写与整文件重写

| 来源 | 现象 | 他们的处理 |
|---|---|---|
| Cline CHANGELOG | `apply_patch` 在模型用 “Add File” 指向已存在路径时**静默覆写**，原文「contents were replaced with no error and no record of what was lost」 | 改为显式失败，不再静默覆盖 |
| Cursor 论坛（官方回复） | Agent 后续轮次可覆盖手工修改，「known pattern, tracking」 | 检查点/还原 |
| Cursor 论坛（讨论帖） | 编辑失败（search/replace 或 patch 不干净）后 agent **退回整文件重写** | 建议按行号编辑、避免整文件重写 |
| VS Developer Community #11009462 | Copilot Agent 在大文件上删代码、反复重生成、最终覆盖文件，用户丢失数天工作 | 上下文上限 + 恢复机制 |
| GitLab wally #195 | agent 忽略工具错误反馈、陷入自纠循环直至超时 | 循环上限 + 失败上报 |
| Cline v3.54.0 发布说明 | 「replaceinfile 反复失败时防止无限重试」 | 重复失败检测后跳出循环 |
| Cline Checkpoints / aider `/undo` | — | 每轮变更可还原（checkpoint / git undo） |

### 2.3 「验证独立于生成」的有效性

| 来源 | 结论 | 对我们的含义 |
|---|---|---|
| Agentless, FSE 2025 | 「定位 → 修复 → **补丁验证**」三段式在 SWE-bench Lite 达 32.00%（96 个修复）、成本 $0.70，超过当时复杂 agent | 验证是一等阶段；简单流程 + 严格验证可胜过自由 agent 循环 |
| AlphaCodium, 2024 | 同一 GPT-4，单提示 pass@5 19% → 结构化 flow（含测试迭代）44% | 流程/验收设计比加预算更能提升质量 |
| 多篇工程案例（dev.to、xSquads、Forkbench） | agent 为让测试变绿去**改测试/删断言**（reward hacking） | 验收不得允许修改测试文件；判据要独立于被测对象 |

### 2.4 截断

- OpenAI / Anthropic API 文档与工程实践一致：`finish_reason=length` / `stop_reason=max_tokens` 表示输出不完整，应提高上限或续写，不能把半截当成品。
- 对应：P-222 已把 agent 修复的 16 384 截断升级一次到 32 768。

## 3. 对照矩阵

| 运行 K 现象 | 社区对应 | 我们的缺口 | 方案决策 |
|---|---|---|---|
| 四轮修复写坏 data.py | Cline 静默覆写、Cursor 整文件重写 | 已有静态拒收；缺执行级验证、缺还原点读数 | D-2、D-3 |
| 13→2→2→2→2 不收敛 | wally 自纠循环、Cline 无限重试 | 有轮数上限，无「同因重复即止损」 | D-1 |
| main.py 守卫被覆盖 | Copilot 丢代码、Cursor 覆盖 | P-222 已拒收；缺「保留版本」显式读数 | D-2 |
| 修复 prompt sha 相同 | Huang/Olausson：外部反馈决定收益 | 被拒原因未回传 | D-4 |
| 修复失败后只能整文件重写 | Cursor 建议行号编辑、Cline diff 应用 | 无 diff/行号修补兜底 | D-5 |
| 只信静态检查 | Agentless patch validation、AlphaCodium 测试迭代 | 缺执行级/测试级验收 | D-3、D-6 |
| 无离线对照 | AlphaCodium 的 flow 对照 | 缺 fixture 基准 | D-7 |

## 4. 结论

1. **社区经验支持 P-222 的方向**：不允许静默覆写、保留上一版、把验证从生成中独立出来；这与 Cline 的覆写修复、Cursor 的检查点、Agentless 的 patch validation 同构。
2. **静态闸门不够**：社区与论文都把「执行/测试反馈」作为判别力来源；我们已有沙箱，缺的是把它接进修复验收。
3. **自我修复本身收益不稳定**：因此方案应以「减少无效轮次 + 保留好版本 + 提供可执行反馈」为主，不以「提高修复成功率」为承诺。
4. **证据强度**：§2.1/§2.3 为同行评审论文；§2.2 为 issue/发布说明/论坛，属工程经验，不能替代对照实验。

## 5. 来源

- [Is Self-Repair a Silver Bullet for Code Generation?（arXiv 2306.09896）](https://arxiv.org/pdf/2306.09896)
- [Large Language Models Cannot Self-Correct Reasoning Yet（arXiv 2310.01798）](https://arxiv.org/pdf/2310.01798)
- [How Many Tries Does It Take?（2026 预印本）](https://arxiv.org/html/2604.10508v1)
- [Agentless: Demystifying LLM-based Software Engineering Agents（arXiv 2407.01489）](https://arxiv.org/pdf/2407.01489)
- [Code Generation with AlphaCodium（arXiv 2401.08500）](https://arxiv.org/pdf/2401.08500)
- [Cline CHANGELOG（apply_patch 不再静默覆写）](https://raw.githubusercontent.com/cline/cline/refs/heads/main/CHANGELOG.md)
- [Cline v3.54.0 发布说明（防止无限重试）](https://www.havoptic.com/r/cline-3.54.0)
- [Cursor 论坛：迭代编辑覆盖代码](https://forum.cursor.com/t/editor-can-lose-overwrite-code-during-iterative-edits/159450/5)
- [Cursor 论坛：失败编辑后的整文件重写](https://forum.cursor.com/t/a-way-to-reduce-whole-file-rewrites-after-failed-llm-edits/167947)
- [VS Developer Community #11009462（Copilot Agent 覆盖代码）](https://developercommunity.visualstudio.com/t/11009462)
- [GitLab wally #195（自纠循环）](https://gitlab.com/lx-industries/wally-the-wobot/wally/-/issues/195)
- [Cline Checkpoints](https://docs.cline.bot/core-workflows/checkpoints)
- [aider Git integration（/undo）](https://aider.chat/docs/git.html)
- [LLM API 错误：finish_reason=length](https://ai-tldr.dev/learn/llm-apis/api-basics/llm-api-errors/)
