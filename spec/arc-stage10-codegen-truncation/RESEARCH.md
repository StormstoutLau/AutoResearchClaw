---
id: arc-stage10-codegen-truncation-RESEARCH
type: design
version: 1.1
status: verified
date: 2026-11-25
depends: [arc-stage9-fanout-RESEARCH]
upstream: arc-master-roadmap
---

# 调研：Stage 10 代码生成截断与「空文件进评审」（P-178 候选）

> **症状**：B 站基线 run 的 Stage 10 `CODE_GENERATION` 耗时 1491.2s 后返回 `DONE`，产出 `experiment/main.py`（仅常量）与 `experiment/data.py`；Stage 11 正常；Stage 12 在 0.18s 内以「zero real metrics」失败。
> **取证**：2026-11-25 经 SSH 只读采集 B 站 `stage-10/code_agent_log.json`、`architecture_spec.yaml`、`experiment/*`、`stage-12/runs/run-1.json`、`cost_log.jsonl`。**本文件零代码改动。**

## 1. 现场读数（E1）

| # | 读数 | 证据 |
|---|---|---|
| O-1 | `Blueprint spec: 4478 chars`；随后两条 `Blueprint YAML parse error: ... line 1, column 1: ```yaml` | `stage-10/code_agent_log.json` |
| O-2 | `WARNING: Could not parse blueprint YAML` → `Sequential generation requested but blueprint invalid — falling back to single-shot` | 同上 |
| O-3 | `Empty extraction, retrying with 32768 tokens` → `WARNING: empty generation, returning fallback` | 同上 |
| O-4 | `Review round 1: critical_issues=8`、`round 2: critical_issues=15`；总计 `7 LLM calls, 0 sandbox runs, 1325.8s` | 同上 |
| O-5 | `stage-10/architecture_spec.yaml` **首行即** ` ```yaml `（围栏未被剥离） | 站上文件 |
| O-6 | `cost_log.jsonl`：blueprint 与 single-shot 调用的 `completion_tokens` 均为 **8192**（等于上限） | 站上 cost log |
| O-7 | 最终 `experiment/main.py` 是只含常量的 config 模块（开头自述 “Configuration for …”），无 `__main__` 入口；`data.py` 为数据生成器 | 站上文件 |
| O-8 | `stage-12/runs/run-1.json`：`status=completed, returncode=0, elapsed_sec=0.007, metrics={}, stdout="", stderr=""` | 站上文件 |
| O-9 | Stage 12 守卫报 `zero real metrics (budget was 600s). Likely a misclassified crash` | `stage-12/decision.json` |

结论：Stage 12 的守卫是**正确的**；问题在 Stage 10 把「截断后无法解析」的产物当成成品交付。

## 2. 代码路径（T1，回原文）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | Blueprint 调用固定 `max_tokens=8192` | [code_agent.py L268](../../researchclaw/pipeline/code_agent.py#L268) |
| F-2 | Blueprint 只用「必须闭合」的围栏正则提取 YAML；未闭合则保留原文（含 ` ```yaml `） | [code_agent.py L271-L274](../../researchclaw/pipeline/code_agent.py#L271-L274) |
| F-3 | `_parse_blueprint` 直接对含围栏的文本做 `yaml.safe_load`，失败仅记日志并返回 `None` | [code_agent.py L326-L415](../../researchclaw/pipeline/code_agent.py#L326-L415) |
| F-4 | 单文件抽取器（sequential 路径）每次调用 `max_tokens=8192` | [code_agent.py L506](../../researchclaw/pipeline/code_agent.py#L506) |
| F-5 | 多文件抽取器全部模式都要求闭合 ` ``` `；单块回退也要求闭合，否则只在「整段能 `ast.parse`」时才接受 | [_helpers.py L584-L598](../../researchclaw/pipeline/_helpers.py#L584-L598)、[L601-L680](../../researchclaw/pipeline/_helpers.py#L601-L680) |
| F-6 | 截断从不被识别：仅当「内容为空」才重试 32768；`finish_reason` 未参与判定 | [code_agent.py L986-L993](../../researchclaw/pipeline/code_agent.py#L986-L993) |
| F-7 | 文件为空时仍进入 Review；Review 的修复提示要求「输出全部文件」，其返回值被 `files.update(fixed)` 直接接受 | [code_agent.py L1282-L1343](../../researchclaw/pipeline/code_agent.py#L1282-L1343) |
| F-8 | Review 之后不再跑 hard validation 或 exec-fix | [code_agent.py L217-L222](../../researchclaw/pipeline/code_agent.py#L217-L222) |
| F-9 | `main.py` 的 `if __name__ == "__main__"` 校验只在 sequential 路径、且在 Review 之前 | [code_agent.py L800-L832](../../researchclaw/pipeline/code_agent.py#L800-L832) |
| F-10 | Stage 10 对 agent 返回的 `files` 无条件写盘并返回 `DONE` | [_code_generation.py L1205-L1209](../../researchclaw/pipeline/stage_impls/_code_generation.py#L1205-L1209)、[L940-L991](../../researchclaw/pipeline/stage_impls/_code_generation.py#L940-L991) |
| F-11 | Stage 12 的零指标守卫会拒绝 rc=0 但无 metrics 的「假完成」 | [_execution.py L787-L801](../../researchclaw/pipeline/stage_impls/_execution.py#L787-L801) |

## 3. 外部证据

| # | 来源 | 关键结论 | 本批借用 | 层 |
|---|---|---|---|---|
| E1 | [OpenAI API Reference — Chat](https://developers.openai.com/api/reference/resources/chat/) | `finish_reason` 取值含 `stop` / `length` / `content_filter` 等；`length` 表示**因 `max_tokens` 或模型上限而不完整** | 截断必须由调用方显式处理，不能假设「返回了内容就是完整的」 | T1 |
| E2 | [OpenAI Agents SDK — Models](https://openai.github.io/openai-agents-js/guides/models/) | 对 `finish_reason: 'length'` 的处理：保留可用的部分载荷；若截断后**没有任何可用载荷**则报错，而不是静默接受 | 与我们相反：当前实现把「无可用载荷」交给 Review 去补，最终静默 DONE | T2 |
| E3 | [Anthropic — Handling stop reasons](https://docs.anthropic.com/en/api/handling-stop-reasons) | `stop_reason=max_tokens` 表示达到请求上限；应据此决定重试、续写或拆分 | 同一语义在不同供应商都存在，属通用契约 | T1 |

> 降级链：三条均为官方文档直读；未取到实现细节的部分仅用于形态对照，不参与数值判据。

## 4. 根因

| ID | 根因 | 触发链 |
|---|---|---|
| R1 | **Blueprint 围栏未闭合**：8k 上限截断导致没有结尾 ```，正则不匹配，原文进 YAML 解析器（F-1/F-2/F-3，O-1/O-2/O-5/O-6） | 顺序生成被跳过 |
| R2 | **抽取器要求闭合围栏**：截断响应既过不了多文件模式，也过不了单块回退（F-5，O-3） | 8192 与 32768 两次都得到空文件集 |
| R3 | **空文件仍进 Review**：评审被要求「输出全部文件」，模型只给了 2 个不完整文件（config 风格 `main.py` + `data.py`），被直接合并为成品（F-7，O-4/O-7） | Stage 10 交付了不可执行项目 |
| R4 | **截断无感知**：`finish_reason` 从不参与判定，重试只在「完全空」时发生，且重试预算与首次相同（F-6） | 截断被当成正常输出 |
| R5 | **出口无强校验**：Review 后不再做 hard validation / exec-fix；Stage 10 无「可执行入口」出口门（F-8/F-9/F-10） | 错误被推迟到 Stage 12 才暴露 |

补充：即使 R1 修复、sequential 路径恢复，R4 仍会让单文件超过 8k 时静默截断；因此 R1/R2 与 R4 需同批处理。

## 5. 方案对比

| 方案 | 做法 | 解决 | 代价 |
|---|---|---|---|
| **A 容错围栏（最小）** | 无闭合围栏时取到 EOF；`_parse_blueprint` 额外剥掉首行 ```yaml | R1/R2 | 低；恢复 blueprint → sequential 逐文件生成 |
| **B 截断感知与分级重试** | `finish_reason == "length"` → 记录并重试 32768；仍截断 → 切换逐文件生成；仍失败 → FAILED | R4 | 中；需明确「重试 vs 拆分」的判定 |
| **C 评审守卫** | 输入文件为空时跳过 Review；Review 改过文件后强制重跑 hard validation + exec-fix | R3/R5 | 低；避免「评审凭空造项目」 |
| **D 出口门** | Stage 10 要求 `main.py` 有 `__main__` guard 且打印 `METRIC_DEF`，否则 FAILED(65) | R5 | 低；把失败前移到 Stage 10 |
| **E 强制逐文件** | blueprint 有效时不再走 single-shot，每文件一次调用 | 结构性规避「5 文件塞一个 8k 响应」 | 中；调用次数增加，但单次更短 |

**建议**：**A + C + D 先做**（低风险、立即止血），**B + E 紧随**（解决根因，需设计裁决重试/拆分策略）。

## 6. 未决项（四元块）

| ID | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|---|
| U-178-1 单次调用的实际输出上限 | 站上 `/v1/models` 或服务文档给出 `max_output_tokens`，且与 `finish_reason` 对照 | 实现 B 前 | 估计 8192（O-6 两次命中） | 待核 |
| U-178-2 重试 vs 拆分 | 对同一 blueprint 的 5 文件，逐文件生成的 token 峰值 < 单次全量 | 实现 E 前用一次 A/B 实测 | 倾向 E（逐文件），因为截断面最小 | E3 |
| U-178-3 Stage 10 失败分类 | 「无可执行入口」应映射为 65（数据/契约）而非 75 | 实现 D 时 | 65，不重启 | E3 |

## 7. Review（Step 2 自查）

> **[自查·单视角]（RULE-4）**；未引入异构第二会话（RULE-5）。

| 检查 | 结果 |
|---|---|
| 现场读数可复核 | O-1..O-9 均可由站上只读命令重放 |
| 代码锚点 | F-1..F-11 全部带文件/行号 |
| 因果链完整 | 截断 → blueprint 无效 → single-shot 空 → Review 补齐 → 无出口门 → Stage 12 守卫 |
| 外部结论多源 | 截断契约：E1/E3；截断处理形态：E2 |
| 归因扭曲检查 | 未把「模型输出质量差」当作唯一原因；已区分「模型只给了 2 个文件」与「框架接受它」两个环节 |

## 8. 诚实边界

1. 未保存 single-shot 的原始响应，无法判断 32768 重试是「仍被截断」还是「格式不匹配」；两种都成立时现有抽取器都会返回空。
2. `finish_reason` 在 B 站模型上的取值未直接取证（框架日志未打印），推断依据是 O-6 的 8192 命中与 O-5 的未闭合围栏。
3. 本文件不主张「提高 max_tokens 就能解决」；R1/R2 是解析健壮性问题，R3/R5 是流程守卫问题。
