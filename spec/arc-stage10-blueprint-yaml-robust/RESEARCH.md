---
id: arc-stage10-blueprint-yaml-robust-RESEARCH
type: design
version: 1.1
status: verified
date: 2026-11-26
depends: [arc-stage10-blueprint-fallback]
upstream: arc-master-roadmap
---

> v1.1（2026-11-26）：补 §4.1 M2 四项结构/语义门与折叠保护（P-197）；M1 结论不变。

# 调研：Stage 10 蓝图 YAML 稳健化（B-32 M1）

> **背景**：B 站 Stage 10 的蓝图 57 948 字符解析失败 → `blueprint=None` → 顺序生成被跳过 → 单发只产出 `config.py` + 配置校验入口。全程只留下一条 `logger.info`，默认日志级别下不可见。现场全史见 [B 站 Stage 10 排查、修复与故障分析](../../docs/arc-b-site-stage10-postmortem-20261126.md)，方案分层见 [蓝图 YAML 失效与单发回退退化调研](../../docs/arc-stage10-blueprint-fallback-20261126.md)。
> **本批范围**：只做该调研 §5.1 的 M1 三项（预处理、结构修复重试、回退显式化）。M2 的结构/语义门不在本批。

## 0. 结论

1. 失败形态可**本地一字不差复现**：block sequence 里的自然语言列表项以 `:` 结尾时，PyYAML 把它读成「key + 空值」，下一行缩进续写被当作嵌套内容 → `ScannerError: could not find expected ':'`（§1.1）。
2. 现有 sanitizer 的分隔符正则是 `:\s`（要求冒号**后跟空白**），因此「行尾冒号」整行原样放行，属于**漏判**而非误判（§2.1）。
3. 解析失败后没有任何结构修复重试，直接置 `blueprint=None` 并静默降级（§2.2）。
4. 社区做法一致指向 **「严格解析优先 → 启发式/定向修复 → 重新校验」**，且修复次数有上限（§3，源码级锚点 3 条）。
5. 因此 M1 = ①补列表项行尾冒号折叠 ②一次窄提示 YAML 重试 ③回退写盘并 `logger.warning`。三项都可单测，不触 M2 的结构门。

## 1. 现场证据（E1/E2）

### 1.1 本地复现（E1，可重放）

对 B 站失败片段做最小复现：

```text
ScannerError : while scanning a simple key
  in "<unicode string>", line 3, column 5:
        HiddenStateTauKLMonitor override ...
        ^
could not find expected ':'  (line 4)
```

与 B 站 `stage-10/code_agent_log.json` 的报错**文本一致**（现场为 `line 1055`，因整篇蓝图更长）。复现命令：

```bash
python -c "import yaml;s='''verification_criteria:\n  - All condition classes have DIFFERENT core method implementations:\n    HiddenStateTauKLMonitor overrides score with tau-rescaled KL;\n''';yaml.safe_load(s)"
```

### 1.2 现场产物对账（E1）

| 维度 | 蓝图声明 | 实际交付 |
|---|---|---|
| 文件 | 5 个带 `generation_order` | 2 个 `.py`（`config.py`、`main.py`） |
| 类 | 6 个 `class:`、32 处 `Monitor` | 仅 5 个 `*Config`，0 个 monitor |
| 主指标 | `auroc_frechet_adjoint_minus_tau_kl` | 窗口级 F1 |
| 数据 | `source: yfinance`，6 标的 | `np.random.default_rng` 合成 |

## 2. 机制解剖（E3 @HEAD）

### 2.1 sanitizer 漏判（根因）

[`_parse_blueprint`](../../researchclaw/pipeline/code_agent.py#L405-L502) 逐行处理，列表项剥掉 `- ` 后用 `re.search(r":\s", inner)` 找 key 分隔符。冒号在行尾时 `m is None` → 整行原样保留 → 非法 YAML 通过预处理。同段逻辑还漏了「续行属于同一列表项」这一事实：即使给首行加引号，后续更深的裸标量仍会被判非法。

### 2.2 无结构修复重试

[`_phase1_blueprint`](../../researchclaw/pipeline/code_agent.py#L266-L327) 在 `_parse_blueprint` 返回 `None` 后只记一条 INFO，随即返回 `(arch_spec, None)`；[`generate`](../../researchclaw/pipeline/code_agent.py#L191-L219) 因 `blueprint is None` 落入单发分支。

### 2.3 回退不可见

单发分支只调用 `_log_event`（[L212-216](../../researchclaw/pipeline/code_agent.py#L212-L216) → [`_log_event`](../../researchclaw/pipeline/code_agent.py#L1609-L1612) 走 `logger.info`）。全仓无 `basicConfig`，root 默认 WARNING，该行被丢弃——这也解释了现场日志里直到 `logger.warning` 出现才有信息。

### 2.4 `decision.json` 会被阶段末尾覆盖

[`_write_stage_meta`](../../researchclaw/pipeline/_helpers.py#L307-L329) 在阶段结束时**重写** `stage-10/decision.json`。因此 CodeAgent 若把回退记录写进同名文件，会在 Stage 10 收尾时被覆盖，必须在实现中改用不冲突的文件名（D-4）。

## 3. 社区源码级证据锚点

| ID | 来源（T1 源码 / T2 官方文档） | 原文要点 | 验证状态 |
|---|---|---|---|
| S-1 | `json_repair` README（github.com/mangiucugna/json_repair，main，2026-11-26 抓取）L116 | "By default, `json_repair` first tries the standard-library JSON loader and only falls back to the repair parser when strict JSON parsing fails." | ✅ 原文已抓取 |
| S-2 | 同上 L54-56、L117-119 | `repair_json(bad_json_string)`；"If the string was super broken this will return an empty string"；`skip_json_loads=True` 显式跳过严格解析 | ✅ 原文已抓取 |
| S-3 | LangChain API 参考 `OutputFixingParser`（langchain.output_parsers.fix） | "Wrap a parser and try to fix parsing errors."；`max_retries: int = 1`；`retry_chain` | ✅ API 原文已抓取；**未回 `fix.py` 行号**（源码页抓取为空，降级到官方 API 文档） |
| S-4 | 本仓 `_parse_blueprint` / `_phase1_blueprint` | §2.1–§2.3 行号 | ✅ E3（本批 HEAD，测试同步锁定） |

**提炼出的三条可迁移纪律**：
1. **严格解析先行，修复只作兜底**（S-1）：不要一上来就改写文本；先 `safe_load` 原文，失败才进入修复。
2. **修复必须可判失败**（S-2）：修复器要能返回「修不了」，而不是伪造一个空结构。
3. **修复次数有上限、修复后必须复验**（S-3 `max_retries=1`）：本研究据此定为「最多 1 次窄提示重试 + 重新解析」。

## 4. 方案（M1）

| 项 | 内容 | 依据 |
|---|---|---|
| L1 | 列表项行尾冒号：把该项及其缩进续行折叠成一个带引号的单行标量 | §1.1 复现 + S-1 的「先修形态」 |
| L2 | 解析失败 → 一次「只输出合法 YAML」的窄提示重试（32768），成功后覆盖落盘并 `variant=yaml_repair` 记账 | S-3 的 `max_retries=1`、B-30 的「换额度而非同额度重试」 |
| L3 | 回退显式化：`logger.warning` + `stage-10/codegen_decision.json`（避免 §2.4 覆盖） | 现场日志不可见 + D-4 |

### 4.1 M2：四项结构/语义门（P-197）

M1 只保证「合法蓝图能进顺序生成」，不能保证「产物实现了蓝图」——现场仍是「声明 5 文件、交付 2 文件、指标名与数据源全漂移」却无门禁报错（§1.2）。M2 在 Stage 10 出口补四项判据（依据调研 §5.2）：

| 门 | 判据 | 失败后果 |
|---|---|---|
| 文件集合 | 蓝图带 `generation_order` 且非 `optional` 的文件名 ⊆ 交付文件名 | FAILED |
| 指标一致 | 入口 `METRIC_DEF` 名 == 蓝图声明指标（缺省回落到 Stage 10 的 `metric_key`），归一化比较 | FAILED |
| 数据源 | 蓝图 `data.source` 等声明在产物文本中出现；缺失 → WARN + `synthetic_data` 标志 | 不阻断 |
| 非配置计算 | 至少 1 个非 `*Config`/`*Settings`/`*Params` 的类或函数 | FAILED |

另补 M1 遗留保护：列表项文本**不含空白**（如 `- interface:`）时视为 mapping key，不折叠——否则会把嵌套 mapping 折成字符串。

证据锚点复用 §3：`json_repair` 的「先严格校验、失败才修复」对应「先在出口校验、不猜产物」；`OutputFixingParser` 的 `max_retries=1` 对应「门只报失败、不做无限修补」。

## 5. 未决项（四元块）

| 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|
| 蓝图↔产物/指标/数据源的结构门是否补齐 | M2 立项时 | 补齐（文件集合 ⊆、指标名相等、非 Config 计算类 ≥1） | 待核（调研 §5.2 已列判据） |
| 窄提示重试的实际成功率 | 首次 B 站重跑 Stage 10 后读 `codegen_decision.json` | 未知；即使失败也比静默降级好 | 待核 |
