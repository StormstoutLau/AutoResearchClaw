---
id: arc-stage10-blueprint-yaml-robust-DESIGN
type: design
version: 2.0
status: verified
date: 2026-11-26
depends: [arc-stage10-blueprint-yaml-robust-RESEARCH]
upstream: arc-stage10-blueprint-yaml-robust-RESEARCH
---

# 设计：Stage 10 蓝图 YAML 稳健化（B-32 M1 + M2 + M3）

> v1.1（2026-11-26，P-197）：新增 D-9..D-14（M2 四项门 + 折叠保护）；D-1..D-8 不变。
> v1.2（2026-11-26，P-199）：补 D-15（证据文件落点）、D-16（「成功必须有证据」五项落点），
> 并把「`<metric>: <float>` 可解析」与「真实模型产出未验」写进 §4 / §5。
> v1.3（2026-11-26，P-201）：按 P-200 复审把 F-1..F-4 与 N-1 登记为 **§5.1 已知边界**（不修代码）。
> v2.0（2026-11-26，P-202）：按 §5.1 立项硬化——新增 D-17..D-21 关闭全部五项边界，§5.1 转为**已关闭**表。

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
| D-17 | 指标名**优先取自 `print(...)` 的字面实参**（AST 遍历 `Call.args` 的 `Constant`），无 `print` 时回落「逐行扫描且跳过 `#` 注释行」；捕获类改为「到空白或 `\|`、`,`、`)`、`]` 为止」，再 `rstrip` 标点与引号 | 继续用文件级正则首匹配（现状）；或只用 `tokenize` 过滤注释 | 注释与 docstring 在 AST 里**不进入** `Call.args`（调研 A-1/A-2），是结构性排除而非启发式；纯 `tokenize` 方案需自己重建语句边界，代价更高。宽捕获类解决 `50%-winrate`/`auroc:delta` 被截断 |
| D-18 | 数据源声明**递归取叶子字符串**（dict/list 逐层下钻，深度上限 4），**禁止 `str(容器)`** | 保留 `str(v)` 取 repr；或用 `json.dumps` 后整串匹配 | `str({...})` 产出 `"{'provider': 'x'}"`，与产物里的 `x` 永不相等 → 每条都报虚假 WARN（调研 A-6/A-7：容器应递归到叶子） |
| D-19 | 折叠守卫改两条：① 列表项文本已含 `": "` → 视为 `key: value`，不折叠；② 续行形如 `k: v` / `k:` → 视为 mapping，整项不折叠 | 保留「文本是否含空白」单判据；或对 mapping 强行加引号 | YAML 里 `- some key:` + 缩进 `nested: value` 解析为 **mapping**（调研 A-3），折叠会把结构压成字符串；`- name: foo bar:` 是值以冒号结尾的键值对（A-4），应交给既有 sanitizer |
| D-20 | 修复重试**无围栏时对齐到第一个顶层 `files:` 行**再解析 | 保留 `text.strip()` 全文解析；或要求模型必须围栏后直接放弃 | 无尾冒号的散文会在根层形成裸标量，`safe_load` 抛 `ScannerError`（P-200 §3.3）；LangChain 的标准做法是「剥围栏后解析并容忍非围栏输入」（调研 A-5） |
| D-21 | 证据门以 **`experiment/` 磁盘产物为准**（`delivered_dir`），内存映射仅作缺省回落 | 继续只读内存 `files`；或两者取交集 | Stage 12 实际执行的是磁盘文件（调研 A-8）；`llm is None` + `--from-stage` 重跑时二者可背离，读 dict 会误判 |

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

```python
# researchclaw/pipeline/codegen_evidence.py（M3 变更点）
entrypoint_metric_name(code: str) -> str          # 签名不变；内部改为 AST 优先（D-17）
collect_delivered(files, delivered_dir=None) -> dict[str, str]    # 新增（D-21）
evaluate_stage10_evidence(
    *, stage_dir, files, metric, delivered_dir=None,              # 新增关键字（D-21）
) -> EvidenceReport
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

### 5.1 已知边界（P-200 登记 → P-202 全部关闭）

> 依据 [P-194..P-199 合入内容复审与复核](../../docs/arc-p194-p199-heterogeneous-review-20261126.md) §4。五项均经探针确认；P-202 按本节立项修复，**当前状态：全部关闭**（对应决策与验收项见末两列）。

| ID | 边界 | 现象（P-200 探针读数） | 关闭方式 | 决策 / 验收 |
|---|---|---|---|---|
| F-1 | 指标名取**全文首个** `METRIC_DEF:` 匹配，且字符类在 `:`/`%` 处截断 | 注释行 `# METRIC_DEF: old_metric` → `'old_metric'`；docstring → `'auroc_delta.'`；`50%-winrate` → `'50'` | 改走 `print(...)` 字面实参（AST），回落时跳过注释行；捕获类放宽后 `rstrip` | D-17 / C-29..C-34 |
| F-2 | 数据源 dict 值被 `str()` 成 repr；二重嵌套漏采 | `data.sources: [{provider: x}]` → `"{'provider': 'x'}"`（虚假 WARN）；`data.sources.primary.provider` → `[]` | 递归取叶子字符串（深度上限 4），禁止 `str(容器)` | D-18 / C-35..C-38 |
| F-3 | 折叠守卫只判「是否含空白」，多词 key + 嵌套 mapping 被误折 | `- some key:` + `nested: value` → `- "some key: nested: value"` | 双守卫：文本含 `": "` 不折；续行形如 `k: v` 视为 mapping | D-19 / C-39..C-42 |
| F-4 | 无围栏修复文本若含**无尾冒号**散文，击穿 `safe_load` | `Sure, I fixed the indentation.\nfiles:` → `ScannerError`；带尾冒号的散文无害 | 无围栏时对齐到首个顶层 `files:` 行 | D-20 / C-43..C-44 |
| N-1 | 证据门读 `files` dict，而非磁盘 `experiment/` 实际产物 | `files` 无 main.py + `exp_dir` 残留旧 main.py → 误判 `metric_not_printed` | 门改以 `delivered_dir` 磁盘产物为准，映射仅缺省回落 | D-21 / C-45..C-47 |

**影响评估（关闭前）**：F-1/F-3 会让门在「应通过时误判失败」或反之；F-2 只产生噪声 WARN；F-4/N-1 需窄组合才可达。四类失败都是**显式失败或显式 WARN**，不会静默放过退化产物——这是「宁可误杀、不放过」选择的代价。
**再评估触发**：① B 站 Stage 10 重跑出现 `metric_mismatch`/`blueprint_files_missing` 而人工核对产物实为一致；② `codegen_decision.json` 出现 `yaml_repair_attempted=true` 但 `reason=blueprint_unparsable`；③ A7-1 soak 期间出现证据门误判。关闭后这三条仍保留，用于检出**新**误判形态。
