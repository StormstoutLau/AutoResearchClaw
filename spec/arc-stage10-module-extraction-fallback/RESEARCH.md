---
id: arc-stage10-module-extraction-fallback-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-26
depends: [arc-stage10-blueprint-yaml-robust]
upstream: arc-master-roadmap
---

# 调研：Stage 10 模块级截断提取兜底与证据门误报收口（B-34）

> **背景**：B 站运行 E（2026-11-26，15 769.77 s）中蓝图 36 831 字符**解析成功**，但顺序生成的四模块各命中一次 `truncated`；`data.py` 重试后仍 `Empty code` 被 `continue` 静默跳过，四小时后才在出口失败。归因订正与范围见 [postmortem §F-7b](../../docs/arc-b-site-stage10-postmortem-20261126.md) 与 [P-204 复审](../../docs/arc-p203-postmortem-review-20261126.md) §4。
> **本批范围**：B-34 的 M1-a / M1-b + F-1..F-6（共 8 项）。M2（模块 prompt 瘦身）**不在本批**，见 §6。

## 0. 结论

1. 单文件提取器 [`_extract_single_file_code`](../../researchclaw/pipeline/code_agent.py#L992-L1025) 的三个 fenced 正则都要求闭合围栏；P-178 的 `_close_unterminated_fence` 只补在 [`_extract_code_block`](../../researchclaw/pipeline/_helpers.py#L591) 与 [`_extract_multi_file_blocks`](../../researchclaw/pipeline/_helpers.py#L609)，单文件路径一行未补（§1.1 读数）。
2. 截断响应（含开围栏 + 半截代码）在回落分支必然 `ast.parse` 失败 → 返回 `""`；调用方只记 WARNING 后 `continue`，于是「缺模块」被推迟到出口证据门才暴露（§2.1）。
3. 32768 之后的 `truncated` 从未被检查：代码只判断首轮 8192 的 `truncated`，重试后直接进入提取（§2.2）。因此「32768 是否仍截断」既不可观测、也不会失败。
4. P-204 登记的六项证据门误报/误判可逐条本地重放（§1.2）：注释里的数据源算命中（F-1）、注释里的 `np.random` 算合成（F-5）、`*Config` 一刀切（F-2）、指标名在 `)`/`]` 处被截断（F-3）、`bool` 叶子静默丢弃（F-4）、`code_version()` 版本回落不可见（F-6）。
5. 八项修法都**不新增概念**：闭合围栏与 P-178 同修法；显式失败复用 `steps.jsonl` 与 `execute_stage` 既有异常路径；F-1/F-5 共用一次「剔除注释」；其余四项是单函数级判据收紧。

## 1. 现场证据

### 1.1 提取器与截断（E1，可重放）

本机以最小响应复现（2026-11-26，HEAD `304c9f8`）：

```python
CodeAgent._extract_single_file_code("```python\nimport numpy as np\n\nX = np.zeros(3)\n", "data.py")
# → ''                      （开围栏未闭合，三个模式全不匹配，回落 ast.parse 失败）
CodeAgent._extract_single_file_code("```python\nimport numpy as np\n\nX = np.zeros(3)\n```", "data.py")
# → 'import numpy as np\n\nX = np.zeros(3)'
```

运行 E 的实际体积（postmortem §F-7b.1）：methods 448 行 / 15 802 B、config 343 / 12 528、models 217 / 6 911、main 112 / 3 904，约 2–4.5k tokens——**远低于 8192**。故失败不是「模块超容量」，而是「完整回答没写闭合围栏 / 真正截断时没有兜底」。

### 1.2 证据门六项误报（E1，逐项读数）

| 项 | 输入 | HEAD 读数 | 应有读数 |
|---|---|---|---|
| F-1 | `data.py = "# yfinance\nX = 1\n"`（蓝图声明 `data.source`） | `([], False)` — 注释即命中 | `warnings` 非空 |
| F-5 | `data.py = "# we avoid np.random here\nimport pandas as pd\n"` | `synthetic=True` — 注释触发 | `synthetic=False` |
| F-2 | `class KernelConfig:` + 真实 `compute()` | `0` 个计算单元 | `1` |
| F-3 | `print("METRIC_DEF: auroc(delta) ...")` | `'auroc(delta'` | `'auroc(delta)'` |
| F-3 | `print("METRIC_DEF: hit@k[5] ...")` | `'hit@k[5'` | `'hit@k[5]'` |
| F-4 | `_leaf_strings(True)` / `{"source": True}` | `[]`（隐式，`bool` ⊂ `int`） | `[]`（显式） |
| F-6 | 删去 `researchclaw.__version__` 后 `code_version()` | `'0+…'` 且**无任何日志** | 同值 + DEBUG 可观测 |

`auroc{0.5}` 在 HEAD 已完整保留（`{`/`}` 不在排除类），本批把它固化为用例，避免回归。

## 2. 机制解剖（E3 @HEAD）

### 2.1 提取路径缺闭合围栏

[`_extract_single_file_code`](../../researchclaw/pipeline/code_agent.py#L992-L1025) 的顺序是：`python` fenced 正则 → `filename:` 正则 → 任意 fenced 正则 → 原文 `ast.parse` 回落。三个正则都以闭合围栏结尾，未闭合围栏一律不匹配；回落分支面对「开围栏 + 半截代码」必然 `SyntaxError` → `""`。P-178 的同名兜底只被 [_helpers.py L591/L609](../../researchclaw/pipeline/_helpers.py#L591-L609) 的两个提取器调用。

### 2.2 重试后的截断不可观测

[`_phase2_sequential_generate`](../../researchclaw/pipeline/code_agent.py#L785-L918) 在首轮 `truncated` 时把预算升到 32768，随后**不再读取** `resp.truncated`；提取为空只 `_log_event("WARNING: Empty code …")` 然后 `continue` 到下一个模块。`finish_reason == "length"` 到 `truncated` 的映射在 [llm/client.py L877](../../researchclaw/llm/client.py#L877)，信息本身可靠，只是没有被消费。

### 2.3 证据门六处判据过宽/过窄

| 项 | 位置 | 机制 |
|---|---|---|
| F-1 / F-5 | [`check_data_source`](../../researchclaw/pipeline/codegen_evidence.py#L335-L359) | `"\n".join(files.values())` 把注释当正文做子串/正则匹配 |
| F-2 | [`count_compute_units`](../../researchclaw/pipeline/codegen_evidence.py#L381-L404) | `_is_config_name` 按后缀直接跳过，不看类体 |
| F-3 | [`_METRIC_DEF_RE`](../../researchclaw/pipeline/codegen_evidence.py#L35) | 排除类含 `)`、`]`，带括号的指标名被截半 |
| F-4 | [`_leaf_strings`](../../researchclaw/pipeline/codegen_evidence.py#L134-L157) | `bool` 被隐式排除（`bool` ⊂ `int`），意图不可读 |
| F-6 | [`code_version`](../../researchclaw/pipeline/step_journal.py#L75-L91) | `except Exception` 直接置 `"0"`，无日志 |

## 3. 社区/标准库源码级证据锚点

| ID | 来源（层） | 原文 / 实测要点 | 支撑 |
|---|---|---|---|
| A-1 | CPython `tokenize`（T1，本机 3.11 实测） | `# yfinance\nX = 1\n` → COMMENT 与 NAME/OP/NUMBER 是独立 token；字符串不被拆 | F-1/F-5：剔除注释是**词法事实**，不是正则猜测 |
| A-2 | CPython `ast`（T1，本机实测） | `KernelConfig.compute` 的方法体是 `Return`；纯声明类的 `__init__` 体只有 `Pass`；docstring 是 `Expr(Constant)` | F-2：判据应为「类体是否有非平凡语句」 |
| A-3 | `json_repair` README（T1，P-194 §3 S-2 已抓取） | "If the string was super broken this will return an empty string." | M1-b：修不了就**显式失败**，不要伪造空结构 |
| A-4 | LangChain `OutputFixingParser`（T2，官方 API） | `max_retries: int = 1` | M1-b：升级一次（8192→32768）后仍失败即止，不做第三次 |
| A-5 | 本仓 P-178 实现（T1，E1） | `_close_unterminated_fence` 已被 `_extract_code_block` 与 `_extract_multi_file_blocks` 调用 | M1-a：同一修法补齐第三个调用点 |
| A-6 | CPython `logging` HOWTO（T2，官方） | `DEBUG` 低于默认 `WARNING`，默认不可见 | F-6：回落日志用 DEBUG，不打扰默认输出但可取证 |
| A-7 | 本仓 `execute_stage`（T1，E3） | 阶段执行器异常 → `StageStatus.FAILED`，不进入 `_call_with_retries` 的同级重试 | M1-b：抛异常是既有的显式失败通道 |

**提炼的三条纪律**：
1. **同一修法要枚举所有调用点**（A-5）：P-178 的兜底漏掉一个提取器，代价是四小时；
2. **不能修复就判失败**（A-3/A-4）：显式失败优于静默的半成品；
3. **能问 AST/token 就不问正则**（A-1/A-2）：注释与类体结构在语法层可判定。

## 4. 方案（8 项）

| 项 | 内容 | 依据 |
|---|---|---|
| M1-a | `_extract_single_file_code` 入口先 `content = _close_unterminated_fence(content)` | A-5、§1.1 |
| M1-b | 升级后仍 `truncated` 或提取为空 → 记 `steps.jsonl`（`status=failed`）并抛 `ModuleExtractionError`，不再 `continue` | A-3/A-4/A-7、§2.2 |
| F-1/F-5 | `check_data_source` 先用 `tokenize` 剔除注释再匹配；不可 tokenize 时保持原文（fail-open） | A-1 |
| F-2 | `*Config` 类仅当类体无非平凡语句时才排除；有真实方法的仍计为计算单元 | A-2 |
| F-3 | `_METRIC_DEF_RE` 只以空白/竖线/分号为终止符，圆括号与方括号均属名字 | §1.2 |
| F-4 | `_leaf_strings` 增加显式 `bool` 分支并注释（行为不变，意图可读） | §1.2 |
| F-6 | `code_version()` 版本回落改为 `logger.debug`（带原因），返回值不变 | A-6 |

## 5. 未决项（四元块）

| 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|
| 「截断但可提取」是否算失败 | 每次 `truncated=True` | **算失败**：`finish_reason=length` 意味着代码被切断，部分模块比缺模块更难发现 | E1（`test_still_truncated_after_escalation_fails_fast`） |
| 注释剔除失败（文件不可 tokenize）时如何处理 | 语法错误的生成文件 | **fail-open 保持原文**：门不因自身解析失败新增误报；可运行性由入口契约负责 | E1（`test_unparsable_file_falls_back_to_raw_text`） |
| 括号型指标名的尾随标点怎么办 | 名字以 `)` 收尾且同句带逗号 | 保留括号、只 `rstrip` 引号与 `.,;:`；宁可让门显式 mismatch，也不猜截断 | E1（F-3 用例） |
| M2（prompt 瘦身）是否本批做 | — | **不做**：无已复现失败，且需先测 token 占比；见 §6 | — |

## 6. 非目标

- **不提高生成预算**（用户明确约束）：M1-b 只让失败更早、更显式，不改 8192→32768 的升级策略。
- **不做 M2（模块 prompt 只注入依赖子集蓝图）**：本轮唯一的现场问题是「取不回模块 / 误判」，不是「prompt 太大」；瘦身会改变生成分布，需独立度量 baseline，留 B-34 后续。
- 不把失败模块自动重新生成第二次：升级一次后仍失败即止（A-4）。
- 不为注释剔除引入第三方解析器：stdlib `tokenize` 足够，且已在 3.11 / 3.13 双环境可用。
- 不改 `finish_reason` 到 `truncated` 的映射，也不改 LLM 客户端。

