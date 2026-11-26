# B 站 Stage 10 排查、修复与故障分析完整记录（2026-11-26）

> **性质**：Layer-0 事后分析（postmortem），零代码 / 零门禁变更。本文只做取证、归因与决策回溯，不新增实施承诺。
> **范围**：B 站（`scott-lau-GTR-Pro.local`）run 目录 `~/arc-runs/g7-baseline`，topic 为「LNN 内部动力学信号的分层漂移监测：τ-KL 粗筛与 Fréchet 伴随状态变点检测的金融时序比较研究」，Stage 10（CODE_GENERATION）自 2026-11-25 13:48Z 起的全部尝试（运行 A–E，**E 已于 11-26 11:50:39Z 失败终态**）。
> **证据来源**：`attempts/stage-10/attempt-{1,2,3,4}.json`、`stage-10/code_agent_log.json`、`stage-10/architecture_spec.yaml`、`stage-10/stage_health.json`、`stage-10/agent_runs/`、`stage-10/experiment/`、`stage-10/ablation_warning.json`、`stage-10/experiment_spec.md`、`stage-10/decision.json`、`cost_log.jsonl`、`events.jsonl`、`checkpoint.json`、`lease.json`、`/tmp/p19{1,2}_stage12.log`。
> **方法**：读码锚点 + 远端文件采样 + 本地测试复跑。未做受控实验，未改动远端任何源码。
> **边界**：① 单一 run、单一 topic；② 时间戳统一 UTC，括号内为 B 站本地时间（UTC+8）；③ attempt 编号为跨 run 全局计数，不等同于「某一次 stage 重试」；④ 本文不评价 topic 本身的科学价值。

---

## 0. 结论摘要

1. **Stage 10 在 24 小时内失败 5 次，根因是 5 个不同缺陷的串联**，不是单一 bug：出口门缺失 → 截断/围栏 → repair 整体替换 → 文件提升 → 入口生成无兜底 → 蓝图 YAML 失效导致单发退化。
2. **每修一个，下一个才暴露**。P-178、P-190、P-191、P-192 四次修复各自在 B 站现场被日志证实生效，但 Stage 10 仍未通过。
3. **运行 E 的终态（2026-11-26 11:50:39Z）把阻塞点固定为「实验内容不成立」**：Stage 10 在 **15 769.77 s（4 h 22 m 50 s）** 后 `exit_code=75` 失败，3 次内部重试全部被「主题-实验对齐门」否决。**这是护栏在正确工作，不是护栏误报。**
4. **运行 E 同时给出了两条正反证据**：① **反证**——本轮蓝图（36 831 字符）**解析成功**，`Parsed blueprint: 4 files` + `Phase 2: Sequential generation (blueprint-guided)`，F-6 的 YAML 缺陷**未复发**；② **正证**——`data.py` 生成后**提取为空**（不是"模块太大写不下"，见 §F-7b 订正）、被 `synthetic_finance.py` 顶替，`main.py` 112 行停在 `df` 且无 `METRIC_DEF`。真正的瓶颈是**每模块调用的截断提取兜底缺失**，不是生成预算。
5. **结构性缺口已全部在本地修复并合入 `main`（`304c9f8`），但一个都没有部署到 B 站**：B-32（M1 yaml 折叠 + M2 四项证据门 + M3 硬化，P-194/P-197/P-202）、B-31a（日志可见性，P-195/P-198）、B-33 M1（阶段内断点，P-193）。现场 `~/AutoResearchClaw-main` 中 `logging_setup.py` / `codegen_evidence.py` / `step_journal.py` **均不存在**，`_write_stage_start` 与 `_fold_trailing_colon_items` 零命中。
6. **成本已可量化**：5 次运行 Stage 10 墙钟合计约 **12.7 小时**（1 491 + 13 007 + 14 564 + 约 9 400 + 15 770 s），运行 E 单轮 91 次 LLM 调用；`code_agent_log.json` 中 `truncated` 命中 5 次（蓝图 + 四个模块各一次）。

---

## 1. 运行环境与证据面

| 项 | 值 |
|---|---|
| 主机 | `scott-lau-GTR-Pro.local`（Linux，Python 3.x venv `~/arc-venv`） |
| 仓库 | `~/AutoResearchClaw-main` |
| run 目录 | `~/arc-runs/g7-baseline` |
| 配置 | `~/config.g7-field.yaml`（`experiment.mode: sandbox`、`time_budget_sec: 600`） |
| 模型 | `halogen-qwen3.8-flash-next`（无单价配置 → `cost_usd=0.0`、`source=unknown`） |
| 启动方式 | `tmux`（`p191-stage12` → 已终止；`p192-stage12` → 当前） |
| 观测缺陷 | `heartbeat.json` 只在 stage DONE 后写，`logger.info` 因无日志配置被丢弃 → 现场日志只含 WARNING |

---

## 2. 完整时间线

### 2.1 五次运行 / 五次失败

| # | 时窗（UTC） | 时长 | 结果 | 关键错误 | 触发修复 |
|---|---|---|---|---|---|
| A | 11-25 13:48:50 → 14:13:41 | 1 491 s（25 min） | `exit_code=0` | 无（但产出仅 `experiment/` 2 文件、`architecture_spec.yaml` 4 478 B） | P-178（出口门缺失，穷产物被放行） |
| B | 11-25 14:42:25 → 18:19:12 | **13 007 s（3 h 37 m）** | `exit_code=75` | `main.py has a syntax error: unterminated string literal (line 130)` | **P-190 / B-28** |
| C | 11-25 21:33:16 → 11-26 01:36:00 | **14 564 s（4 h 3 m）** | `exit_code=75` | `main.py missing if __name__ == "__main__"; never prints METRIC_DEF` | **P-191 / B-29** |
| D | 11-26 04:51 → 07:27（人工终止） | 约 2 h 36 m | 未记录 attempt（阶段未结束） | `entrypoint attempt 1/2 truncated` ×2，越界第 517 行；`dedicated entrypoint generation failed`；`Repair attempt returned invalid Python for data.py` ×4 | **P-192 / B-30** |
| E | 11-26 07:27:49 → **11:50:39** | **15 770 s（4 h 22 m 50 s）** | `exit_code=75`（retryable） | 3 次内部重试全部 `Topic-experiment misalignment` → `Persistent topic-experiment misalignment after all regen attempts` | **B-32 / B-31a / B-33**（本地已修，未部署） |

> A 的 `exit_code=0` 是「没有出口门」的直接后果：只有 2 个文件、蓝图 4.5 KB 的产物被判通过，说明当时的成功判据只看「能跑」。
> E 是本记录的重心：它是**唯一一次蓝图解析成功**的运行（详见 §2.3），因此暴露的问题层次比前四次更靠后。

### 2.2 运行 E 的分段耗时（本次最完整的一次）

| 时刻（UTC） | 事件 | 证据 |
|---|---|---|
| 07:27:49 | 启动，租约 `fencing=1` | `lease.json` |
| 07:39–07:44 | `agent_runs/attempt_001..003`（沙箱执行） | 目录 mtime |
| 07:47–08:22 | 蓝图：8192 截断 → 32 768 重试 → 57 948 字符 → **YAML 解析两次失败** | `code_agent_log.json` 前 10 行 |
| 08:25 | `CodeAgent.generate()` 完成：**3 471 s / 17 次 LLM / 4 次沙箱 / 2 轮 review** | `code_agent_log.json` 末行 |
| 08:25 | `entrypoint contract unmet (never prints METRIC_DEF)` → 生成入口（B-29 生效） | 日志第 2 行 |
| 08:31–08:43 | 产出 `config.py`(13 978 B) / `utils.py`(1 719 B) / `main.py`(3 573 B) | `experiment/` mtime |
| 08:37–08:43 | 对齐检查 → MISALIGNED → 重生成 2 次 → 仍 MISALIGNED | 日志第 17–19 行 |
| ~08:43 | 消融条件重复检测 → 修复尝试 | `ablation_warning.json` |
| 09:45 | `Stage CODE_GENERATION failed (attempt 1/3) — retrying` | 日志第 22 行（末行） |
| 09:45→ | 第 2/3 次重试：新建 `agent_runs/attempt_001`，4 文件（`models.py` 14 540 B、`main.py` 9 674 B、`config.py` 9 638 B、`data.py` **181 B**） | 目录 mtime + 文件尺寸 |
| 10:11 | 仍在第 2 次重试；累计 279 次 LLM 调用 | `cost_log.jsonl` |
| ~10:2x | 第 2/3 次失败：`data.py` 5 次 repair 全返非法 Python → 1 个 CRITICAL 残留 → `Blocking stage` | 日志 `Repair aborted for data.py after 2 unusable response(s)` / `CRITICAL validation issues remain after 5 repair attempts` |
| 10:3x→ | 第 3/3 次重试：`entrypoint contract unmet (missing __main__; never prints METRIC_DEF)` → 生成入口 | 日志 |
| 11:0x | 对齐门判 MISALIGNED → regen 1、regen 2 仍不合格 → `Persistent topic-experiment misalignment` | 日志 |
| **11:50:39** | **`Stage 10/23 CODE_GENERATION — FAILED (15769.8s)`；`Pipeline complete: 0/1 stages done, 1 failed`** | `stage_health.json` / `events.jsonl seq 82 run.failed` |

### 2.3 运行 E 的终态与产物对账

**终态**（全部一手读数）：

| 项 | 值 | 证据 |
|---|---|---|
| 时长 | 15 769.77 s（4 h 22 m 50 s） | `stage-10/stage_health.json` |
| 结果 | `status: failed`、`exit_code: 75`、`exit_class: retryable` | `attempts/stage-10/attempt-4.json` |
| 管线 | `0/1 stages done, 1 failed`；`stages_run=1` | `events.jsonl` seq 81/82 |
| checkpoint | 仍为 `last_completed_stage=11`；**无 `stage-12`** | `checkpoint.json`、`ls stage-*` |
| 租约 | `released: true`、`fencing=1`（优雅释放，非崩溃） | `lease.json` |
| 成本 | 本轮 91 次 LLM 调用 | `cost_log.jsonl`（07:00–12:00Z 窗口） |

**蓝图↔产物对账**（这是 B-32 M2 证据门的靶心）：

| 维度 | 蓝图声明 | 实际交付 | 结论 |
|---|---|---|---|
| 文件 | `config.py` / `data.py` / `models.py` / `methods.py`（4 个均有 `generation_order`） | `config.py` / `models.py` / `methods.py` / **`synthetic_finance.py`** / `main.py` / `utils.py` | **`data.py` 缺失**（生成返回空 → 被顶替） |
| 主指标 | `changepoint_detection_AUROC` | `main.py` **无任何 `METRIC_DEF`**（`grep` 0 命中） | **指标完全缺失** |
| 入口 | — | 112 行，**末尾停在 `df`（截断）**，无 `if __name__ == "__main__"` | 不合 B-29 契约 |
| 数据源 | `source: yfinance`，6 标的（^GSPC/^IXIC/^DJI/^VIX/BTC-USD/ETH-USD） | `np.random.default_rng` 合成序列 | 语义漂移 |
| 消融 | 应有多方法对照 | `ablation_warning.json`：12 个 condition 仅标签不同，"no actual parameter differences are encoded" | 无真实对照 |

> **反事实**：装上 B-32 M2 的证据门后，这一轮会**在几秒内**得到 `blueprint_files_missing: data.py` + `metric_not_printed` + `synthetic_data=true` 三条结构化失败，而不必等对齐门用三段自然语言判词、耗掉 4 小时 22 分。这是这批修复最直接的价值证据。

**失败模式变迁**（本轮最重要的新信息）：

```text
旧（运行 B–D）：蓝图 YAML 失效 → blueprint=None → 单发 → 只有 config.py + 配置校验 main.py
新（运行 E）  ：蓝图解析成功（36 831 字符 / 4 files）→ 顺序生成真的跑了
                → 四模块首轮 8192 均截断 → 三个在 32768 补全成功
                → data.py 的 32768 响应无闭合围栏 → 提取器返回空 → 静默跳过
                → 对齐门否决（内容不成立）← 语义层
```

详见 §F-7b（含订正）。

**日志交错顺序（B-31a 的现场实证）**：`/tmp/p192_stage12.log` 里所有 `logger.warning` 行（无缓冲 stderr）先写出，而 `print` 的管道横幅——

```text
ResearchClaw v0.5.0 — Starting pipeline
[g7-baseline] Stage 10/23 CODE_GENERATION — running...
```

——直到进程退出才出现在文件**末尾**。这是「块缓冲 + 默认 WARNING 级别」双杀的教科书形态，与 B-31a 的根因分析完全一致。

**部署状态核对**（`~/AutoResearchClaw-main` 是源码副本、非 git 仓库）：

```text
researchclaw/runtime/logging_setup.py      不存在
researchclaw/pipeline/codegen_evidence.py  不存在
researchclaw/pipeline/step_journal.py      不存在
runner.py:      _write_stage_start          0 命中
code_agent.py:  _fold_trailing_colon_items  0 命中
```

即本轮跑的是 P-192 之前的代码：`steps.jsonl` / `codegen_decision.json` / `codegen_evidence.json` 三个新产物在 `stage-10/` 中**均不存在**（`ls` 已确认）。

---

## 3. 故障分层（F 表）

### F-1 出口门缺失（已修：P-178）

- **现象**：运行 A 以 25 分钟、2 个文件、4.5 KB 蓝图判 `exit_code=0`。
- **机制**：Stage 10 只校验「文件可解析」，不校验「入口可执行、有指标行」。
- **修复**：`_entrypoint_issues` 用 AST 检查 `if __name__ == "__main__"` 与 `METRIC_DEF`，Stage 10 在 DONE 前拦截（`spec/arc-stage10-codegen-truncation/`）。

### F-2 截断与未闭合围栏（已修：P-178）

- **现象**：运行 B `main.py` 在第 130 行 `"cor` 处截断，语法错误。
- **机制**：模型输出被 `max_tokens` 截断；围栏未闭合时抽取器丢掉整块。
- **修复**：`_close_unterminated_fence`（奇数 ``` 补闭合）；blueprint/单文件/single-shot 在 `truncated` 时各重试一次 32 768。

### F-3 repair 整体替换 + 无截断重试（已修：P-190 / B-28）

- **现象**：repair 连续 5 次只返回 `main.py`，`data.py` 的 7 个 CRITICAL 永不消；且修复版比原版更完整（9 472 B / 294 行，沙箱可执行）却被丢弃。
- **机制**：`files = repaired` 整体替换，未返回的文件被删；repair 无截断感知。
- **修复**：`_extract_valid_repair_files`（AST 过滤、未知文件忽略）+ `_merge_repair_files`（合并保留）+ `_request_repair_response`（截断 8192→32768 重试）。
- **现场验证**：运行 E 08:35 出现 `Stage 10 repair: response truncated — retrying with 32768`。

### F-4 首个文件被提升为 main.py（已修：P-191 / B-29）

- **现象**：运行 C `main.py` 3 809 B、末尾 `state = alpha`，语法合法但无 `__main__`、无 `METRIC_DEF`；同时 `BUG-184: config.py imports 'types' which is not in generated files`。
- **机制**：`code_agent.py` 在缺 `main.py` 时把**第一个文件**（config.py）重命名为 main.py，导致 `from config import ...` 悬空。
- **修复**：删除文件提升；新增 `entrypoint_contract.py`（`entrypoint_issues` / `summarize_modules` / `build_entrypoint_prompt`）；专用 `_generate_entrypoint_file`（2 次、截断重试、第 2 次带上次拒绝原因）；repair 拒绝不合契约的 main.py。
- **现场验证**：运行 E 08:25 `Stage 10: entrypoint contract unmet (...); generating main.py` —— 契约前置逻辑被真实触发。

### F-5 入口生成无体量约束、无兜底、repair 空转（已修：P-192 / B-30）

- **现象**：运行 D 两次尝试均在 32 768 截断，越界第 517 行；`dedicated entrypoint generation failed`；`data.py` repair 连续 4 次返回非法 Python。
- **机制**：① 同额度重试无信息增量；② 提示未限制体量，模型把全部实现搬进入口；③ 无确定性兜底；④ repair 无止损。
- **修复**：预算 32 768 → 65 536（第二次）；提示 ≤150 行 / 只 import 不重写 / `exp_plan` 摘要 3 000→1 200；`synthesize_entrypoint` 薄驱动兜底（取不到数值打印 `nan`，**绝不填 0.0**）；repair 连续 2 次不可用即止损。
- **现场验证**：运行 E 入口一次成功（`experiment/main.py` 3 573 B、含 `METRIC_DEF`），未触发 65 536 升级。

### F-6 蓝图 YAML 失效 → 顺序生成被跳过 → 单发退化（已修：B-32 M1/M2，未部署）

- **现象**（运行 E 上一轮，即 08:22 那一次）：蓝图 57 948 字符，两次解析均失败：

  ```
  Blueprint YAML parse error: while scanning a simple key ... line 1055:
      HiddenStateTauKLMonitor override ...
  could not find expected ':'  (line 1056)
  Sequential generation requested but blueprint invalid — falling back to single-shot
  ```

- **机制**：`_parse_blueprint` 的预处理把 key 分隔符定为 `":\s"`（冒号 + 空白），不覆盖「值以冒号结尾 + 下一行续写」的形态；解析失败后 `blueprint=None`，`_is_valid_blueprint` 不满足 → 走单发。
- **后果**：单发只生成 `config.py` + 配置校验型 `main.py`。蓝图声明 5 个文件 / 6 个 `class:` / 32 处 `Monitor`，实际交付 0 个 monitor 类。B-29/B-30 所在的**顺序路径根本没有执行**。
- **证据**：`architecture_spec.yaml` 第 1055–1056 行；`code_agent_log.json` 第 4、5 行；`experiment/` 仅 3 个文件。
- **状态**：**已修复并合入 `main`（`304c9f8`），未部署**。P-194 修折叠与重试、P-197 加四项证据门、P-202 硬化五项边界；规格见 `spec/arc-stage10-blueprint-yaml-robust/`（DESIGN v2.0）。
- **运行 E 终态的反证**：11-26 最后一次运行中蓝图 **36 831 字符解析成功**（`Parsed blueprint: 4 files` → `Phase 2: Sequential generation (blueprint-guided)`），F-6 的 YAML 缺陷**未复发**。因此 E 的失败不能归因于 F-6。

### F-7 主题-实验对齐门（既有护栏，运行 E 首次真实触发）

- **机制**：`_code_generation.py` L1780-1910 先让模型自评「代码是否真的检验了 topic」，不合格则最多重生成 2 次并复检；仍不合格则 FAILED（L2020）。
- **运行 E 判词（节选，属正确判断）**：

  > main.py 只做合成 AR 式隐状态模拟，没有实例化或训练 LNN；τ-KL 不是对 LNN 内部动力学的粗筛，而是对差分序列的高斯均值/方差 KL；Fréchet 是对窗口累积偏差的离散距离，不是伴随状态变点检测；没有分层漂移架构，没有金融时序数据管线。

  以及消融判词：12 个条件只是 `DRIFT_TYPES × DRIFT_SPEEDS × NOISE_LEVELS` 的标签组合，无参数差异、无代码分支、无消融开关。

- **评价**：**这是护栏按设计工作**。它把「假实验」挡在 Stage 12 之外，代价是 Stage 10 显式失败而不是静默带着穷产物继续。
- **运行 E 终态的三次判词**（11-26 最后一轮，节选）：① `main.py implements a generic synthetic AR-like hidden state simulation and does not instantiate or train a Liquid Neural Network`；② `The code only generates synthetic financial time series with injected regime shifts ... and does not implement the core methods`；③ 消融判词 `all 12 conditions are configuration-identical at the level visible in this snippet`。
- **问题**：护栏只负责否决，不提供「怎么改才合格」的有效路径。运行 E 中它连否 3 次 ×2 轮，而代码侧真正缺的是 `data.py`（空返回）与模块体量——**护栏的判词是对的，但它不是可执行的修复线索**。

### F-7b 模块级截断提取兜底缺失（订正；B-34 候选）

> **订正说明（2026-11-26，P-205）**：本节的初版把根因写成「模块级生成容量不足 / 四模块全部在 32 768 打满」。用代码锚点 + 交付体积复核后，该归因**不成立**，已按下列读数改写。原文错误保留在 §F-7b.3 以备追溯。

#### F-7b.1 现场读数

`code_agent_log.json` 中 `truncated` 命中 **5 次**，逐行位置与含义：

| 行 | 内容 | 含义 |
|---|---|---|
| 6 | `Blueprint truncated (finish_reason=length) — retrying with 32768` | 蓝图首轮 8192 截断 |
| 11 | `config.py: truncated — retrying with 32768` | 模块首轮 **8192** 截断 |
| 14 | `data.py: truncated — retrying with 32768` | 同上 |
| 15 | `WARNING: Empty code for data.py` | **32768 重试后仍提取为空** |
| 17 | `models.py: truncated — retrying with 32768` | 模块首轮 8192 截断 |
| 20 | `methods.py: truncated — retrying with 32768` | 模块首轮 8192 截断 |

**关键**：这 5 条全部是**首轮 8192 的 `finish_reason=length`**——代码 [L803-814](../researchclaw/pipeline/code_agent.py#L803-L814) 在 32768 重试后**不再检查 `truncated`**，因此「32768 是否也打满」在日志上**不可观测**。

交付体积（`wc -c` / `wc -l` on `experiment/`）：

| 文件 | 行 | 字节 | ≈ tokens（chars/3.5） | 提取结果 |
|---|---|---|---|---|
| `methods.py` | 448 | 15 802 | ~4.5 k | ✅ 成功 |
| `config.py` | 343 | 12 528 | ~3.6 k | ✅ 成功 |
| `models.py` | 217 | 6 911 | ~2.0 k | ✅ 成功 |
| `main.py` | 112 | 3 904 | ~1.1 k | ✅（后由 B-29 入口生成补） |
| `data.py` | — | — | — | ❌ 空 |

**逻辑链**：提取器要求**闭合围栏**（见下）⇒ 提取成功 ⇒ 响应完整 ⇒ 未在 32768 截断。三个模块成功，说明 **32768 对它们的体量是够用的**。因此「四模块全部 32768 打满」为**外推错误**；「单模块体积超模型容量」同样不成立——交付模块只用了限额的 1/3～1/8。

#### F-7b.2 真根因：每模块调用缺少截断围栏兜底

`_extract_single_file_code`（[L900-L933](../researchclaw/pipeline/code_agent.py#L900-L933)）的三个 fenced 模式**全部要求闭合 ` ``` `**：

```python
m = re.search(r"```python\s*\n(.*?)```", content, re.DOTALL)
...
m = re.search(rf"```(?:filename:)?{re.escape(expected_name)}\s*\n(.*?)```", ...)
m = re.search(r"```[^\n`]*\n(.*?)```", ...)
stripped = content.strip()
if stripped:
    ast.parse(stripped)          # 截断响应含 ```python 开头 + 半截代码 → SyntaxError
    ... except SyntaxError: return ""
```

截断响应**没有闭合围栏** ⇒ 三个 fenced 模式全 miss ⇒ 全文 `ast.parse` 因残留的 ` ```python ` 行 SyntaxError ⇒ 返回 `""` ⇒ [L812-814](../researchclaw/pipeline/code_agent.py#L812-L814) 打一条 `WARNING` 后 `continue`，该文件就此消失。这是**确定性**行为，与模型能力无关。

**对照**：P-178 的 `_close_unterminated_fence`（[_helpers.py L584](../researchclaw/pipeline/_helpers.py#L584)）只被 [`_extract_code_block` L592](../researchclaw/pipeline/_helpers.py#L592) 与 [`_extract_multi_file_blocks` L636](../researchclaw/pipeline/_helpers.py#L636) 调用——即**单发路径**。`_extract_single_file_code` 一行未补。所以 F-2 的修法**没有覆盖顺序生成的每模块分支**。

#### F-7b.3 原错误的归因（保留追溯）

初版写的是「蓝图给每个文件下 `min_effective_lines: 45` 等体量要求，而单模块预算固定 32 768，两者不匹配时模型只能截断或返回空」。**该推理的漏洞**：把首轮 8192 的截断当成了 32768 打满，并用「模块应当很大」代替了「实测体积」。

另一条被忽略的可能：每模块 prompt 注入**整份 36 831 字符蓝图** + 全部依赖源码 + 4 KB plan（[L796-802](../researchclaw/pipeline/code_agent.py#L796-L802)），首轮 8192 截断更可能是**输入过载导致输出啰嗦/重复**，而非模块本身超长。

#### F-7b.4 关于「alignment 门更早、更强硬」的核对

| 主张 | 裁决 | 证据 |
|---|---|---|
| alignment 门**更早** | ✅ 属实 | 对齐检查在 [_code_generation.py L1713-1911](../researchclaw/pipeline/stage_impls/_code_generation.py#L1713-L1911)，硬失败在 L2021；证据门在 L2074 |
| alignment 门**更强硬** | ⚠️ 需修正 | 它给 **2 次 regen**（L1818 `_max_regen = 2`），比证据门"一次即否"**更宽容**；真实问题是"更早 + 更贵"（每次 regen 整包重写，构成 4 h 22 m 的主体） |
| run E 中 alignment 抢在结构门之前否决 | ⚠️ **不可观测** | run E 跑的是 P-192 之前代码，**证据门尚不存在**；该因果只能在部署后重跑时验证 |

另：alignment 判据是开放式语义判断，且**不提供最低实现清单**，regen 无靶子——这是它"难满足"的实际来源，与"更强硬"是两件事。

#### F-7b.5 建议的 B-34 范围（命题已改）

| 档 | 内容 | 价值 |
|---|---|---|
| **M1-a** | 把 `_close_unterminated_fence` 补进 `_extract_single_file_code`（或直接复用 `_extract_code_block`） | 直接修掉 `data.py` 空返回；与 P-178 同修法，零新概念 |
| **M1-b** | 32768 之后仍 `truncated` → 记 `steps.jsonl`（`variant` / `status=failed`）并**显式失败**，不再 `continue` 静默跳过 | 把"几小时后出口才发现"变成"模块边界分钟级失败"（fail fast） |
| M2（可选） | 模块 prompt 只注入该模块依赖子集的蓝图节点，不再整份 36 KB | 降低输入过载，间接减少 8192 截断 |

**明确不做**：单靠提高 32768 → 65536。交付体积证明不需要。

#### F-7b.6 B-34 的合并范围（含 P-204 复审的 F-1..F-6）

按用户裁决（2026-11-27），B-34 **并入** [P-204 复审](arc-p203-postmortem-review-20261126.md) §4 的六项证据门误报，一次性收口 Stage 10 生成链的剩余缺陷：

| 编号 | 来源 | 内容 | 严重度 |
|---|---|---|---|
| M1-a | 本 §F-7b.2 | `_close_unterminated_fence` 补进 `_extract_single_file_code` | — |
| M1-b | 本 §F-7b.2 | 32768 后仍截断/提取空 → 记 `steps.jsonl` + 显式失败 | — |
| F-1 | P-204 §4 | 数据源门子串匹配命中注释 → 假阴性 | 中 |
| F-5 | P-204 §4 | 合成数据正则命中注释 → `synthetic_data` 假阳性 | 低-中 |
| F-2 | P-204 §4 | `*Config` 后缀一刀切（`KernelConfig` 含真实计算判 0） | 中 |
| F-3 | P-204 §4 | 指标名被 `(` `[` `{` `}` 截断 | 低-中 |
| F-4 | P-204 §4 | `_leaf_strings` 跳过 `bool` | 低 |
| F-6 | P-204 §4 | `code_version()` 版本静默回落 `"0"` | 低 |

**合并理由**：F-1 与 F-5 共用「剔除注释行」一个实现；F-2/F-3/F-4/F-6 都在 `codegen_evidence.py` 与 `step_journal.py` 内，与 M1 同批改动面重叠，分开做会重复跑同一组回归。

**与 B-32 的边界**（不变）：B-32 修的是「结构是否被实现」，B-34 修的是「结构能否被完整取回」+「判定是否误报」。B-32 M2 只能**判定** `data.py` 缺失，不能**修复**提取。

**优先级**：P1（非 P0）——B-32 M2 已能在出口判 `blueprint_files_missing: data.py`，现状是「最终会失败但浪费 4 小时」，不是「静默成功」。

### F-8 阶段重试从零重跑（已修：B-33 M1，未部署）

- **现象**：09:45 失败后，`agent_runs/attempt_001` 被**重新创建**（此前已有 001–004），`code_agent_log.json` 仍是 08:25 旧版 → 第 2 次重试从 Phase 1 重新开始。
- **机制**：`checkpoint.json` 只在 stage DONE 后写，Stage 10 内部无任何可恢复状态；`_call_with_retries`（`executor.py` L613-629）最多 3 次，每次都是完整重跑。
- **代价**：单次重试约 70 分钟 / 17–20 次调用，全部丢弃重来。运行 E 的三次内部重试合计约 4 h 22 m，其中可复用部分为零。
- **状态**：**B-33 M1 已由 P-193 实现并合入 `main`（`304c9f8`），未部署**（`in_progress_stage` + 蓝图尽早落盘 + `steps.jsonl`）。运行 E 现场 `stage-10/` 中**无 `steps.jsonl`**，故断点收益在本轮为零。L2（生成路径实际跳过）与 L3（LLM 响应缓存）仍未做。

### F-9 可观测性盲区（已修：B-31a，未部署）

- **现象**：运行 E 前 2 h 44 m，`/tmp/p192_stage12.log` 只有 **22 行 / 6 656 B**；`heartbeat.json` 停留在 2026-11-25T14:14:37Z；`events.jsonl` 只有 `stage.started`。运行 E 全程结束时日志 12 153 B / 4 h 22 m。
- **机制**：① `_write_heartbeat` 仅在 DONE 后调用；② 无 `logging.basicConfig`，`logger.info` 全丢；③ `print` 在重定向下块缓冲；④ `llm.call/llm.result` 有声明无生产者；⑤ dashboard/`ops` 不读 lease 与 `steps.jsonl`。
- **后果**：08:43–09:45 这 62 分钟（对齐重生成 + 消融修复）在现场完全不可见，只能靠 `cost_log.jsonl` 的调用节奏反推。
- **运行 E 终态的直接实证**：日志文件的**行序**证明块缓冲——所有 `logger.warning`（stderr，无缓冲）写在前面，`print` 的 `ResearchClaw v0.5.0 — Starting pipeline` 与 `Stage 10/23 ... running...` 却出现在文件**末尾**，即进程退出时才 flush。
- **状态**：**B-31a 已修复并合入 `main`（`304c9f8`），未部署**。P-195 加 `run --log-level/--log-file` + `basicConfig(force=True)` + 行缓冲 + 阶段横幅入日志；P-198 补录真实红→绿。B-31b（心跳 details + `STALLED`）仍未做。

---

## 4. 修复决策回溯

| 批次 | 编号 | 触发故障 | 核心改动 | 交付 | B 站现场验证 |
|---|---|---|---|---|---|
| P-178 | — | F-1 / F-2 | 围栏容错、截断重试 32768、评审守卫、出口门（AST 检查 `__main__` + `METRIC_DEF`） | `spec/arc-stage10-codegen-truncation/` | 运行 B/C 的失败证明门在检查；运行 E 未再出现「无守卫入口」 |
| P-190 | B-28 | F-3 | repair 合并而非替换、AST 过滤、截断重试 | `spec/arc-stage10-repair-merge/` | 运行 E 08:35 `repair: response truncated — retrying with 32768` |
| P-191 | B-29 | F-4 | 删除文件提升；`entrypoint_contract.py`；专用入口生成；repair 拒绝不合契约 main.py | `spec/arc-stage10-entrypoint-contract/` | 运行 E 08:25 `entrypoint contract unmet ... generating main.py` |
| P-192 | B-30 | F-5 | 预算 32768→65536；提示 ≤150 行 + 禁止重写；`synthesize_entrypoint`（`nan` 兜底）；repair 2 次止损 | `spec/arc-stage10-entrypoint-budget/` | 运行 E 入口一次成功，未升级 65536，未再出现「repair 空转 4 次」 |
| P-193 | B-33 M1 | F-8 | `in_progress_stage`（含事件重建回填）；蓝图 Phase 1 后即落盘；`step_journal`（append-only / 摘要 / 复合键 / `should_skip`） | `spec/arc-stage10-intra-stage-checkpoint/` | **未部署**（B 站 `step_journal.py` 不存在、`_write_stage_start` 零命中） |
| P-194 | B-32 M1 | F-6 | 折叠「行尾冒号 + 缩进续行」；一次窄提示 YAML 重试；回退写 `codegen_decision.json` + `logger.warning` | `spec/arc-stage10-blueprint-yaml-robust/` | **未部署**（`codegen_decision.json` 不存在） |
| P-195 / P-198 | B-31a | F-9 | `run --log-level/--log-file`；`basicConfig(force=True)`；行缓冲；阶段横幅入日志；补真实 TDD 红→绿 | `spec/arc-runtime-log-visibility/` | **未部署**（`logging_setup.py` 不存在） |
| P-197 | B-32 M2 | F-6 后果 | 四项证据门（文件集合 / 指标一致 / 数据源 WARN / 非配置计算）+ 折叠 mapping 保护 | 同上（v1.1） | **未部署**（`codegen_evidence.json` 不存在） |
| P-202 | B-32 M3 | F-6 + P-200 复审 | 指标名 AST 优先；数据源递归取叶子；折叠双守卫；无围栏 `files:` 对齐；门读磁盘 `experiment/` | 同上（v2.0） | **未部署** |

> 提交：`6274eb2`（P-190/P-191）、`afd0dd5`（P-192/P-193）、`9ac80b3`（边界写点登记）、`8744c84`（P-194..P-199）、`1d7853a`（P-200..P-202）；PR [#55](https://github.com/StormstoutLau/AutoResearchClaw/pull/55) 与 [#56](https://github.com/StormstoutLau/AutoResearchClaw/pull/56)，CI 各 8/8；`main` 当前 `304c9f8`。
> **一句话**：P-178..P-192 已在现场验证生效；P-193..P-202 已合入但**零部署**，因此运行 E 的失败不能用来评价这批修复。

### 4.1 关键决策与理由

| 决策 | 被拒替代 | 理由 |
|---|---|---|
| 入口契约前置到「校验前 + 出口门前」 | 只在出口门拦 | 出口门在阶段末，失败要等数小时；前置把失败成本从小时级降到分钟级 |
| 截断后**升级**预算而非同额度重试 | 32 768 重试两次 | 运行 D 两次都在同一行截断，同额度无信息增量 |
| 兜底打印 `nan` | 填 `0.0` | `0.0` 会被下游当作有效指标，污染结论（与 B-30 纪律一致） |
| repair 连续 2 次不可用即止损 | 耗满 5 个槽 | 同一失败重复 4 次无收益，纯增耗时 |
| `--resume` 让 `in_progress_stage` 优先 | 只在 CLI 侧推断 | 事件推断无法区分「已完成」与「已开始未完成」 |
| 蓝图在 Phase 1 后立即落盘 | 阶段末统一落盘 | Phase 1 后崩溃是最贵窗口（生成前），否则断点无产物可校验 |
| 证据门**只判失败、不修补产物** | 按缺失清单再生成补齐 | 补齐需要 topic/plan 上下文，容易造出「二次伪成功」；显式失败把证据留给下游与审计 |
| 证据门**以磁盘 `experiment/` 为准** | 只读内存 `files` 映射 | Stage 12 实际执行的是磁盘文件；`--from-stage` 重跑时二者可背离（P-202 N-1） |
| 指标名**从 AST 取 `print` 实参** | 文件级正则首匹配 | 注释与 docstring 在 AST 里不进 `Call.args`，是结构性排除而非启发式（P-202 F-1） |
| 折叠守卫判「续行是否 `k: v`」 | 判「文本是否含空白」 | YAML 把 `- some key:` + 缩进 `nested: value` 解析为 mapping，含空白不代表是散文（P-202 F-3） |

---

## 5. 仍未解决

| # | 项 | 影响 | 处置 |
|---|---|---|---|
| 1 | **P-193..P-202 全部未部署** | B 站仍跑 P-192 之前代码，同一故障会持续复现 | **最高优先**：同步 `~/AutoResearchClaw-main` 到 `304c9f8` 后重跑 |
| 2 | **F-7b 每模块截断提取兜底缺失（B-34 候选，命题已订正）** | `data.py` 的 32768 响应无闭合围栏 → 提取空 → 静默跳过；浪费 1/4 模块 | 立项：M1-a 补 `_close_unterminated_fence` 到 `_extract_single_file_code`；M1-b 空返回显式失败并记 `steps.jsonl`。**不加预算** |
| 3 | 对齐门只有否决、无「合格线」 | 判词正确但不可执行，连否 3 次 ×2 轮 | 建议在 regen 提示中附带蓝图 `files`/`classes` 清单作为最低实现要求 |
| 4 | 阶段重试 3 次上限 | 3 次全失败后 Stage 10 直接失败，管线停在 12 之前 | 与 B-8（退出码分类）一起评估「降级 + 标注」而非硬失败 |
| 5 | B-31b 未做（心跳 + `STALLED`） | 部署 B-31a 后日志可见，但仍无「活着但停滞」判定 | 与 B-33 M2 同批 |
| 6 | 证据门未在真实模型产出上验证 | C-27 仍 ⏳；门可能在真实产出上误杀 | 部署后重跑即为首次现场验证 |
| 7 | 现场无 `heartbeat` / `stage_health` 更新 | 无法判断「活着但停滞」 | B-31a 部署后缓解一半 |

---

## 6. 成本统计

| 项 | 值 |
|---|---|
| Stage 10 累计墙钟（A–E） | 1 491 + 13 007 + 14 564 + 约 9 400（D 被杀）+ **15 770（E）** ≈ **12.7 h** |
| 运行 E 单轮 | 15 769.77 s，**91 次 LLM 调用**，3 次内部重试 |
| 单次 CodeAgent 典型耗时 | 3 471 s（58 min），17 次 LLM，4 次沙箱，2 轮 review |
| 生成链内部日志 | `code_agent_log.json` 中 `truncated` 命中 **5 次**，全部为**首轮 8192** 的 `finish_reason=length`（蓝图 1 + `config.py`/`data.py`/`models.py`/`methods.py` 各 1）；32768 之后的截断状态**不可观测**（代码无二次检查） |
| 实际交付体量 | `methods.py` 448 行/15.8 KB、`config.py` 343 行/12.5 KB、`models.py` 217 行/6.9 KB ≈ **2–4.5 k tokens**，均远低于 8192 ⇒ 首轮截断不能归因于"模块太大" |
| 截断率 | 运行 E 前段 245 次调用中 **84 次（34%）** `completion_tokens=16384` 打满 |
| 失败重试浪费 | 每次 stage 重试丢弃前一整轮（约 17–20 次调用、约 70 min）；E 的三次重试各被对齐门否决 |
| 观测成本 | 运行 E 全程 4 h 22 m 仅产出 **12 153 B** 日志；`heartbeat` 滞后 19 h |
| 未被结构门捕获的漂移 | `data.py` 缺失 / 指标全缺 / `main.py` 截断 —— 若 B-32 M2 已部署，本可在**秒级**判定 |

---

## 7. 教训与流程建议

1. **修一个暴露下一个是正常的，但要按「生成链」顺序修**。B-28/29/30 都是「有产物之后」的修复，而 F-6 让产物路径根本不成立——**应先修前置（B-32），再修后置**。
2. **成功判据比错误处理更危险**。运行 A 的 `exit_code=0` 比任何崩溃都糟：它让 25 分钟的穷产物被当作成功。任何「能跑即通过」的判据都应配结构/语义门。
3. **本地门禁与 CI 门禁的判定模式不同**。P-179..P-189 在本地提交时走 `session-progress` 模式（通过），CI 对 PR 区间走 `batch` 模式（红）。这类差异应在本地预演（本次已用 `step_enforce --base origin/main <changed>` 补齐）。
4. **未部署的修复等于没修**。B-31/B-32/B-33 都已实现并合入 `main`，但 B 站跑的是旧代码，因此同一故障会持续复现。**部署本身应作为批次的一部分登记**，而不是一个可选的后续动作。
5. **现场必须留「进行时」痕迹**。本次定位 08:43–09:45 的 62 分钟空白，只能靠 `cost_log.jsonl` 的行数与时间戳反推，成本极高。
6. **「判定」与「修复」必须分层**。运行 E 证明：结构门（B-32 M2）能秒级判定 `data.py` 缺失，但不能让模型把 `data.py` 生成出来。把二者混在一个批次里，会让门看起来"没用"——其实它只是**下游**。
7. **日志的行序本身就是证据**。运行 E 的日志里 `print` 横幅全部落后于 `logger.warning`，这一现象单独就证实了块缓冲；无需另做实验。排查时应优先看"顺序异常"而非只看"内容缺失"。
8. **失败判词要可执行**。对齐门的三段判词在科学上正确，但对生成侧没有可操作指令；这类"只否决不指路"的门应附最低实现清单（蓝图 `files`/`classes`）。
9. **归因要看"实测体积"，不要看"应然体积"**。F-7b 初版把「四模块 32768 打满」当事实写入，实际 5 条 `truncated` 全是**首轮 8192**，交付模块只用了限额的 1/3～1/8。用"模块应当很大"代替实测，会把「提取器缺兜底」误诊为「模型容量不足」，从而给出错误处方（加预算而非补兜底）。
10. **同一修法要检查是否覆盖所有分支**。P-178 的 `_close_unterminated_fence` 只补在单发路径的两个提取器上，顺序生成的 `_extract_single_file_code` 一行未补——这就是 `data.py` 消失的直接原因。修一个缺陷时应枚举所有调用点。

---

## 8. 附录

### A. 复现命令

```bash
# 阶段尝试记录（跨 run 全局编号）
for f in ~/arc-runs/g7-baseline/attempts/stage-10/*.json; do echo "== $f"; cat $f; done

# 生成链内部日志（明确记录蓝图截断与回退）
python3 - <<'EOF'
import json, pathlib
d = json.loads(pathlib.Path("~/arc-runs/g7-baseline/stage-10/code_agent_log.json").expanduser().read_text())
print(d["llm_calls"], d["sandbox_runs"], d["review_rounds"])
print("\n".join(d["log"][:12]))
EOF

# YAML 失效行
sed -n '1050,1060p' ~/arc-runs/g7-baseline/stage-10/architecture_spec.yaml

# 对齐/消融判词
grep -nE 'MISALIGNMENT|Regen attempt|Duplicate ablation|Persistent' /tmp/p192_stage12.log
cat ~/arc-runs/g7-baseline/stage-10/ablation_warning.json

# 阶段重试起点（新 attempt 目录 = 从零重跑）
ls -l --time-style=+%H:%M ~/arc-runs/g7-baseline/stage-10/agent_runs

# 调用节奏与截断率
wc -l ~/arc-runs/g7-baseline/cost_log.jsonl
grep -c '"completion_tokens": 16384' ~/arc-runs/g7-baseline/cost_log.jsonl

# ---- 运行 E 终态复核（2026-11-26 11:50:39Z 之后）----

# 1) 进程与租约：应无 researchclaw 进程、lease.released=true
ps -ef | grep researchclaw | grep -v grep; cat ~/arc-runs/g7-baseline/lease.json

# 2) 终态读数：failed / exit_code 75 / 15 769.77 s
cat ~/arc-runs/g7-baseline/stage-10/stage_health.json
cat ~/arc-runs/g7-baseline/attempts/stage-10/attempt-4.json

# 3) 事件链末三条（应见 run.failed，stages_run=1）
tail -3 ~/arc-runs/g7-baseline/events.jsonl

# 4) 蓝图是否解析成功（本轮反证：应见 Parsed blueprint + Sequential generation）
grep -nE 'Blueprint spec|Parsed blueprint|Sequential generation|falling back' \
  ~/arc-runs/g7-baseline/stage-10/code_agent_log.json

# 5) 模块级截断与空返回（F-7b：5 条 truncated 全是首轮 8192）
grep -c 'truncated' ~/arc-runs/g7-baseline/stage-10/code_agent_log.json
grep -nE 'Empty code|retrying with 32768' ~/arc-runs/g7-baseline/stage-10/code_agent_log.json
# 5b) 实测交付体量（证明"不是模块太大"）
wc -lc ~/arc-runs/g7-baseline/stage-10/experiment/*.py
# 5c) 提取器是否补了截断围栏兜底（应发现 single_file 未补）
grep -c '_close_unterminated_fence' ~/AutoResearchClaw-main/researchclaw/pipeline/code_agent.py
grep -n '_close_unterminated_fence' ~/AutoResearchClaw-main/researchclaw/pipeline/_helpers.py

# 6) 产物对账：data.py 缺失 / main.py 无 METRIC_DEF / main.py 末尾截断
ls -la ~/arc-runs/g7-baseline/stage-10/experiment/
grep -c 'METRIC_DEF' ~/arc-runs/g7-baseline/stage-10/experiment/main.py
tail -3 ~/arc-runs/g7-baseline/stage-10/experiment/main.py

# 7) 蓝图声明与指标
grep -A20 '^files:' ~/arc-runs/g7-baseline/stage-10/architecture_spec.yaml | head -25
grep -n 'primary_metric' ~/arc-runs/g7-baseline/stage-10/architecture_spec.yaml | head -3

# 8) 日志块缓冲实证：print 横幅是否落在文件末尾
tail -12 /tmp/p192_stage12.log

# 9) 部署状态：三个新模块是否存在于现场
ls ~/AutoResearchClaw-main/researchclaw/runtime/logging_setup.py \
   ~/AutoResearchClaw-main/researchclaw/pipeline/codegen_evidence.py \
   ~/AutoResearchClaw-main/researchclaw/pipeline/step_journal.py
grep -c '_write_stage_start' ~/AutoResearchClaw-main/researchclaw/pipeline/runner.py
grep -c '_fold_trailing_colon_items' ~/AutoResearchClaw-main/researchclaw/pipeline/code_agent.py
```

### B. 证据文件清单

| 文件 | 用途 |
|---|---|
| `attempts/stage-10/attempt-{1,2,3,4}.json` | 四次阶段结果、退出码、resume_note、产物快照（**attempt-4 为运行 E 终态**） |
| `stage-10/stage_health.json` | 运行 E 终态：`duration_sec=15769.77`、`status=failed`、错误原文 |
| `stage-10/code_agent_log.json` | CodeAgent 逐阶段日志（蓝图截断、YAML 错误、回退、硬校验、exec-fix；运行 E 中 `truncated` ×5） |
| `stage-10/architecture_spec.yaml` | 蓝图原文（运行 E：36 907 B / 36 831 字符，**解析成功**；上一轮：57 957 B，失败行 1055–1056） |
| `stage-10/agent_runs/attempt_00N/` | 每次沙箱执行的完整文件集 |
| `stage-10/experiment/` | 最终交付（运行 E：config/methods/models/synthetic_finance/main/utils 六文件；`data.py` 缺失） |
| `stage-10/ablation_warning.json` | 消融条件重复判词 |
| `stage-10/decision.json` | 阶段判决（`status=failed`、`next_stage=10`） |
| `stage-10/experiment_spec.md` | 阶段规格与对齐状态 |
| `cost_log.jsonl` | 调用节奏与截断率（运行 E：91 次） |
| `events.jsonl` / `checkpoint.json` / `lease.json` | 阶段边界与存活信号（运行 E：seq 82 `run.failed`、`lease.released=true`） |
| `/tmp/p191_stage12.log`、`/tmp/p192_stage12.log` | WARNING 级现场日志（运行 E：12 153 B；**行序证明 `print` 块缓冲**） |

### C. 相关文档与提交

- 修复规格：[P-178](../spec/arc-stage10-codegen-truncation/)、[B-28](../spec/arc-stage10-repair-merge/)、[B-29](../spec/arc-stage10-entrypoint-contract/)、[B-30](../spec/arc-stage10-entrypoint-budget/)、[B-31a](../spec/arc-runtime-log-visibility/)、[B-32 v2.0](../spec/arc-stage10-blueprint-yaml-robust/)、[B-33](../spec/arc-stage10-intra-stage-checkpoint/)
- 立项调研：[B-31](arc-longrun-progress-observability-20261126.md)、[B-32](arc-stage10-blueprint-fallback-20261126.md)、[B-33](arc-stage10-intra-stage-checkpoint-20261126.md)
- 异构复审：[B-31 复审](arc-longrun-progress-review-20261126.md)、[B-33 复审](arc-stage10-checkpoint-review-20261126.md)、[P-194..P-199 复审](arc-p194-p199-heterogeneous-review-20261126.md)
- 总纲：[arc-master-roadmap.md](../arc-master-roadmap.md) §3.2（B-28..B-33）
- 提交：`6274eb2`、`afd0dd5`、`9ac80b3`、`8744c84`、`1d7853a`；PR [#55](https://github.com/StormstoutLau/AutoResearchClaw/pull/55)、[#56](https://github.com/StormstoutLau/AutoResearchClaw/pull/56)；`main` = `304c9f8`

### D. 与本文其余文档的关系

| 文档 | 关系 |
|---|---|
| `docs/arc-stage10-blueprint-fallback-20261126.md`（B-32 调研） | F-6 的方案来源；本文 §F-6 的「运行 E 反证」为其增加一条边界（YAML 缺陷可自发消失，不能只靠它解释失败） |
| `docs/arc-p194-p199-heterogeneous-review-20261126.md` | B-32/B-31a 合入内容的复审；本次运行 E 的产物对账为它提供第一个**真实产出形态**的样本 |
| `spec/arc-stage10-blueprint-yaml-robust/`（DESIGN v2.0） | §5.1 五项边界的关闭记录；本文 §2.3 反事实所用的门即该批交付 |
| `docs/arc-longrun-progress-observability-20261126.md`（B-31 调研） | F-9 的方案来源；本文 §2.3「日志行序」为其根因提供现场实证 |
