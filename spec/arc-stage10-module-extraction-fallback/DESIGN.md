---
id: arc-stage10-module-extraction-fallback-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-26
depends: [arc-stage10-module-extraction-fallback-RESEARCH]
upstream: arc-stage10-module-extraction-fallback-RESEARCH
---

# 设计：Stage 10 模块级截断提取兜底与证据门误报收口（B-34）

## 1. 决策

| ID | 决策 | 被拒替代 | 理由 |
|---|---|---|---|
| D-1 | M1-a：`_extract_single_file_code` **入口**调用 `_close_unterminated_fence`，与 P-178 的两个提取器同修法 | 在三个 fenced 正则里分别加「可选闭合围栏」 | 三个正则各改一次会产生三份语义；入口归一化只改一行，且幂等（已闭合原样返回） |
| D-2 | M1-b 的失败判据 = **升级后 `truncated`** OR **提取为空** | 只以「空字符串」判失败 | `finish_reason=length` 表示代码被切断；能提取出「半截模块」比缺模块更难在前端发现（证据门只查文件存在） |
| D-3 | 失败后**抛 `ModuleExtractionError`**，立即终止本阶段生成 | ① 记 diag 后继续（原行为）；② 返回部分 files 交出口门判 | ① 是四小时浪费的直接来源；② 仍要跑完硬校验 / exec-fix / review 才失败。异常经 `execute_stage` 转 `FAILED`，是既有显式失败通道（调研 A-7） |
| D-4 | 失败证据写 `steps.jsonl`：`step_id="generate_file"`、`variant=<file>`、`status="failed"`、`truncated`、摘要 only | ① 写 `codegen_decision.json`；② 不记账 | ① 该文件的语义是「回退决策」，失败模块不是回退；② `steps.jsonl` 是 B-33 既有账本，I-2/I-3 已规定只存摘要、只复用 `done` |
| D-5 | F-1/F-5：用 `tokenize` **只剔除注释 token**，字符串与代码原样保留；无法 tokenize 时保持原文 | ① 正则删 `#.*$`；② 整文件 `ast` 后重生成 | ① 会误删字符串里的 `#`；② 重生成会丢失格式且更贵。fail-open 保证门不因自身解析失败新增误报 |
| D-6 | F-2：`*Config/*Settings/*Params` 类仅在**类体无非平凡语句**时排除；方法体含 `Return`/赋值/调用等即算行为 | ① 删除后缀规则（全按类计）；② 只数方法个数 ≥1 | ① 会让纯 dataclass 计为计算，配置自检又能通过；② `def __init__(self): pass` 也是方法。判据用「语句是否平凡」 |
| D-7 | F-3：`_METRIC_DEF_RE` 终止符只保留空白 / 竖线 / 分号，`(` `[` `{` 与 `)` `]` `}` 均属名字；`rstrip(".,;:'\"")` 不变 | 继续维护排除字符类 | 名字形态无界（`auroc(delta)`、`hit@k[5]`、`auroc{0.5}`）；白名单比黑名单稳定。格式分隔符已由提示约束为 ` \| ` |
| D-8 | F-4：`_leaf_strings` 增加显式 `bool → []` 分支 + 注释 | 把 `True/False` 转字符串参与匹配 | 布尔是开关，不是数据源名；转字符串只会制造「declared data source 'True'」噪声 |
| D-9 | F-6：版本回落改 `logger.debug` 并带异常原因，返回值与格式不变 | ① `logger.warning`；② 不记录 | ① 会在每次 `append_step` 调用时污染默认输出；② 「不可见」正是本条缺陷。DEBUG 可取证且默认静默（调研 A-6） |
| D-10 | **不做** M2（prompt 瘦身）与**不提高**生成预算 | — | 用户明确约束不加预算；M2 无已复现失败、需独立度量，留后续批次（调研 §6） |
| D-11 | 异常不在网络层重试：`execute_stage` 捕获后直接 `FAILED`，同级 `_call_with_retries` 不介入 | 在 `_phase2` 内部重试第三次 | 重试第三次违背 A-4 的「修复次数有上限」；同一响应再要一次大概率同样截断 |

## 2. 接口

```python
# researchclaw/pipeline/code_agent.py
class ModuleExtractionError(RuntimeError):
    file_name: str          # e.g. "data.py"
    reason: str             # "truncated" | "empty"

CodeAgent._record_module_failure(
    *, file_name: str, reason: str, truncated: bool,
    file_spec_str: str, dep_code: str,
    prompt_version: str, model: str,
) -> None                   # best-effort journal append

CodeAgent._extract_single_file_code(content, expected_name) -> str   # 签名不变
```

```python
# researchclaw/pipeline/codegen_evidence.py
_strip_comments(text: str) -> str        # 新增；tokenize 失败时原样返回
_class_has_behavior(node: ast.ClassDef) -> bool   # 新增
check_data_source(blueprint, files) -> tuple[list[str], bool]   # 签名不变
count_compute_units(files) -> int                                # 签名不变
```

顺序生成的新流程：

```text
chat(8192) ──truncated?──> chat(32768) [budget=32768]
                                    │
              truncated or empty? ──┴── no ──> generated_files[file] = code
                     │
                     yes
                     ├─ diag["module_failures"].append({file, reason, budget, chars})
                     ├─ append_step(status="failed", truncated=...)
                     └─ raise ModuleExtractionError  → Stage 10 FAILED
```

```json
// stage-10/steps.jsonl（失败记录，摘要 only）
{
  "seq": 2,
  "step_id": "generate_file",
  "variant": "data.py",
  "status": "failed",
  "inputs_digest": "sha256:…",
  "outputs": {},
  "truncated": true,
  "code_version": "0.5.0+…",
  "prompt_version": "…"
}
```

## 3. 提取与注释处理算法

| 项 | 规则 |
|---|---|
| 闭合围栏 | `text` 中 ``` 出现奇数次 → 追加 `\n``` `；偶数次原样返回（幂等） |
| 注释剔除 | `tokenize.generate_tokens` → 收集每行最早 `COMMENT` 的列 → 该行从该列起截断（保留换行） |
| 失败回落 | `TokenError` / `IndentationError` / `SyntaxError` → 返回原文（fail-open） |
| 计算单元 | `ClassDef`：名字命中后缀 **且** `_class_has_behavior` 为假才跳过；函数分支不变 |
| 平凡语句 | `Pass`、`Expr(Constant)`（docstring）视为平凡；其余任一语句即行为 |

## 4. 非目标

- 不提高生成预算（8192→32768 的升级策略不变，用户明确约束）。
- 不做 M2 的模块 prompt 瘦身（D-10）。
- 不改变单发路径、tree search 路径与 review 路径的失败语义：只覆盖顺序生成。
- 不为失败模块自动追加第三次生成（D-11）。
- 不改 `finish_reason` 映射、不改 LLM 客户端、不改 `execute_stage`。
- 不把证据门结果反馈给生成路径做重试（沿用 B-32 D-9）。
- 不引入第三方 Python 解析器（`tokenize`/`ast` 足够）。
- 不改 `main.py` 入口生成与修复路径的预算（归 B-29/B-30）。

## 5. 边界

- **抛异常后不写 `code_agent_log.json`**：`generate()` 未返回，日志写入点在其后。证据由 `steps.jsonl`（失败模块）与 Stage 10 的 `stage_meta.error` 承担；这是显式失败换来的可观测性折损，已在 IMPLEMENTATION 登记。
- **docstring 里的数据源仍算命中**：只剔除注释 token，不剔除字符串。数据源说明常写在 docstring，按「文档即声明」保留；真正未实现但 docstring 提到的形态仍是假阴性（F-1 的剩余面）。
- **fail-open**：文件不可 tokenize 时注释不剔除，F-1/F-5 回到旧行为；此类文件本身通常过不了入口契约。
- **F-2 是语法级判据**：`return None`、纯 `property` 也算行为；「配置类里有一个空壳方法」会被计为计算单元（宁可少误杀、不多误杀）。
- **F-3 保留括号**：`print("METRIC_DEF: acc), direction=higher")` 这类散文会把 `)` 带进名字 → `metric_mismatch`；这是「不猜截断」的代价。
- **数据源门仍是子串匹配**：`yfinance` 出现在字符串常量里也算命中；不做 API 级语义核验。
- **仅单测级验证**：未在真实模型产出与 B 站上跑过；`ModuleExtractionError` 对上游重试策略（B-8 退出码分类）的影响未在本批接线。
- **M2 未做**：模块 prompt 仍注入整份蓝图（约 36 KB）；本批不改变生成分布。

