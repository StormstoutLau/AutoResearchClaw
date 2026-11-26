# P-194..P-199 合入内容异构复审与复核（2026-11-26）

> **性质**：Layer-0 复审（T3），零代码 / 零门禁变更。本文只做取证、判定与登记，不构成修复承诺。
> **对象**：commit `8744c84`（`feat(stage10): blueprint YAML robustness, evidence gates, runtime log visibility`），PR #55，merge commit `3eea3f1`。
> **范围**：`researchclaw/pipeline/code_agent.py`、`researchclaw/pipeline/codegen_evidence.py`（新增）、`researchclaw/pipeline/stage_impls/_code_generation.py`、`researchclaw/runtime/logging_setup.py`（新增）、`researchclaw/cli.py`、`researchclaw/pipeline/runner.py`。
> **方法**：E2 运行时探针（场景自选，理由见 §1.2）+ E3 读码锚点（@`8744c84`）。**未做**：真实模型产出上的门行为验证、B 站部署验证。
> **边界**：① 复审者与实现者为同一 agent，按 RULE-4 属「自查」而非独立异构审查——本文的独立性来自**结论层面的自我反驳**（§3 证伪 2 项），不代表第三方独立；② 探针为一次性脚本，已删除的可重放命令内联在 §3，未保留脚本文件；③ 未覆盖性能与内存面。

---

## 0. 结论摘要

| 项 | 初判发现 | 复核裁决 | 净结果 |
|---|---|---|---|
| 1 | 数据源递归漏报 | **收窄**：列表项不丢，但 dict 值被 `str()` 成 repr；二重嵌套才真丢 | F-2（中） |
| 2 | 指标正则过严 | **确认并加重**：真正风险是「全文首匹配」，注释/docstring 可劫持 | F-1（中） |
| 3 | YAML 修复提取过宽 | **收窄**：仅「无尾冒号的散文」击穿解析，带冒号的散文无害 | F-4（低） |
| 4 | `force=True` 清外部 handler | **降级**：技术属实，但 DESIGN §5 已登记且仅 1 个调用方 | 已登记边界，不修 |
| 5 | 单 token 判定不准 | **确认**：多词 key + 嵌套 mapping 被误折 | F-3（低-中） |
| 6 | 只统计顶层、漏类方法 | **证伪**：类本身即计入，`Monitor` 得 1 | 不成立 |
| 7 | artifacts 路径不一致 | **证伪**：四类 artifact 均为 `stage_dir` 相对路径 | 不成立 |
| N-1 | —（复核中新增） | 证据门读 `files` dict 而非磁盘产物 | N-1（低） |

**净结果**：4 项需修（F-1/F-2/F-3/F-4），1 项新增低危（N-1），1 项降级为已登记边界，2 项证伪。

---

## 1. 复审方法与取证

### 1.1 取证方式

| 手段 | 覆盖 | 说明 |
|---|---|---|
| E3 读码 @`8744c84` | 六个文件全部改动 | 逐行读 diff 与上下文（含 `_ensure_entrypoint` 的 dict/磁盘同步、`_write_stage_meta` 的重写语义） |
| E2 运行时探针 | 发现 1/2/3/5/6/7 + 新增 N-1 | 直接调用 `codegen_evidence` / `code_agent` 的纯函数，比对输入输出 |
| E1 可重放命令 | 发现 2/3/5/6 | 内联在 §3 各条，第三方可原样重放 |

### 1.2 场景选择理由（E2 必附）

选的是**现场真实形态**与其最近邻反例，不是随机输入：
- 数据源：`data.sources: [{provider: ...}]` 取自 B 站蓝图风格（多标的列表）；
- 指标：`auroc:delta` / `50%-winrate` / 注释行 / docstring 四种，因为 B-29 只要求字符串含 `METRIC_DEF`；
- 折叠：`- some key:` + 嵌套 mapping（多词 key 是 D-14 未覆盖的盲区）、`- name: foo bar:`（值以冒号结尾的 mapping）。

---

## 2. 初判发现（原样保留，未改写）

| No. | 主张 | 初判严重度 |
|---|---|---|
| 1 | `_find_data_sources` 列表递归有漏洞，嵌套 dict 会漏报 | Critical |
| 2 | `_METRIC_DEF_RE` 不匹配含冒号指标名，会截断 | Critical |
| 3 | `_repair_blueprint_yaml` 无围栏时把散文纳入，导致解析失败 | High |
| 4 | `configure_logging(force=True)` 清除外部 handler | Medium |
| 5 | 折叠的单 token 判定不准 | Medium |
| 6 | `count_compute_units` 只统计顶层，类方法不计 | High |
| 7 | 证据门失败时 artifacts 路径不一致 | Low |

---

## 3. 复核（逐条，附读数）

### 3.1 发现 1 → 收窄为 F-2

```bash
python -c "from researchclaw.pipeline.codegen_evidence import _find_data_sources; \
print(_find_data_sources({'data': {'sources': [{'provider': 'yfinance'}, {'provider': 'worldbank'}]}}))"
# → ["{'provider': 'yfinance'}", "{'provider': 'worldbank'}"]
python -c "from researchclaw.pipeline.codegen_evidence import _find_data_sources; \
print(_find_data_sources({'data': {'sources': {'primary': {'provider': 'yfinance'}}}}))"
# → []
```

**裁决：主张的机制写错了，但缺陷存在。** 列表项**没有漏报**——`_collect_sources` 对 dict 值取 `value.values()`，把整个 dict 的 `repr` 当成了「数据源字符串」（`"{'provider': 'yfinance'}"`），随后 `check_data_source` 拿它去产物里做子串匹配必然失败，于是**每条都会产生一条虚假 WARN**。真正漏报的是「dict 里再套 dict」（深度 3 且 `_collect_sources` 不递归）。因数据源门只 WARN 不阻断，严重度中。

### 3.2 发现 2 → 确认并加重（F-1）

```bash
python -c "from researchclaw.pipeline.codegen_evidence import entrypoint_metric_name as f; \
print(repr(f('print(\"METRIC_DEF: auroc:delta\")')))"
# → 'auroc'
python -c "from researchclaw.pipeline.codegen_evidence import entrypoint_metric_name as f; \
print(repr(f('# METRIC_DEF: old_metric')))"
# → 'old_metric'   （整行被注释，仍被当作指标名）
```

**裁决：成立，且初判低估了风险形态。** 字符类 `[A-Za-z0-9_.\-]` 确实在 `:` 与 `%` 处截断（`50%-winrate` → `'50'`），但更常见的是**全文首个匹配**：B-29 只要求 `"METRIC_DEF" in code`，不要求它是 `print` 的实参，于是一行被注释掉的旧指标、或 docstring 里的示例（读数 `'auroc_delta.'`，带句点）都能劫持判定。这会让指标一致门在**真一致时误报 mismatch**，或反过来拿注释里的值放行。

### 3.3 发现 3 → 确认为更窄的形态（F-4）

```bash
python -c "import yaml; d=yaml.safe_load('Here is the fixed YAML:\nfiles:\n  - name: main.py\n    generation_order: 1\n'); print(list(d), 'files' in d)"
# → ['Here is the fixed YAML', 'files'] True      ← 带冒号的散文只是同级 key，解析成功
python -c "import yaml; yaml.safe_load('Sure, I fixed the indentation.\nfiles:\n  - name: main.py\n')"
# → ScannerError                                    ← 无冒号的散文击穿解析
python -c "import yaml; yaml.safe_load('Here is the fix.\nI quoted values.\nfiles:\n  - name: main.py\n')"
# → ScannerError                                    ← 多行无冒号散文同样击穿
```

**裁决：主张的后果写错了，但缺陷存在、形态更窄。** 带尾冒号的散文行只是与 `files` 平级的 key（值为 null），`_parse_blueprint` 仍能找到顶层 `files`，**修复实际会成功**；真正导致失败的是**无尾冒号的句子**（`Sure, I fixed the indentation.`）或多行散文——它们在根层形成裸标量，`safe_load` 抛 `ScannerError`，修复被判失败并回落。即：不会造出错误蓝图，只会**在模型不守「只输出围栏」时静默损失一次修复机会**。严重度低。

### 3.4 发现 4 → 降级为已登记边界

```bash
python -c "import io,logging; from researchclaw.runtime.logging_setup import configure_logging; \
r=logging.getLogger(); h=logging.StreamHandler(io.StringIO()); r.addHandler(h); \
configure_logging('INFO', None, stream=io.StringIO()); print(h in r.handlers)"
# → False
```

**裁决：技术事实成立，但不修。** ① DESIGN v1.1 §5 已明文登记「会关闭此前安装的 root handler；若将来有人嵌入本包并自建 handler，需改 `force=False`」；② 复核确认 `configure_logging` 在生产代码中**只有 `cmd_run` 一个调用方**（全仓 grep），当前无被破坏对象。按「不为假设需求加配置」的纪律，维持现状。

### 3.5 发现 5 → 确认（F-3）

```bash
python -c "from researchclaw.pipeline.code_agent import _fold_trailing_colon_items as f; \
print(f(['  - some key:', '    nested: value']))"
# → ['  - "some key: nested: value"']
python -c "from researchclaw.pipeline.code_agent import _fold_trailing_colon_items as f; \
print(f(['  - name: foo bar:', '    order: 1']))"
# → ['  - "name: foo bar: order: 1"']
```

**裁决：成立。** D-14 的守卫是「text 不含空白则不折」，因此：单 token key（`- interface:`）被正确保护，但**多词 key + 嵌套 mapping 会被折成字符串**，`- name: foo bar:`（mapping 值以冒号结尾）同样被折。两者的判别式应改为「text 内是否已含 `: `（即已经是 key: value）」而非「是否含空白」。

### 3.6 发现 6 → 证伪

```bash
python -c "from researchclaw.pipeline.codegen_evidence import count_compute_units as c; \
print(c({'monitor.py': 'class Monitor:\n    def score(self, xs):\n        return sum(xs)/len(xs)\n'}))"
# → 1
```

**裁决：不成立。** 类名本身计入（`Monitor` 非 `*Config`），所以「计算全在类方法里」仍是 1 个计算单元，门通过。只有「纯 Config 类 + `main()`」这种配置自检形态才得 0——这正是门要拦的目标，行为正确。

### 3.7 发现 7 → 证伪

**裁决：不成立。** `artifacts` 的既有取值（`experiment/`、`experiment_spec.md`、`validation_report.md`）与新增的 `codegen_evidence.json` **都是 `stage_dir` 相对路径**，口径一致；`write_evidence_report` 也写在 `stage_dir`。不存在「artifact 指 exp_dir 而文件在 stage_dir」的错配。

### 3.8 复核新增：N-1 证据门读 dict 而非磁盘

```bash
python -c "import tempfile,pathlib;from researchclaw.pipeline.codegen_evidence import evaluate_stage10_evidence as e; \
d=pathlib.Path(tempfile.mkdtemp()); (d/'architecture_spec.yaml').write_text('files:\n  - name: main.py\n    generation_order: 1\nprimary_metric: auroc\n'); \
(d/'main.py').write_text('print(\"METRIC_DEF: auroc\")'); \
r=e(stage_dir=d, files={'config.py': 'x=1\n'}, metric='auroc'); print([f.code for f in r.failures])"
# → ['blueprint_files_missing', 'metric_not_printed', 'no_compute_unit']
```

**裁决：成立（低危）。** 门的输入是 `files` dict，而 Stage 10 实际交付的是磁盘 `experiment/`。正常路径下二者同步（`_ensure_entrypoint` 会 `files["main.py"] = code`，写盘循环逐文件落盘），所以**新跑不会触发**。可达路径只有一条窄组合：`llm is None` + `files` 里没有 `main.py` + `experiment/` 残留上一轮 `main.py`（`--from-stage` 重跑）。此时入口契约检查读磁盘通过，证据门读 dict 判失败。建议：门改成读 `exp_dir`（即「实际要发的东西」），或在调用点断言二者同步。

---

## 4. 复核后的最终清单

| ID | 问题 | 位置 | 严重度 | 修法要点 |
|---|---|---|---|---|
| F-1 | `METRIC_DEF` 全文首匹配 + 字符类截断 | [codegen_evidence.py L198-L205](../researchclaw/pipeline/codegen_evidence.py#L198-L205) | 中 | 优先匹配 `print(...)` 实参；忽略注释行；字符类补 `%/@:` 或改用「到 `\|` 前」截断 |
| F-2 | 数据源 dict 值被 `str()` 成 repr；二重嵌套漏采 | [codegen_evidence.py L109-L138](../researchclaw/pipeline/codegen_evidence.py#L109-L138) | 中 | dict 值递归取叶子字符串，不做 `str(dict)`；`_collect_sources` 受 depth 约束 |
| F-3 | 折叠误判多词 key + 嵌套 mapping | [code_agent.py L93-L97](../researchclaw/pipeline/code_agent.py#L93-L97) | 低-中 | 守卫改为「text 已含 `: ` 则不折」，并补两条用例 |
| F-4 | 无围栏修复文本含**无尾冒号**的散文，击穿 `safe_load` | [code_agent.py L459-L461](../researchclaw/pipeline/code_agent.py#L459-L461) | 低 | 退化为「从第一个 `^files:` 起截取」再解析 |
| N-1 | 门读 `files` dict 而非磁盘产物 | [_code_generation.py L2072-L2076](../researchclaw/pipeline/stage_impls/_code_generation.py#L2072-L2076) | 低 | 读 `exp_dir` 或断言 dict/磁盘一致 |

**不成立（记录在案，不再重开）**：发现 6（类本身计入计算单元）、发现 7（artifacts 口径一致）。
**降级（已登记边界，不修）**：发现 4（`force=True` 清 handler；DESIGN v1.1 §5 已写明，且仅 `cmd_run` 调用）。

---

## 5. 与被审文档的关系

| 文档 | 需要同步的点 |
|---|---|
| `spec/arc-stage10-blueprint-yaml-robust/DESIGN.md` v1.2 §5 | 已写「折叠对单 token 不折」；**缺**「多词 key + 嵌套 mapping 会被误折」（F-3 暴露的盲区） |
| 同上 §5 | 已写「门只在单测级验证」；**缺**「门读 dict 而非磁盘」（N-1） |
| `spec/arc-stage10-blueprint-yaml-robust/CHECKLIST.md` v1.1 | C-18/C-19（指标门）未覆盖「注释/docstring 劫持」（F-1）；C-14..C-17（文件门）未覆盖 stale `exp_dir`（N-1） |
| `spec/arc-runtime-log-visibility/DESIGN.md` v1.1 §5 | 已写 `force=True` 边界与「当前无此调用方」；复核确认属实，**无需改** |

本次只登记，不改上述文档——修哪几项、是否并入下一批，见 §6。

---

## 6. 未决项（四元块）

| 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|
| F-1..F-4 + N-1 是否作为修复批立项 | 用户裁决或下一次 Stage 10 现场失败命中任一项 | F-3 与 F-1 优先（影响判定正确性）；F-2/F-4/N-1 次之 | E2（本批探针）+ E3 |
| F-3 的守卫改写是否会回归现场形态 | 补用例后跑 `test_blueprint_yaml_repair.py` | 用「`: ` 已存在则不折」+ 保留单 token 规则，双守卫 | 待核 |
| 证据门改读磁盘是否改变 `codegen_evidence.json` 语义 | 立项时 | 应改为「校验要发的产物」，dict 仅作参考 | 待核 |

---

## 7. 边界

- 复审者与实现者同一 agent（RULE-4）：本文不是独立第三方审查；独立性仅体现在复核阶段对 2 项主张的自我证伪。
- E2 探针覆盖纯函数，未覆盖 `evaluate_stage10_evidence` 在真实 LLM 产出上的端到端行为。
- 未评估性能（`count_compute_units` 对每文件 `ast.parse` 一次，与既有校验重复解析）。
- 未检查文档面（`spec/**`）的文字一致性——那属 Step 8，不在代码复审范围。
