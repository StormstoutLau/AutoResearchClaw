# P-203 postmortem 与 P-178..P-202 修复提案的异构复审与复核（2026-11-26）

> **性质**：Layer-0 复审（T3），零代码 / 零门禁变更。本文只做取证、判定与登记，不构成修复承诺。
> **对象**：① `docs/arc-b-site-stage10-postmortem-20261126.md`（397 行，含运行 A–E 全史）；② 其引用的代码实现 —— `code_agent.py`（F-6 折叠 + 修复重试）、`codegen_evidence.py`（B-32 M2 四项门）、`_code_generation.py`（出口集成）、`runner.py`（B-33 L0 + B-31a）、`step_journal.py`（B-33 L1）、`logging_setup.py` + `cli.py`（B-31a）。
> **基线**：`main` = `304c9f8`（PR #56 已合入）。
> **方法**：E2 运行时探针（场景自选，理由见 §1.2）+ E3 读码锚点 + E1 可重放单行命令。
> **边界**：① 复审者与实现者同一 agent，按 RULE-4 属**自查**，独立性仅体现在复核阶段对初判的自我证伪（本文证伪 4 项、纠正 2 项）；② 探针覆盖纯函数，未跑真实模型产出；③ 未评估性能与 B 站现场。

---

## 0. 结论摘要

| 初判 | 复核裁决 | 净结果 |
|---|---|---|
| C1 折叠重复补冒号 | **降级**：注释已说明「regex 消费了冒号」，无缺陷 | 不修 |
| C2 `nested_sequence` / `nested_mapping` 可合并 | **降级**：纯风格，两个标志语义不同（列表 vs 映射） | 不修 |
| C3 `anchor.start()` 无守卫 | **证伪**：`if anchor:` 守卫存在（L481） | 不成立 |
| C4 修复提示词硬编码 | **降级**：单次重试的窄提示，硬编码是特性不是缺陷 | 不修 |
| C5 数据源子串匹配误报 | **确认并加重**：注释里出现源名即算命中 → **假阴性（漏报缺失）** | F-1（中） |
| C6 计算单元漏统计类方法 | **原主张证伪，但暴露新缺陷**：类本身计入（读数 1）；真问题是 `*Config` 后缀一刀切（`KernelConfig` 含真实计算 → 判 0） | F-2（中） |
| C7 `_METRIC_DEF_RE` 边界不清 | **确认，但原描述写错**：`]` `)` 已排除；真正漏排的是 `(` `[` `{` `}` | F-3（低-中） |
| C8 `bool` 被 `_leaf_strings` 忽略 | **确认（低）**：`sources: {enabled: true}` 取不到任何叶子 | F-4（低） |
| C9 合成数据检测过宽 | **确认**：注释里的 `np.random` 触发 `synthetic_data=True`（假阳性） | F-5（低-中） |
| C10 计算门阈值硬编码 0 | **设计选择**：D-13 明确「≥1」，非缺陷 | 不修 |
| C11 证据门产物路径不一致 | **证伪**：`artifacts` 与 `codegen_evidence.json` 同为 `stage_dir` 相对路径 | 不成立 |
| C12 `code_version` 版本回落无警告 | **确认（低）**：`__version__ = "0"` 静默回落 | F-6（低） |
| D6 `release` 后 `fencing=1` 异常 | **证伪**：`lease.py` L228 注释明示「保留记录使 fencing 单调递增」 | 不成立 |

**净结果**：6 项低/中危需修（F-1..F-6），4 项证伪（C3/C6 原主张/C11/D6），3 项降级为风格或设计选择，1 项确认为「原主张错但另有真缺陷」。

**整体判断**：postmortem 的证据链与归因**成立**；修复实现的核心逻辑**正确**；初判的 12 条代码问题中**只有 6 条成立**，其中 3 条是初判把机制写错了（C6/C7/C11）。

---

## 1. 复审方法与取证

### 1.1 取证方式

| 手段 | 覆盖 | 说明 |
|---|---|---|
| E2 运行时探针 | C1–C12、D6 | 直接调用 `codegen_evidence` / `code_agent` 的纯函数，比对输入输出 |
| E3 读码 @`304c9f8` | 六个文件的改动 | 逐行读 diff 与上下文（含 `lease.py` 的 release 语义、`artifacts` 口径） |
| E1 可重放命令 | C5–C9 | 内联在 §3，第三方可原样重放 |

### 1.2 场景选择理由（E2 必附）

选的都是**生产形态的最近邻**，不是随机输入：
- 指标名：`auroc(delta)` / `auroc[delta]` / `auroc}delta` —— 因为指标名可能含数学记号或括号；
- 数据源：`# TODO: switch to yfinance later` —— 因为模型常在注释里提到未来要用的数据源；
- 计算单元：`class KernelConfig` 带 `compute` 方法 —— 因为「Config」后缀与「有真实计算」可以同时成立；
- bool：`sources: {enabled: true}` —— 因为 YAML 布尔是最常见的标量类型之一。

---

## 2. 初判发现（原样保留，未改写）

| No. | 主张 | 初判严重度 |
|---|---|---|
| C1 | `folded = [text + ":"]` 重复添加冒号，正则变更时易错 | 低 |
| C2 | `nested_sequence` / `nested_mapping` 可合并简化 | 低 |
| C3 | `repaired[anchor.start():]` 在 `anchor` 为 None 时越界 | 中 |
| C4 | `_YAML_REPAIR_SUFFIX` 硬编码，缺乏可配置性 | 低 |
| C5 | `check_data_source` 子串匹配会命中注释 | 中 |
| C6 | `count_compute_units` 只遍历 `tree.body`，漏统计类方法 | 中 |
| C7 | `_METRIC_DEF_RE` 边界不清，可能包含 `]` `)` `}` | 中 |
| C8 | `_leaf_strings` 忽略 `bool` | 低 |
| C9 | 合成数据检测正则过宽，命中注释 | 中 |
| C10 | 计算门阈值硬编码为 0 | 低 |
| C11 | 证据门 artifacts 含 `codegen_evidence.json` 但未写入 `experiment/` | 中 |
| C12 | `code_version` 的 `__version__ = "0"` 回落无警告 | 低 |
| D6 | `lease.json` 的 `released: true` 与 `fencing=1` 并存异常 | 低 |

---

## 3. 复核（逐条，附读数）

### 3.1 C1 / C2 / C4 / C10 → 降级，不修

```bash
python -c "import inspect,researchclaw.pipeline.code_agent as m; \
print('comment mentions colon consumed:', 'regex consumes it' in inspect.getsource(m._fold_trailing_colon_items))"
# → True   （L110-111 已写明「regex consumes it, so re-add it」）
```

**裁决**：C1 是**已有注释解释的实现细节**，不是缺陷；C2 两个标志分别对应「嵌套列表」与「嵌套映射」，合并会丢失语义；C4 的窄提示是 D-5「最多 1 次」的组成部分，可配置化属过度设计；C10 由 D-13 明确「≥1 个非 Config 计算单元」，硬编码 0 即设计本身。

### 3.2 C3 → 证伪

```bash
python -c "import inspect,researchclaw.pipeline.code_agent as m; \
src=inspect.getsource(m.CodeAgent._repair_blueprint_yaml); \
print('guard present:', 'if anchor:' in src)"
# → True
```

**裁决**：`anchor = re.search(...)` 之后紧跟 `if anchor: repaired = repaired[anchor.start():]`，`None` 时走原文本路径。初判漏读了守卫。

### 3.3 C5 → 确认并加重（F-1）

```bash
python -c "from researchclaw.pipeline.codegen_evidence import check_data_source as c; \
print(c({'data': {'source': 'yfinance'}}, {'data.py': '# TODO: switch to yfinance later\nimport numpy as np\n'}))"
# → ([], False)     ← 注释里的 yfinance 让门认为「数据源已实现」
```

**裁决**：初判说「会匹配注释」，方向正确，但后果比初判更严重——不是「产生噪声」，而是**假阴性**：真正没实现 yfinance 时，只要注释里提一句就放行。数据源门本身只 WARN，所以危害限于「该警告没发出」，但 `synthetic_data` 也会因此保持 False，下游会误认为用了真实数据。

### 3.4 C6 → 原主张证伪，暴露新缺陷（F-2）

```bash
python -c "from researchclaw.pipeline.codegen_evidence import count_compute_units as c; \
print('Monitor class:', c({'m.py': 'class Monitor:\n    def score(self, xs): return sum(xs)/len(xs)\n'}))"
# → 1               ← 类本身计入，「漏统计类方法」不成立
python -c "from researchclaw.pipeline.codegen_evidence import count_compute_units as c; \
print('KernelConfig with compute:', c({'k.py': 'class KernelConfig:\n    def compute(self, x): return x*2\n'}))"
# → 0               ← 真缺陷：*Config 后缀一刀切
python -c "from researchclaw.pipeline.codegen_evidence import count_compute_units as c; \
print('inline main:', c({'main.py': 'def main():\n    x=[i*i for i in range(10)]\n    print(sum(x))\n'}))"
# → 0               ← DESIGN §5 已登记的已知误杀面
```

**裁决**：初判「漏统计类方法」**错误**——`ClassDef` 本身计入，所以「算法全在类方法里」仍是 1 个单元，门通过。但探针暴露一个**不同的**缺陷：`_is_config_name` 只看后缀，`KernelConfig` / `ModelConfig` 这类名字即使含真实计算也被判 0。现场 `config.py` 的五个 `*Config` 确实只有字段（`deep quality` 报「0 non-dunder method」），所以**现场未命中**，但语义上「名字决定判据」是脆弱的。

### 3.5 C7 → 确认，但原描述写错（F-3）

```bash
python -c "from researchclaw.pipeline.codegen_evidence import entrypoint_metric_name as f; \
print(repr(f('print(\"METRIC_DEF: auroc(delta)\")')))"
# → 'auroc(delta'    ← 左括号保留
python -c "from researchclaw.pipeline.codegen_evidence import entrypoint_metric_name as f; \
print(repr(f('print(\"METRIC_DEF: auroc[delta]\")')))"
# → 'auroc[delta'    ← 左方括号保留
python -c "from researchclaw.pipeline.codegen_evidence import entrypoint_metric_name as f; \
print(repr(f('print(\"METRIC_DEF: auroc}delta\")')))"
# → 'auroc}delta'    ← 右花括号保留
```

**裁决**：初判说「可能包含 `]` `)` `}`」——`]` 和 `)` **确实在**排除类 `[^\s|,;)\]]+` 里，但 `( ` `[` `{` `}` **都不在**。所以真正的问题形态是「左括号 / 左方括号 / 花括号被吞进指标名」，导致后续 `normalize_metric` 比较失配 → 误报 `metric_mismatch`。严重度低-中（只在指标名含括号时触发）。

### 3.6 C8 → 确认（F-4，低）

```bash
python -c "from researchclaw.pipeline.codegen_evidence import _leaf_strings as f; \
print(f(True), f({'enabled': True}), f({'provider': 'yf', 'enabled': True}))"
# → [] [] ['yf']     ← bool 被显式跳过
```

**裁决**：成立。影响面窄：只有「数据源写成纯布尔」时才会丢掉；正常写法 `source: yfinance` 不受影响。低危。

### 3.7 C9 → 确认（F-5，低-中）

```bash
python -c "from researchclaw.pipeline.codegen_evidence import check_data_source as c; \
print(c({'data': {'source': 'yfinance'}}, {'d.py': '# np.random mentioned\nimport pandas as pd\n'}))"
# → (["declared data source 'yfinance' not found in generated code"], True)
#                     ↑ 源缺失（正确）      ↑ 但 synthetic=True 来自注释（假阳性）
```

**裁决**：成立。注释里的 `np.random` 会让 `synthetic_data=True`，从而下游误判「用了合成数据」。数据源门只 WARN，但 `synthetic_data` 是结构化字段，可能被 B-11 验收读取。

### 3.8 C11 → 证伪

```bash
python -c "import re,pathlib; \
s=pathlib.Path('researchclaw/pipeline/stage_impls/_code_generation.py').read_text(encoding='utf-8'); \
print(re.search(r'artifacts = \[[^\]]*\]', s).group(0))"
# → artifacts = ["experiment/", "experiment_spec.md"]
python -c "import pathlib; \
s=pathlib.Path('researchclaw/pipeline/stage_impls/_code_generation.py').read_text(encoding='utf-8'); \
print('writes to stage_dir:', 'write_evidence_report(stage_dir,' in s)"
# → writes to stage_dir: True
```

**裁决**：`artifacts` 的既有成员（`experiment/`、`experiment_spec.md`）与新增的 `codegen_evidence.json` **都是 `stage_dir` 相对路径**，口径一致，不存在「artifact 指 exp_dir 而文件在 stage_dir」的错配。初判的路径推断错误——这与 P-200 复审「发现 7 证伪」的结论一致（同一处）。

### 3.9 C12 → 确认（F-6，低）

```bash
python -c "import pathlib; \
s=pathlib.Path('researchclaw/pipeline/step_journal.py').read_text(encoding='utf-8'); \
i=s.find('__version__ = \"0\"'); print('fallback:', i>0, '| warning nearby:', 'warning' in s[i-300:i+300].lower())"
# → fallback: True | warning nearby: False
```

**裁决**：成立。版本读不到时静默回落 `"0"`，`code_version()` 仍能靠文件哈希区分，所以只影响可读性（日志里看到 `0+xxxxxxxx` 无从判断是哪个版本）。低危。

### 3.10 D6 → 证伪

```bash
python -c "import pathlib,inspect,researchclaw.runtime.lease as m; \
print('released' in inspect.getsource(m.Lease.release))"
# → True
grep -n "stays monotonic" researchclaw/runtime/lease.py
# → 228: The record is kept (with ``released: true``) so ``fencing`` stays monotonic
```

**裁决**：不成立，且是**有意设计**。`lease.py` L226-240 明确写明：释放时保留记录、`fencing` 不变，以便 fencing 跨持有者单调递增。`released: true` + `fencing=1` 正是该设计的结果。

---

## 4. 复核后的最终清单

| ID | 问题 | 位置 | 严重度 | 修法要点 |
|---|---|---|---|---|
| F-1 | 数据源门用子串匹配，注释里的源名算命中 → **假阴性** | [codegen_evidence.py L298-L314](../researchclaw/pipeline/codegen_evidence.py#L298-L314) | 中 | 只扫「非注释的代码行」或 AST 的 import/调用；至少剔除 `#` 之后 |
| F-2 | `_is_config_name` 按后缀一刀切，`KernelConfig` 等含真实计算也判 0 | [codegen_evidence.py L317-L342](../researchclaw/pipeline/codegen_evidence.py#L317-L342) | 中 | 后缀命中时再判「是否有非平凡方法」；或改为白名单式（只认纯 dataclass/字段类） |
| F-3 | `_METRIC_DEF_RE` 未排除 `(` `[` `{` `}`，指标名被截成半截 | [codegen_evidence.py L33](../researchclaw/pipeline/codegen_evidence.py#L33) | 低-中 | 补 `([{` 到排除类，并 `rstrip` 未闭合的括号 |
| F-4 | `_leaf_strings` 跳过 `bool` | [codegen_evidence.py L132-L151](../researchclaw/pipeline/codegen_evidence.py#L132-L151) | 低 | 显式决定：忽略并注释理由，或转 `"true"/"false"` |
| F-5 | 合成数据正则命中注释 → `synthetic_data` 假阳性 | [codegen_evidence.py L312-L313](../researchclaw/pipeline/codegen_evidence.py#L312-L313) | 低-中 | 与 F-1 同法：剔除注释行 |
| F-6 | `code_version()` 版本回落静默 | [step_journal.py L79-L83](../researchclaw/pipeline/step_journal.py#L79-L83) | 低 | 回落时 `logger.debug` 记一次 |

**不成立（记录在案，不再重开）**：C3（`if anchor:` 守卫存在）、C6 原主张（类本身计入）、C11（artifact 口径一致）、D6（fencing 单调是设计）。
**降级（风格 / 设计选择，不修）**：C1、C2、C4、C10。

---

## 5. 与既有文档的关系

| 文档 | 需要同步的点 |
|---|---|
| `spec/arc-stage10-blueprint-yaml-robust/DESIGN.md` v2.0 §5 | 已写「门只判失败、不修补」与「数据源用子串匹配」；**缺**「注释内子串算命中」（F-1/F-5）与「`*Config` 后缀一刀切」（F-2） |
| 同上 CHECKLIST v2.0 | C-23（`no_compute_unit`）未覆盖「`KernelConfig` 含真实计算」；C-37（缺失仍 WARN）未覆盖「注释命中即放行」 |
| `docs/arc-b-site-stage10-postmortem-20261126.md` §7 | 教训 6「判定与修复必须分层」成立；可补一句「判定本身的误报面需单测覆盖」 |

本次只登记，不改上述文档。

---

## 6. 未决项（四元块）

| 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|
| ~~F-1..F-6 是否立项修复~~ → **已裁决：并入 B-34** | 用户裁决（2026-11-27） | 与 B-34 的 M1-a/M1-b 合并为一批；F-1 与 F-5 共用「剔除注释行」，F-2 改「有非平凡方法则不判 Config」 | E2 + E3（见 [postmortem §F-7b.6](arc-b-site-stage10-postmortem-20261126.md)） |
| F-2 的「非平凡方法」判据 | 立项时 | 用「方法数 ≥1 且非纯 `pass`/`return`」比「类名后缀」稳 | 待核 |
| 证据门是否需要在真实产出上回归验证 | 部署 `304c9f8` 后首次重跑 | 必须；这是 C-27 唯一的关闭路径 | 待核 |

---

## 7. 边界

- 复审者与实现者同一 agent（RULE-4）：本文不是独立第三方审查；独立性仅体现在复核阶段对 4 项初判的自我证伪与 2 项的机制纠正（C6/C7）。
- E2 探针覆盖纯函数，未跑真实 LLM 产出；`synthetic_data` / `metric_mismatch` 在真实 main.py 上的触发率未知。
- 未评估性能（`count_compute_units` 对每文件重复 `ast.parse`，与既有校验重复解析）。
- 未复核 postmortem 中的远端读数本身（依赖 §8A 的复现命令），只复核其**结论与代码的一致性**。
