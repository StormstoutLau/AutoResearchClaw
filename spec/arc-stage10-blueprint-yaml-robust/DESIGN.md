---
id: arc-stage10-blueprint-yaml-robust-DESIGN
type: design
version: 1.2
status: verified
date: 2026-11-26
depends: [arc-stage10-blueprint-yaml-robust-RESEARCH]
upstream: arc-stage10-blueprint-yaml-robust-RESEARCH
---

# 设计：Stage 10 蓝图 YAML 稳健化（B-32 M1 + M2）

> v1.1（2026-11-26，P-197）：新增 D-9..D-14（M2 四项门 + 折叠保护）；D-1..D-8 不变。
> v1.2（2026-11-26，P-199）：补 D-15（证据文件落点）、D-16（「成功必须有证据」五项落点），
> 并把「`<metric>: <float>` 可解析」与「真实模型产出未验」写进 §4 / §5。

## 1. 决策

| ID | 决策 | 被拒替代 | 理由 |
|---|---|---|---|
| D-1 | 列表项「行尾冒号 + 缩进续行」**折叠为一个带引号的单行标量**（原文语义保留，续行以空格连接） | ①直接删掉冒号 ②把整项转成 `\|` block scalar | 删冒号会改变原文；block scalar 需要重排缩进，风险更大。折叠后仍是同一句话，且 `safe_load` 的结果是字符串 |
| D-2 | 折叠**只作用于 block sequence 项**（`^\s*-\s`），顶层/嵌套 mapping 的 `key:` 一律不动 | 对所有行统一处理 | `verification_criteria:` 这类合法 key 一旦加引号会毁掉整棵子树 |
| D-3 | 保留现有两次尝试顺序：**先 sanitized、再原文** | 只解析 sanitized | 原文优先失败时才能暴露 sanitizer 自身的错（本轮现场正是 sanitized 未修好、原文也失败） |
| D-4 | 回退记录写 **`stage-10/codegen_decision.json`** | 写 `stage-10/decision.json`（调研 §5.1 原措辞） | [`_write_stage_meta`](../../researchclaw/pipeline/_helpers.py#L307-L329) 在阶段末**重写** `decision.json`，同写会丢证据（调研 §2.4） |
| D-5 | 结构修复重试**最多 1 次**（总 LLM 解析尝试 ≤2），`max_tokens=32768`，只追加 user 端指令 | 重试 2 次；重试时改 system 提示 | LangChain `OutputFixingParser.max_retries=1`（调研 S-3）；改 system 会让缓存/版本口径漂移 |
| D-6 | 重试成功 → **覆盖** `architecture_spec.yaml` 并以 `variant="yaml_repair"` 记账；失败 → 保留首版蓝图，只记决策文件 | 失败时删除首版蓝图 | 首版是现场证据；账本只存摘要，覆盖不丢历史（`variant` 区分） |
| D-7 | 回退原因**二值化**：`blueprint_unparsable`（`None`）/ `blueprint_structure_invalid`（有 dict 但 `_is_valid_blueprint` 为假） | 统一写 `blueprint_invalid` | 两者修法不同：前者靠解析/重试，后者靠提示约束结构 |
| D-8 | 决策落盘/记账全部 best-effort（`try/except` + `logger.warning`），**不得中断生成** | 落盘失败即抛错 | 与 B-33 同纪律：账本是投影，产物是事实 |
| D-9 | 四项门在 **Stage 10 出口执行一次**，失败即 `FAILED`，**不修补产物** | 按缺失清单再生成补齐（调研 §5.2 原措辞） | 补齐需要 topic/plan 上下文，容易造出「二次伪成功」；显式失败把证据留给 Stage 12/15 与审计（与 S-1「先校验」一致） |
| D-10 | 文件门只对带 `generation_order` 的条目生效，`optional: true` 显式豁免 | 对 `files` 全量要求 | 蓝图可声明可选辅助文件；与 M1 既有「≥2 个 generation_order」判据同口径 |
| D-11 | 指标门比较**归一化**（小写、空白/连字符→下划线）后的 `METRIC_DEF` 名与蓝图声明指标；蓝图无声明时回落到 Stage 10 的 `metric_key` | 严格字符串相等；或只比较 `config.py` 里的常量 | 站点差异是语义漂移，不是大小写；`config.py` 的常量名不统一，入口 `METRIC_DEF` 是唯一稳定契约（B-29） |
| D-12 | 数据源门**只 WARN + 写 `synthetic_data` 标志**，不阻断 | 直接 FAILED | 合成数据在部分域合法（如理论推导）；但必须留痕，供 Stage 12/15 判定 |
| D-13 | 计算门要求 ≥1 个非 `*Config/*Settings/*Params` 的顶层类或函数；`main`/`check_*`/`validate_*`/`test_*` 不计 | 按行数/文件数判复杂度 | 直接对应现场「配置自检 `rc==0`」的假阳性；行数阈值会随模型风格漂移 |
| D-14 | 折叠只对**含空白**的列表项文本生效；单 token（`- interface:`）视为 mapping key，原样保留 | 只靠「续行是否以 `- ` 开头」判断 | 单 token 几乎必然是 key；散文必然含空格。这条补上 M1 遗留的 mapping 误折风险 |
| D-15 | Stage 10 的全部证据统一写 **`stage-10/codegen_evidence.json`**；`synthetic_data` 只在该文件留痕，不写 `decision.json` | 写 `decision.json`（调研 §5.2 第 6 项原措辞） | 与 D-4 同因：`_write_stage_meta` 在阶段末重写 `decision.json`，写入即被覆盖 |
| D-16 | 「成功必须有证据」五项**分别落到不同层**：`METRIC_DEF` 存在（B-29 既有）、文件集合（本批）、指标一致（本批）、非配置计算（本批）、`<metric>: <float>` 可解析（**不在本批**，归 B-29 的 Stage 12 侧） | 五项全部在本批重写一遍 | 单一真值源：Stage 12 已有指标解析，重复造门会产生两套口径；本批只补 Stage 10 出口缺的三项 + 复用 B-29 契约 |

## 2. 接口

```python
# researchclaw/pipeline/code_agent.py
_fold_trailing_colon_items(lines: list[str]) -> list[str]   # 模块级纯函数，可单测

CodeAgent._parse_blueprint(yaml_text: str) -> dict[str, Any] | None   # 签名不变
CodeAgent._repair_blueprint_yaml(
    system: str, user: str, *, variant: str,
) -> tuple[str, dict[str, Any] | None]      # (yaml_text, blueprint)
CodeAgent._record_codegen_decision(
    *, fallback: str, reason: str, blueprint_chars: int,
) -> None                                   # 写 codegen_decision.json
```

`_phase1_blueprint` 的新流程：

```text
chat(8192) ──truncated?──> chat(32768)         # 既有逻辑不变
   │
persist(architecture_spec.yaml, variant=first|retry)   # B-33 N-1 不变
   │
_parse_blueprint(arch_spec) ──None?──> _repair_blueprint_yaml(..., variant="yaml_repair")
   │                                        │
   └── 成功 ─────────────────────────────────┘
```

```json
// stage-10/codegen_decision.json
{
  "fallback": "single_shot",
  "reason": "blueprint_unparsable",
  "blueprint_chars": 57948,
  "yaml_repair_attempted": true,
  "at": "2026-11-26T08:22:00+00:00"
}
```

```python
# researchclaw/pipeline/codegen_evidence.py（M2 新增）
EVIDENCE_NAME = "codegen_evidence.json"

evaluate_stage10_evidence(*, stage_dir, files, metric) -> EvidenceReport
write_evidence_report(stage_dir, report) -> Path
check_declared_files(blueprint, files) -> list[EvidenceFailure]
check_metric_consistency(declared_metric, files) -> list[EvidenceFailure]
check_data_source(blueprint, files) -> tuple[list[str], bool]   # (warnings, synthetic)
count_compute_units(files) -> int
check_compute_presence(files) -> list[EvidenceFailure]
```

```json
// stage-10/codegen_evidence.json
{
  "ok": false,
  "failures": [{"code": "blueprint_files_missing", "detail": "…monitor.py"}],
  "warnings": ["declared data source 'yfinance' not found in generated code"],
  "synthetic_data": true,
  "at": "2026-11-26T09:45:00+00:00"
}
```

## 3. 折叠算法（D-1/D-2/D-14）

| 步骤 | 规则 |
|---|---|
| 识别 | 行匹配 `^(?P<indent> *)-\s+(?P<text>.*\S):\s*$`，且 `text` 非空、不以引号开头、**含空白**（D-14） |
| 收集 | 向后吞并：空行，或缩进 > `len(indent)` 且不是同层新 `- ` 项；遇到更深缩进的 `- ` 视为嵌套序列，放弃折叠 |
| 产出 | `{indent}- "{folded}"`，`folded = text + ":" + " " + " ".join(续行.strip())`；内部 `"` 转义为 `\"` |
| 终止 | 遇到缩进 ≤ 项缩进的非空行（新 key 或新项） |

不满足识别条件（值非空、已带引号）→ 原样保留，交给既有 sanitizer。

## 4. 非目标

- 不做蓝图↔产物的自动补齐生成（D-9）：门只判失败，不重写产物。
- 不把 YAML 换成 JSON。
- 不对 `verification_criteria` 做语义解析。
- 不新增 prompt 资源文件：重试指令以 `sp.user + 追加段` 形式出现，`prompt_version` 沿用原版本。
- 不改变单发路径的生成逻辑（M3 的最低复杂度约束不在本批）。
- 不对数据源缺失做阻断（D-12）。
- 不校验「蓝图声明的类名是否都被实现」——只校验文件集合与「存在非配置计算单元」（D-13）。
- 不校验入口输出的 `<metric>: <float>` 是否可解析（D-16）：该项归 B-29 的 Stage 12 侧，本批不重复造门。
- 不把门结果反馈给生成路径做自动重试（D-9）：门的输出只供下游与审计读取。

## 5. 边界

- 折叠只解决「同一列表项跨行」；单 token 的 `- key:` 按 D-14 一律不折叠，若模型把散文写成单 token（无空格）则不会修复——这是为保护 mapping 付出的代价。
- 一次重试只改 `user`，模型可能重复同样错误；此时 `codegen_decision.json` 会留下证据，M2 门禁负责判失败。
- 文件门按**文件名 basename** 比对，不校验目录层级；蓝图写 `src/monitor.py` 而交付 `monitor.py` 视为满足。
- 计算门是语法级启发式：`main.py` 里内联写完全部算法且只定义 `main()` 会被判 0 个计算单元（已知误杀面，现场未见）。
- 数据源门用子串匹配，`yfinance` 出现在注释里也算命中（只做留痕，不做语义判断）。
- **四项门只在单测级验证**：未在真实模型产出上跑过（C-27 待验）；门失败后的下游行为（Stage 12/15 如何读取 `codegen_evidence.json`）未在本批接线。
- `codegen_evidence.json` 是只读证据面：`write_evidence_report` 未包 `try/except`，写盘失败会让 Stage 10 抛错——有意为之，无证据即不可验收（与 M1 决策落盘的 best-effort 不同）。
