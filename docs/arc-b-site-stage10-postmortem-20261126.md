# B 站 Stage 10 排查、修复与故障分析完整记录（2026-11-26）

> **性质**：Layer-0 事后分析（postmortem），零代码 / 零门禁变更。本文只做取证、归因与决策回溯，不新增实施承诺。
> **范围**：B 站（`scott-lau-GTR-Pro.local`）run 目录 `~/arc-runs/g7-baseline`，topic 为「LNN 内部动力学信号的分层漂移监测：τ-KL 粗筛与 Fréchet 伴随状态变点检测的金融时序比较研究」，Stage 10（CODE_GENERATION）自 2026-11-25 13:48Z 起的全部尝试（运行 A–E 为全管线；**运行 F 为 11-26 部署 `dc5f80b` 后的 Stage 10 单阶段验证**，见 §2.4）。
> **证据来源**：`attempts/stage-10/attempt-{1,2,3,4}.json`、`stage-10/code_agent_log.json`、`stage-10/architecture_spec.yaml`、`stage-10/stage_health.json`、`stage-10/agent_runs/`、`stage-10/experiment/`、`stage-10/ablation_warning.json`、`stage-10/experiment_spec.md`、`stage-10/decision.json`、`cost_log.jsonl`、`events.jsonl`、`checkpoint.json`、`lease.json`、`/tmp/p19{1,2}_stage12.log`。
> **方法**：读码锚点 + 远端文件采样 + 本地测试复跑。未做受控实验，未改动远端任何源码。
> **边界**：① 单一 run、单一 topic；② 时间戳统一 UTC，括号内为 B 站本地时间（UTC+8）；③ attempt 编号为跨 run 全局计数，不等同于「某一次 stage 重试」；④ 本文不评价 topic 本身的科学价值。

---

## 0. 结论摘要

1. **Stage 10 在全管线中失败 5 次，根因是 5 个不同缺陷的串联**，不是单一 bug：出口门缺失 → 截断/围栏 → repair 整体替换 → 文件提升 → 入口生成无兜底 → 蓝图 YAML 失效导致单发退化。部署修复后再做 1 次单阶段验证（运行 F），失败点已提前到模块边界（§2.4）。
2. **每修一个，下一个才暴露**。P-178、P-190、P-191、P-192 四次修复各自在 B 站现场被日志证实生效，但 Stage 10 仍未通过。
3. **运行 E 的终态（2026-11-26 11:50:39Z）把阻塞点固定为「实验内容不成立」**：Stage 10 在 **15 769.77 s（4 h 22 m 50 s）** 后 `exit_code=75` 失败，3 次内部重试全部被「主题-实验对齐门」否决。**这是护栏在正确工作，不是护栏误报。**
4. **运行 E 同时给出了两条正反证据**：① **反证**——本轮蓝图（36 831 字符）**解析成功**，`Parsed blueprint: 4 files` + `Phase 2: Sequential generation (blueprint-guided)`，F-6 的 YAML 缺陷**未复发**；② **正证**——`data.py` 生成后**提取为空**（不是"模块太大写不下"，见 §F-7b 订正）、被 `synthetic_finance.py` 顶替，`main.py` 112 行停在 `df` 且无 `METRIC_DEF`。真正的瓶颈是**每模块调用的截断提取兜底缺失**，不是生成预算。
5. **结构性缺口已合入 `main` 并完成首次部署（2026-11-26，`dc5f80b` / PR #57）**：B-32（M1/M2/M3）、B-31a、B-33 M1、B-34（M1-a/M1-b + F-1..F-6）。部署后首轮 Stage 10（运行 F，§2.4）在 **1 489.86 s（24 m 50 s）** 显式失败，错误为 `data.py: module extraction failed (truncated)`，并在 `steps.jsonl` 留下 `generate_file/failed` 记录——运行 E 的 4 h 22 m 静默浪费不再复现。
6. **成本已可量化**：5 次全管线运行 Stage 10 墙钟合计约 **12.7 小时**（1 491 + 13 007 + 14 564 + 约 9 400 + 15 770 s）；运行 E 单轮 91 次 LLM 调用，`code_agent_log.json` 中 `truncated` 命中 5 次（蓝图 + 四个模块各一次）。**运行 F（部署后单阶段）仅 1 490 s**，失败成本降到 1/10.6。
7. **运行 F 给出新的一手事实**：`data.py` 的 32768 调用 `completion_tokens=32768`（打满上限）仍 `finish_reason=length`，而 `config.py` 只需 11 190。P-205 的「2–4.5k tokens」体积表**不含 `data.py`**（当时它缺失），因此不能据此否定容量问题；「不加预算」的前提需按 §F-7b.7 重新裁决。
8. **社区案例复核把处置顺序改了**（§F-7b.8）：`finish_reason=length` 只证明**请求上限**到了，不证明引擎只能输出 32768（OpenAI 官方文档）；Aider 基准与 RPG 论文都表明长输出 ≠ 完整实现，而 RPG 明确要求规划到**函数**。因此把「加预算」从第一选择降为**条件兜底**，先做引擎上限探针（Phase 0），再按「文件预算 + 符号契约」（C+）拆分，函数级分块（C++）默认关。
9. **Phase 0 探针已执行，结论：32768 是自设，不是引擎硬顶**（§F-7b.9）：halogen 服务 `--max-tokens-cap 65536`，`max_tokens=70000` 被 400 拒绝并明确提示「cap is server policy」；同时发现 `completion_tokens` **混合 reasoning 与正文**，默认模板 `xhigh` 下代码任务的 reasoning 占 **76–85%**，`enable_thinking=false` 可归零。由此新增选项 **E（思考预算分档）**，优先级高于 A'；A'（按文件 65536）技术可行但需权衡 batch-1 下约 10.7 分钟的 GPU 独占。
10. **是否关闭思考：文献 + 本地 A/B 的裁决是「限流而非关闭」**（§F-7b.10）：Qwen3 官方把关闭定义为 hard switch、等价退回非推理模型（能力下降），vLLM 与 Qwen3 技术报告都把**思考预算**作为一等能力，过度思考文献则说明低难度任务上多花 token 收益极小。本地四种模式在语法/需求覆盖代理上无可见差异，但默认模式把 3–7k token 花在思考上——**`data.py` 触顶的根因是思考挤占代码，而不是代码写不下**。落地策略：蓝图/算法类保留思考（预算兜底 65536），机械模块用 `reasoning_effort=low` 或 `reasoning.max_tokens≈2048`，硬关闭只作最后手段。

---

## 1. 运行环境与证据面

| 项 | 值 |
|---|---|
| 主机 | `scott-lau-GTR-Pro.local`（Linux，Python 3.x venv `~/arc-venv`） |
| 仓库 | `~/AutoResearchClaw-main` |
| run 目录 | `~/arc-runs/g7-baseline` |
| 配置 | `~/config.g7-field.yaml`（`experiment.mode: sandbox`、`time_budget_sec: 600`） |
| 模型 | `halogen-qwen3.8-flash-next`（无单价配置 → `cost_usd=0.0`、`source=unknown`） |
| 启动方式 | `tmux`（`p191-stage12` / `p192-stage12` → 已终止；运行 F 为 `p207-stage10`，已结束） |
| 观测缺陷 | `heartbeat.json` 只在 stage DONE 后写，`logger.info` 因无日志配置被丢弃 → 现场日志只含 WARNING |

---

## 2. 完整时间线

### 2.1 五次全管线运行 / 五次失败（另有运行 F 单阶段，见 §2.4）

| # | 时窗（UTC） | 时长 | 结果 | 关键错误 | 触发修复 |
|---|---|---|---|---|---|
| A | 11-25 13:48:50 → 14:13:41 | 1 491 s（25 min） | `exit_code=0` | 无（但产出仅 `experiment/` 2 文件、`architecture_spec.yaml` 4 478 B） | P-178（出口门缺失，穷产物被放行） |
| B | 11-25 14:42:25 → 18:19:12 | **13 007 s（3 h 37 m）** | `exit_code=75` | `main.py has a syntax error: unterminated string literal (line 130)` | **P-190 / B-28** |
| C | 11-25 21:33:16 → 11-26 01:36:00 | **14 564 s（4 h 3 m）** | `exit_code=75` | `main.py missing if __name__ == "__main__"; never prints METRIC_DEF` | **P-191 / B-29** |
| D | 11-26 04:51 → 07:27（人工终止） | 约 2 h 36 m | 未记录 attempt（阶段未结束） | `entrypoint attempt 1/2 truncated` ×2，越界第 517 行；`dedicated entrypoint generation failed`；`Repair attempt returned invalid Python for data.py` ×4 | **P-192 / B-30** |
| E | 11-26 07:27:49 → **11:50:39** | **15 770 s（4 h 22 m 50 s）** | `exit_code=75`（retryable） | 3 次内部重试全部 `Topic-experiment misalignment` → `Persistent topic-experiment misalignment after all regen attempts` | **B-32 / B-31a / B-33**（当时本地已修、未部署；2026-11-26 随 `dc5f80b` 部署） |

> A 的 `exit_code=0` 是「没有出口门」的直接后果：只有 2 个文件、蓝图 4.5 KB 的产物被判通过，说明当时的成功判据只看「能跑」。
> E 是本记录的重心：它是**唯一一次蓝图解析成功**的全管线运行（详见 §2.3），因此暴露的问题层次比前四次更靠后。
> 运行 F（部署 `dc5f80b` 后的 Stage 10 单阶段验证，1 489.86 s 失败）单列于 §2.4；它不是一次完整 run，故不计入本表。

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

> 运行 F（部署后）测得同一模块的 32768 调用确实 `finish_reason=length` 打满——「无闭合围栏」是截断的**症状**，不是独立原因；见 §F-7b.7。

**日志交错顺序（B-31a 的现场实证）**：`/tmp/p192_stage12.log` 里所有 `logger.warning` 行（无缓冲 stderr）先写出，而 `print` 的管道横幅——

```text
ResearchClaw v0.5.0 — Starting pipeline
[g7-baseline] Stage 10/23 CODE_GENERATION — running...
```

——直到进程退出才出现在文件**末尾**。这是「块缓冲 + 默认 WARNING 级别」双杀的教科书形态，与 B-31a 的根因分析完全一致。

**部署状态核对**（运行 E 当时的历史读数；`~/AutoResearchClaw-main` 是源码副本、非 git 仓库）：

```text
researchclaw/runtime/logging_setup.py      不存在
researchclaw/pipeline/codegen_evidence.py  不存在
researchclaw/pipeline/step_journal.py      不存在
runner.py:      _write_stage_start          0 命中
code_agent.py:  _fold_trailing_colon_items  0 命中
```

即本轮跑的是 P-192 之前的代码：`steps.jsonl` / `codegen_decision.json` / `codegen_evidence.json` 三个新产物在 `stage-10/` 中**均不存在**（`ls` 已确认）。

### 2.4 运行 F：部署后的 Stage 10 单阶段验证（2026-11-26）

**部署**：从 `dc5f80b`（PR #57）用 `git archive` 导出 48 345 130 B，两端 SHA-256 一致（`7b8e9e22…c794b`）；旧代码保留为 `AutoResearchClaw-main.prev-20261126`，旧 Stage 10 保留为 `stage-10.bak-p207`。导入校验 `IMPORT_OK`；`ModuleExtractionError` / `_close_unterminated_fence` / `_strip_comments` / `_class_has_behavior` / `_write_stage_start` 均命中。

**命令**（只跑 Stage 10，不推进 Stage 11）：

```bash
~/arc-venv/bin/python -m researchclaw run --output ~/arc-runs/g7-baseline \
  --config ~/config.g7-field.yaml --from-stage CODE_GENERATION --to-stage CODE_GENERATION \
  --log-level INFO --log-file ~/arc-runs/p207-stage10.log
```

| 时刻（CST / UTC） | 事件 | 读数 |
|---|---|---|
| 21:27:45 / 13:27:45 | Stage 10 启动，`in_progress_stage=10` 落盘 | `checkpoint.json`（B-33 L0 生效） |
| 21:30:21 | 蓝图首轮 8192 `finish_reason=length` → 32768 | 日志 |
| 21:38:38 | 蓝图 **19 943 字符 / 3 files** 解析成功（`variant=retry`） | `steps.jsonl` seq 1 |
| 21:40:40 | `config.py` 首轮 8192 截断 → 32768 | 日志 / `cost_log.jsonl` |
| 21:43:02 | `config.py` **372 行 / 1 class** 提取成功（completion 11 190） | 日志 |
| 21:45:11 | `data.py` 首轮 8192 截断 → 32768 | 日志 / `cost_log.jsonl` |
| 21:52:35 | `data.py` 的 32768 **仍 truncated**（completion **32 768**）→ 记失败账 → 抛 `ModuleExtractionError` | 日志 / `steps.jsonl` seq 2 |
| 21:52:35 | Stage 10 **FAILED（1 489.9 s）**；`--to-stage` 正常停止 | `stage_health.json` / `decision.json` |

**账本**（`stage-10/steps.jsonl`，首次在现场出现；摘要 only）：

```json
{"seq":1,"step_id":"blueprint","variant":"retry","status":"done","truncated":false,"code_version":"0.5.0+6878c4c8"}
{"seq":2,"step_id":"generate_file","variant":"data.py","status":"failed","truncated":true,"model":"halogen-qwen3.8-flash-next"}
```

**与运行 E 的对照**：

| 维度 | 运行 E（旧代码） | 运行 F（部署后） |
|---|---|---|
| 模块失败后 | `Empty code` WARNING → `continue` → 继续生成其余模块 → 对齐门否决 | 立即 `steps.jsonl(failed)` + `ModuleExtractionError` → Stage 10 FAILED |
| 墙钟 | 15 769.77 s（4 h 22 m 50 s） | **1 489.86 s（24 m 50 s）**，10.6× |
| 失败位置 | 对齐门（自然语言判词） | 生成链（结构化错误 + 账本） |
| 日志 | 仅 WARNING（INFO 被默认级别吞掉） | INFO 级蓝图/模块进度全部落盘（B-31a） |
| 重入 | checkpoint 停在 11，`--resume` 会跳过 10 | `in_progress_stage=10`，`--resume` 重入 10（B-33 L0） |
| `experiment/`、`codegen_evidence.json` | 六文件 / 不存在 | 均不存在（失败早于写盘与出口门） |

**判定**：B-34 M1-b、B-33 L0、B-31a 在真实现场生效；**B-32 M2 的出口证据门仍未被触达**（失败发生在生成阶段），C-27 记「提前失败分支已验、四模块齐全分支待验」。M1-a 未被本轮单独观测（无「完整但漏闭合围栏」的响应），由 24 例单测覆盖。

### 2.5 运行 H：M4（tiered 思考预算）部署后的 Stage 10 验证（2026-11-27）

**部署**：工作树快照 42 734 592 B（两端 SHA-256 `4bd6513d…0ade` 一致），旧代码保留为 `AutoResearchClaw-main.prev-p207`；`config.g7-field.yaml` 追加 `experiment.code_agent`（`thinking_policy: tiered`、`thinking_mechanical_effort: low`、`thinking_core_max_tokens: 2048`、`file_max_lines: 300`），`researchclaw validate` 通过；旧 Stage 10 保留为 `stage-10.bak-p210`。

**首次启动（运行 G）暴露配置缺陷**：yaml 写入后 `policy` 仍为 `off` —— [`_parse_code_agent_config`](../../researchclaw/config.py#L1603-L1623) 逐字段构造 `CodeAgentConfig`，新增的四个键被静默丢弃。修复（补四个字段 + 2 例单测）后重新部署，复读 `policy=tiered effort=low core=2048 lines=300`，再启动运行 H。

**运行 H（attempt 1）时间线**：

| 时刻（CST / UTC） | 事件 | completion | 说明 |
|---|---|---|---|
| 23:23:39 / 15:23:39 | Stage 10 启动（租约顺延后） | — | 前次租约未释放，等了 7 min |
| 23:26:14 | 蓝图首轮 8192 截断 → 32768 | 8 192 → 29 720 | **蓝图未分档**（设计阶段） |
| 23:33:23 | 蓝图解析成功：5 files / 51 565 B | — | `steps.jsonl` seq 1 |
| 23:33:23 | `config.py` tier `{'reasoning_effort': 'low'}` | **2 542** | 39 s，**无截断**（运行 F：8 192 截断） |
| 23:34:02 | `data.py` tier `{'reasoning': {'max_tokens': 2048}}` | **6 249** | 92 s，**无截断**（运行 F：32 768 仍截断→失败） |
| 23:35:34 | `models.py` 同档 | 6 018 | 87 s，无截断 |
| 23:37:01 | `monitors.py` 同档 | 8 192 → **10 387** | 唯一一次升级，第二次成功 |
| 23:41:08 | `main.py` 同档 | 5 489 | 无截断 |
| 00:00:50 | Phase 2 完成：**2 211 s / 13 次 LLM** | — | 5 个模块全部产出（config 217 行、data 320 行、models 295 行 4 类） |
| 00:00:50 | 入口契约不满足 → 专用入口生成 | — | `main.py` 无 `__main__`、无 `METRIC_DEF` |
| 00:12:57 | 入口第 2 次成功（7 011 字符） | — | 第 1 次 `syntax error (line 1)` |
| 00:12:57 | `data.py` 代码校验失败（1 error）→ repair 2 次返回非法 Python → abort | — | **新阻塞点**：repair 质量，不是生成截断 |
| 00:15:03 | `CRITICAL validation issues remain after 5 repair attempts` → attempt 1 失败 → 自动重试 | — | 运行在 attempt 2 被人工终止（证据已足） |

**与运行 F 的对照**：

| 指标 | 运行 F（M1 后） | 运行 H（M4 后） |
|---|---|---|
| 首轮 8192 截断的模块数 | 4/4（`config`/`data`/`models`/`methods`） | **1/5**（仅 `monitors.py`） |
| `data.py` 结果 | 8 192 → 32 768 仍截断 → `ModuleExtractionError` → FAILED（1 489.86 s） | **6 249 一次成功**，320 行 |
| 模块阶段耗时 | 未进入（24 m 50 s 即失败） | Phase 2 2 211 s（36.8 min），五模块齐全 |
| 失败位置 | 生成链（提取为空） | 生成后校验（`data.py` 1 个错误 + repair 不可用） |

**判定**：C-28 的**目标达成**——tiered 让 4/5 模块在首轮 8192 内完成，`data.py` 从「必失败」变为「一次成功」；Stage 10 仍未 DONE，但阻塞点已从「生成/提取」推进到「生成后的代码校验与 repair」，属另一层问题（repair 连续返回非法 Python）。

**新观察（待立项）**：① 蓝图与对齐仍走默认 `xhigh`（蓝图 29 720/32 768）；② `data.py` 的 1 个校验错误在 5 次 repair 中始终无法修好（2 次直接返回非法 Python），说明 repair 提示与校验器的错误描述可能不匹配；③ 人工终止 attempt 2 时 `experiment/` 仅写入 `main.py`，其余模块留在内存映射与 `agent_runs/`。

#### 2.5.1 本轮操作流水（可重放）

```bash
# 1) 主控站打包（排除 .git/.venv/__pycache__/.pytest_cache/artifacts/.trae/image）
tar -czf D:\tmp\arc-p210.tgz -C d:\AutoResearchClaw-main\AutoResearchClaw-main \
  --exclude=.git --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache \
  --exclude=artifacts --exclude=.trae --exclude=image .
scp D:\tmp\arc-p210.tgz scott-lau@<B_HOST>:~/   # sha256 4bd6513d…0ade

# 2) B 站替换（旧代码保留）
cd ~ && mv AutoResearchClaw-main AutoResearchClaw-main.prev-p207
mkdir AutoResearchClaw-main && tar -xzf arc-p210.tgz -C AutoResearchClaw-main

# 3) 配置（幂等插入 experiment.code_agent）
#    thinking_policy: tiered / thinking_mechanical_effort: low
#    thinking_core_max_tokens: 2048 / file_max_lines: 300
cp ~/config.g7-field.yaml ~/config.g7-field.yaml.bak-p210
# + 插入后 `researchclaw validate --config ~/config.g7-field.yaml` → passed

# 4) 旧 Stage 10 归档 + 单阶段重跑
mv ~/arc-runs/g7-baseline/stage-10 ~/arc-runs/g7-baseline/stage-10.bak-p210
cd ~/AutoResearchClaw-main && ~/arc-venv/bin/python -m researchclaw run \
  --output ~/arc-runs/g7-baseline --config ~/config.g7-field.yaml \
  --from-stage CODE_GENERATION --to-stage CODE_GENERATION \
  --log-level INFO --log-file ~/arc-runs/g7-baseline/p211-stage10-h.log

# 5) 中途发现的配置缺陷（G）：修 _parse_code_agent_config 后 scp 单文件并重启
# 6) 证据收集：p211-stage10-h.log / stage-10/{steps.jsonl,code_agent_log.json,experiment}/
#    attempts/stage-10/attempt-5.json（运行 F）/ cost_log.jsonl（运行 H 段 20 次调用）
# 7) 终止 attempt 2（保留证据），未回滚代码与配置
```

**回退点**：`AutoResearchClaw-main.prev-p207`、`config.g7-field.yaml.bak-p210`、`stage-10.bak-p210`、`stage-10.bak-p210-g`（运行 G 的中断态）。

### 2.6 运行 I：B-36 P0（repair 取证）部署后的 Stage 10 验证（2026-11-27）

**部署**：工作树快照 42 751 487 B（本地 / B 站 SHA-256 `a5340cfa…19c5` 一致）；旧代码保留 `AutoResearchClaw-main.prev-p210`，旧 Stage 10 保留 `stage-10.bak-p213`；配置未变（沿用 p210 的 tiered 四键）。部署校验：`IMPORT_OK`、`trace_name=repair_trace.jsonl`、`policy=tiered core=2048`、`_record_repair_trace` 8 处引用；`researchclaw validate` 通过。tmux `p213-stage10`，日志 `~/arc-runs/g7-baseline/p213-stage10.log`。

**时间线（CST）**：

| 时刻 | 事件 | 读数 |
|---|---|---|
| 00:31:09 | 运行 I 启动 | — |
| 00:41:08 | 蓝图完成（8 192→32 768） | 63 135 B / 4 files；`steps.jsonl` seq 1；`code_version=0.5.0+16dc7ee1` |
| 00:54:17 → 01:11:20 | CodeAgent 硬校验 5 次（19/9/10/10/10 个 CRITICAL）+ 4 次 repair | 每次 `Repair updated 2 file(s)`（data.py + main.py）仍未清零；01:11:20 `Max repair attempts reached` |
| 01:12:35 | Phase 2 完成 | 2 465.3 s / 13 次 LLM / 1 次沙箱 / score 1.00 |
| 01:15:58 | 专用入口生成成功 | 4 294 字符，首次即过 |
| 01:15:58 | `data.py` 校验失败 attempt 1/5 | `syntax / line 46 / col 20 / '(' was never closed` |
| 01:17:01 | 第 1 次 per-file repair 被拒 | 响应 3 189 字符、`truncated=true` |
| 01:17:51 | 第 2 次 per-file repair 接受 | 响应 1 620 字符、`truncated=false` |
| 01:17:51 | 12 处 UnboundLocalError 风险自动修复 | models 1 / methods 7 / main 4 |
| 01:25:03 | 项目级 repair 完成 | 8 192 截断→32 768；合并 4 文件、保留 `config.py`；`experiment_config.py` 因未知文件名被忽略；`fixed 0/1` |
| 01:25:12 → 01:29:50 | 对齐门连否 2 次后通过 | 第 2 次重生成后 `Code aligned` |
| 01:29:53 | 入口契约再次不满足 → 重新生成 | 对齐重生成覆盖了 `main.py` |
| 01:34:12 | 入口第 1 次被拒 | `main.py has a syntax error: invalid syntax (line 1)` |
| 01:39:07 | 入口第 2 次成功（4 519 字符） | — |
| 01:39:07 | **证据门失败**：`blueprint_symbols_missing` | `data.py` 缺 7 个声明符号（`build_external_controls` / `compute_features` / `inject_regime_shifts` / `load_raw_yfinance` / `make_window_dataset` / `prepare_scenario_bundle` / `standardize_features`）；磁盘 `data.py` 仅 1 422 B |
| 01:39:07 | executor 判定 `Stage CODE_GENERATION failed (attempt 1/3) — retrying` | 进入 attempt 2 全量重生成 |
| 01:39:15 → 01:39:27 | attempt 2：GitHub code search 401×4 → `0 repos`；Phase 1 蓝图启动 | B-35 P0 缺口再次复现 |

**`repair_trace.jsonl`（7 行，摘要 only）**：

| # | phase | file | attempt | 关键字段 |
|---|---|---|---|---|
| 1 | `validation_failed` | data.py | 1/5 | `errors: syntax / 46 / 20 / "'(' was never closed"` |
| 2 | `repair_request` | data.py | 1/5 | prompt 51 111 chars；response 3 189；`truncated=true` |
| 3 | `repair_rejected` | data.py | 1/5 | `reason=invalid_python`（旧码；本地已改为优先 `truncated`） |
| 4 | `validation_failed` | data.py | 2/5 | 同 #1 |
| 5 | `repair_request` | data.py | 2/5 | prompt 同 sha `b5656f37…`；response 1 620；`truncated=false` |
| 6 | `repair_accepted` | data.py | 2/5 | `accepted=["data.py"]` |
| 7 | `project_repair` | — | — | prompt 52 812；response 51 142；accepted 4 / rejected `config.py`；`reason=merged` |

**三问的现场回答**：

1. **错误是否进 prompt**：是。`validation_failed.errors` 带 `syntax/line/col/message`，`issues_text` 由 `format_issues_for_llm(errors_only)` 组装进 `code_repair` 提示。但两次 repair 的 prompt sha **完全相同** ⇒ 首次被拒的原因没有回传；第二次成功只是同一请求的重新采样。
2. **响应为何被拒**：第 1 次 `truncated=true`（3 189 字符）。per-file repair 走 `_chat_with_prompt` 且不传 `max_tokens`/`extra_body` ⇒ 引擎默认 8 192 输出 + 默认思考档，思考挤占预算（与 B-34 同源）；项目级 repair 有 8 192→32 768 升级（日志 `retrying with 32768`），per-file 没有。
3. **计数口径**：per-file 的 `attempt x/5`/abort 用 `invalid_returns`（连续不可解析次数，本次 1 次后被接受，未 abort）；项目级 `fixed 0/1` 统计关键词过滤后的 **warning 文本**，不是文件数；trace 的 `accepted/rejected` 是**文件级**。三者不同源。且该 1 个 critical（`config.py` 文件名遮蔽 stdlib）**无法靠内容重写修复**——模型返回改名后的 `experiment_config.py`，被 `unknown file` 规则忽略。

**判定**：C-12 现场关闭（5/6 类事件；`repair_aborted` 未触发属正常路径）。运行 I 的代码不含 agent 站点与 `reason=truncated` 细化，二者由 C-13 单测覆盖，现场验证留到下一次部署。

**额外收获（B-34 M4 符号契约的首次现场命中）**：attempt 1 的失败点已从「repair 不可用」后移到出口证据门——对齐重生成把 `data.py` 写成 1 422 B 的薄壳（语法合法），`check_symbol_contract` 以 `blueprint_symbols_missing` 一次列出 7 个缺失符号并显式失败，总耗时 68 min（**不是**数小时后才失败）。同时说明对齐重生成路径缺少「不得把已交付文件替换成空壳」的守卫，属 B-36 P1/P2 的新输入。

**attempt 2**：executor 自动重试（`attempt 1/3`），01:39:27 重新进入 Phase 1 蓝图；其 `repair_trace.jsonl` 与 attempt 1 共用同一文件（append-only，attempt 1 的 7 行保留）。

**操作流水（可重放）**：

```bash
# 1) 主控站打包（与 §2.5.1 同一排除集）
tar -czf D:\tmp\arc-p213.tgz -C d:\AutoResearchClaw-main\AutoResearchClaw-main \
  --exclude=.git --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache \
  --exclude=artifacts --exclude=.trae --exclude=image .
scp D:\tmp\arc-p213.tgz scott-lau@<B_HOST>:~/   # sha256 a5340cfa…19c5

# 2) B 站替换（旧代码保留）
cd ~ && mv AutoResearchClaw-main AutoResearchClaw-main.prev-p210
mkdir AutoResearchClaw-main && tar -xzf arc-p213.tgz -C AutoResearchClaw-main
# 配置未改；导入自检：IMPORT_OK / repair_trace.jsonl / tiered core 2048

# 3) 旧 Stage 10 归档 + 单阶段重跑（tmux p213-stage10 内）
mv ~/arc-runs/g7-baseline/stage-10 ~/arc-runs/g7-baseline/stage-10.bak-p213
cd ~/AutoResearchClaw-main && ~/arc-venv/bin/python -m researchclaw run \
  --output ~/arc-runs/g7-baseline --config ~/config.g7-field.yaml \
  --from-stage CODE_GENERATION --to-stage CODE_GENERATION \
  --log-level INFO --log-file ~/arc-runs/g7-baseline/p213-stage10.log

# 4) 证据：p213-stage10.log / stage-10/{repair_trace.jsonl,steps.jsonl,
#    validation_report.md,code_complexity.json,experiment_spec.md}
```

**回退点**：`AutoResearchClaw-main.prev-p210`、`config.g7-field.yaml.bak-p210`、`stage-10.bak-p213`。

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

### F-6 蓝图 YAML 失效 → 顺序生成被跳过 → 单发退化（已修：B-32 M1/M2，已部署）

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
- **状态**：**已修复、随 `dc5f80b` 部署，运行 F 已验**。P-194 修折叠与重试、P-197 加四项证据门、P-202 硬化五项边界；规格见 `spec/arc-stage10-blueprint-yaml-robust/`（DESIGN v2.0）。运行 F 中蓝图 19 943 字符 / 3 files 一次解析成功（`steps.jsonl` `blueprint/retry/done`）。
- **运行 E 终态的反证**：11-26 最后一次运行中蓝图 **36 831 字符解析成功**（`Parsed blueprint: 4 files` → `Phase 2: Sequential generation (blueprint-guided)`），F-6 的 YAML 缺陷**未复发**。因此 E 的失败不能归因于 F-6。

### F-7 主题-实验对齐门（既有护栏，运行 E 首次真实触发）

- **机制**：`_code_generation.py` L1780-1910 先让模型自评「代码是否真的检验了 topic」，不合格则最多重生成 2 次并复检；仍不合格则 FAILED（L2020）。
- **运行 E 判词（节选，属正确判断）**：

  > main.py 只做合成 AR 式隐状态模拟，没有实例化或训练 LNN；τ-KL 不是对 LNN 内部动力学的粗筛，而是对差分序列的高斯均值/方差 KL；Fréchet 是对窗口累积偏差的离散距离，不是伴随状态变点检测；没有分层漂移架构，没有金融时序数据管线。

  以及消融判词：12 个条件只是 `DRIFT_TYPES × DRIFT_SPEEDS × NOISE_LEVELS` 的标签组合，无参数差异、无代码分支、无消融开关。

- **评价**：**这是护栏按设计工作**。它把「假实验」挡在 Stage 12 之外，代价是 Stage 10 显式失败而不是静默带着穷产物继续。
- **运行 E 终态的三次判词**（11-26 最后一轮，节选）：① `main.py implements a generic synthetic AR-like hidden state simulation and does not instantiate or train a Liquid Neural Network`；② `The code only generates synthetic financial time series with injected regime shifts ... and does not implement the core methods`；③ 消融判词 `all 12 conditions are configuration-identical at the level visible in this snippet`。
- **问题**：护栏只负责否决，不提供「怎么改才合格」的有效路径。运行 E 中它连否 3 次 ×2 轮，而代码侧真正缺的是 `data.py`（空返回）与模块体量——**护栏的判词是对的，但它不是可执行的修复线索**。
- **运行 F 未触达**：部署后失败提前到 `data.py` 模块边界（§2.4），对齐门尚未开始判断。这符合「先结构、后语义」的分层：先确保模块取回，再谈内容是否对齐。

### F-7b 模块级截断提取兜底缺失（订正；B-34 已实施并部署）

> **订正说明（2026-11-26，P-205）**：本节的初版把根因写成「模块级生成容量不足 / 四模块全部在 32 768 打满」。用代码锚点 + 交付体积复核后，该归因**不成立**，已按下列读数改写。原文错误保留在 §F-7b.3 以备追溯。
> **再订正（2026-11-26，运行 F）**：部署后直接测到 `data.py` 的 32768 调用打满（`completion_tokens=32768`），即「容量」问题对 `data.py` **确实存在**；P-205 的体积表不含该文件。完整读数与选项见 §F-7b.7。

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

> **2026-11-26 更新（运行 F，见 §2.4）**：该结论对 `config.py`/`models.py`/`methods.py` 成立，但**对 `data.py` 不成立**——部署后实测其 32768 调用 `completion_tokens=32768` 打满仍 `finish_reason=length`；体积表当时不含 `data.py`。裁决见 §F-7b.7。

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

#### F-7b.7 部署后复测（运行 F）：`data.py` 确实超出 32768

| 项 | 读数（`cost_log.jsonl` / `p207-stage10.log`） |
|---|---|
| `config.py` 首轮 | `completion_tokens=8192`（`finish_reason=length`） |
| `config.py` 升级后 | `completion_tokens=11 190`（stop）→ 372 行提取成功 |
| `data.py` 首轮 | `completion_tokens=8192`（length） |
| `data.py` 升级后 | **`completion_tokens=32 768`（length，打满）** → 仍 truncated |
| 结果 | `steps.jsonl` `generate_file/data.py/failed`，Stage 10 于 1 489.86 s 失败 |

**这是对 P-205 订正的再订正**：P-205 用「实际交付体积 2–4.5k tokens」撤销了「模块超容量」，但那张表只统计了**已交付**的 `methods/config/models/main`——`data.py` 当时**缺失**，从未被测到。运行 F 首次直接观测到 `data.py` 的输出上限。

**因此当前有两类事实并存**：
1. `config.py` 的问题确实是「首轮 8192 太小、响应漏了闭合围栏」——M1-a/M1-b 已覆盖；
2. `data.py` 的问题是**输出真的超过 32768**——M1-a/M1-b 只能让它快速失败，不能让它生成成功。

**可选处置（待裁决，本批未实施）**：

| 选项 | 内容 | 代价 / 风险 |
|---|---|---|
| A | 单模块预算 32768→65536（与 B-30 入口生成同额） | 最小改动；但 3 万+ token 的模块可能冗长难维护，「不加预算」约束需重新裁决 |
| B | 实施 B-34 M2（模块 prompt 只注入依赖子集蓝图） | 主要降低**输入**过载；未必减少输出体积 |
| C | 蓝图阶段约束单文件规模，或把 `data.py` 拆为 `data_io.py` + `synthetic.py` | 结构性、最稳；改动落在蓝图提示与顺序生成 |
| D | 维持现状，接受快速失败 | 无新工作，但 Stage 10 仍无法通过 |

倾向：**C 为主，A 作兜底**——先让单模块职责变小，再决定是否给 `data.py` 双倍预算。无论选哪条，`data.py` 的成功判据仍由 B-32 M2 证据门在出口把关。

> **后续（2026-11-26）**：本节四个选项已按社区案例复核，结论调整为「**先探针、再拆分、加预算降为条件兜底**」，见 §F-7b.8。上表保留为初始判断。

#### F-7b.8 社区案例复核与优化方案（2026-11-26）

> 对象：§F-7b.7 的 A/B/C/D。方法：T1 源码/论文 + T2 官方文档 + T3 社区问答；每条标注证据层与抓取日期。

| ID | 来源（层 / 日期） | 原文要点 | 含义 |
|---|---|---|---|
| E-1 | [OpenAI API Reference](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create/)（T2，2026-11-26） | `finish_reason="length"` = "the maximum number of tokens specified in the request was reached" | `length` 只证明**请求上限**到了，不证明引擎硬顶 |
| E-2 | [OpenAI 文本生成指南](https://platform.openai.com/docs/guides)（T2） | `length`：incomplete output due to `max_tokens` or token limit | 同上；32768 不是既成事实的硬顶 |
| E-3 | [OpenAI 社区问答](https://community.openai.com/t/is-there-also-a-situation-where-gpt-stops-generating-so-we-need-to-make-it-continue-manully/426194)（T3） | 可用 `finish_reason=length` 检测后提示续写 | 仅线索；代码续写有重复/缩进风险，不作主路径 |
| E-4 | [Aider 编辑格式](https://aider.chat/docs/more/edit-formats.html)（T2） | `whole` 返回整文件；`diff` 只返回改动部分 | 整文件可靠但**成本随文件线性增长** |
| E-5 | [Aider 基准](https://aider.chat/docs/benchmarks.html)（T2，2023 数据） | "whole file… most reliable"；function calls 更差 | **不要用 diff 拼接拆**；应拆成更小的完整文件 |
| E-6 | [Aider repo map](https://aider.chat/docs/repomap.html)（T2） | 只发最相关片段，`--map-tokens` 默认 1k，按依赖图选 | 支持 B（输入瘦身），但不作用于输出 |
| E-7 | [Aider architect](https://aider.chat/docs/usage/modes.html)（T2） | architect 提议、editor 转成具体编辑；两请求有时优于一次 | 支持「先骨架、再实现」的两阶段 |
| E-8 | [SWE-agent](https://swe-agent.com/latest/usage/coding_challenges/)（T2） | `edit` 用行区间替换，编辑后做语法检查 | 支持「按符号增量写 + 语法校验」兜底 |
| E-9 | [MetaGPT `write_code.py`](https://github.com/geekan/MetaGPT/blob/main/metagpt/actions/write_code.py)（T1 源码，main） | "Only One file: implement THIS ONLY ONE FILE"、完整代码、不留 TODO；`@retry` 最多 6 次 | 文件级生成是主流，但社区文件普遍更小 |
| E-10 | [MetaGPT 论文](https://arxiv.org/abs/2308.00352)（T1，v7 2024-11-01） | SOP 流水线把复杂任务拆成子任务，中间产物互相校验 | 拆分必须有**契约**，不能只拆文件 |
| E-11 | [RPG / ZeroRepo](https://arxiv.org/abs/2509.16198)（T1，v6 2026-02-13） | 两级规划（模块→实现）；图编码 file structures / data flows / **functions**；LLM 擅长单函数/单文件，整仓仍难 | 最强支持 C，且粒度应到**符号** |

**复核裁决**：

| 原选项 | 裁决 | 理由 |
|---|---|---|
| A 32768→65536 | ⚠️ **降为条件兜底**（§F-7b.9 已证 cap=65536，技术上可行） | 长输出 ≠ 完整（E-5/E-11）；与「不加预算」冲突且不治本；batch-1 下单次 65536 约独占 GPU 10.7 min |
| B prompt 瘦身 | ⚠️ **降为辅助** | repo map（E-6）只减输入，不改变 `data.py` 的输出体积 |
| C 拆分 | ✅ **升为主方案 C+** | RPG 要求规划到函数（E-11）；MetaGPT 证明文件级可行但要小（E-9）；Aider 提示拆小文件而非 diff 拼接（E-5） |
| D 维持现状 | ⚠️ **仅短期可接受** | 已有 24 m 50 s 快速失败，可过渡，但不能作为终点 |

**优化后的执行顺序**：

| 阶段 | 内容 | 性质 |
|---|---|---|
| **Phase 0** | **引擎输出上限探针**：`max_tokens=65536` 请求，读 `completion_tokens` 与 `finish_reason`；停在 32768 即证明硬顶，A 直接排除 | 零代码，5 分钟，先做 |
| **Phase 1（C+）** | ① 蓝图加 `max_lines`/`max_symbols` 预算；② 超预算文件在**蓝图阶段**拆（如 `data_io.py` + `synthetic.py` + `schema.py`）；③ B-32 M2 从「文件集合」扩到「**符号集合**」（AST 类/函数名）；④ `steps.jsonl` 增加 `generate_file/done` | T1，主方案 |
| **Phase 2（C++）** | 若拆后仍超：先生成骨架（imports + 签名，必须 `ast.parse`），再按符号逐个实现，最后 **AST 拼装**（非文本拼接）+ 符号表校验；默认关 | T1，兜底 |
| **Phase 3（A'）** | 仅当 Phase 0 证明引擎支持 >32768 **且**仍有单文件超限时，按文件升到 65536，保留 fail-fast | T1，条件启用 |
| **Phase 4（B'）** | 模块 prompt 只注入依赖子集蓝图 + 符号摘要（E-6 思路），减少首轮 8192 截断 | 可选，辅助 |

**风险与反例**：

- 拆分引入跨文件导入/接口漂移 → 符号契约门 + import 检查；蓝图依赖必须同步重写。
- 函数级拼装复杂 → 默认关，只在超预算时触发；失败仍走 B-34 fail-fast。
- 长输出可能重复或跳过实现（Aider "lazy coding" 与 RPG 结论）→ A' 只能兜底，不能替代拆分。
- 引擎上限可能随容器重启变化 → 写入部署检查清单，每次部署后复测。
- B-32 M2 的**通过分支**仍需一次「四模块齐全」的重跑才能验证。

**建议批次拆分**：Phase 0（T3 运维读数）→ B-34 M4（文件预算 + 符号契约，T1/P1）→ 现场复跑 → B-34 M5（函数级分块，T1/P2）→ B-34 M2（prompt 子集，T1/P2）→ A'（T1/P3）。与原方案的关键变化：**加预算从第一选择降为最后兜底，拆分层级从文件下沉到符号**。

**证据降级（诚实清单）**：llama.cpp server README 抓取为空，引擎上限**未证**，必须探针；Aider 基准是 2023 年 GPT-3.5/4 数据，只取方向不带数值；OpenAI 社区回答属 T3，其事实部分已由 T2 官方文档替代；RPG 论文未复现，只取其设计主张。

#### F-7b.9 Phase 0 探针：引擎输出上限实测（2026-11-26，已执行）

**环境**（一手读数）：`halogen` 容器 `ghcr.nju.edu.cn/peonist-ai/halogen-flash-server:0.20.7`，进程为
`python3 /halogen/tools/serve_api.py --max-tokens-cap 65536 --context 1048576 --queue-timeout 3600`，监听 `127.0.0.1:8080 → 8731`。

| 探针 | 请求 | 读数 | 结论 |
|---|---|---|---|
| P-1 模型卡 | `GET /v1/models` | `max_model_len=1048576`、`context_length=1048576`、**`max_tokens_cap=65536`**、`max_tokens_default=8192` | 上限是 65536，默认 8192 |
| P-2 运行时 | `GET /props` | `n_ctx=1048576`、`default_generation_settings.params.n_predict=8192`、4 slots | 默认 8192 解释了首轮截断 |
| P-3 超限 | `max_tokens=70000` | HTTP 400：`max_tokens 70000 exceeds this server's cap of 65536. The cap is server policy, not a model limit…` | **65536 是服务策略**，不是模型极限 |
| P-4 边界内 | `max_tokens=40000` | 接受，`finish_reason=stop`、`predicted_per_second≈101.7` | 4 万预算可用 |
| P-5 源码 | `serve_api.py` L4249-4250 | `max_tokens_clamped_from/to`（prompt+预算超出上下文余量时下调） | 1 M 上下文下不会触发 |
| P-6 思考预算 | 同一问题三次 | 默认：`completion=45 / reasoning=26`；`reasoning_effort=low`：`48 / 26`；**`chat_template_kwargs.enable_thinking=false`：`28 / 0`** | 短问答下 reasoning 已接近下限，看不出 effort 差异（见 §F-7b.10 的代码任务复测） |

**结论**：

1. **运行 F 的 32768 是自设上限，不是引擎硬顶**。引擎允许到 65536，因此 A'（按文件提预算）**技术上可行**，不必先改引擎。
2. **`completion_tokens` 混合了 reasoning 与正文**：默认模板 `reasoning_effort=xhigh`，连一句短问答都花 26 个 reasoning token。`data.py` 的 32768 里很可能有相当比例是思考，而不是代码——这给出一条**比加预算更便宜**的新杠杆（见下 E）。
3. **`reasoning_effort=low` 在短问答上看不出效果**（26→26），但这是**任务饱和**导致，不是参数无效——代码任务复测为 6989→114（§F-7b.10）。`enable_thinking=false` 是硬开关，两者都能把 reasoning 压到接近 0。
4. **代价**：`predicted_per_second≈102`，65536 约需 10.7 分钟；服务是 batch-1，长请求期间其他客户端排队（错误文案明示）。因此 A' 的收益必须与「独占 GPU 10 分钟」权衡。
5. `max_tokens` 会被服务端按上下文余量下调（P-5），1 M 上下文下不构成约束。

**新增选项 E（由探针得出，优先级高于 A'）**：在代码生成请求上关闭或限定 thinking（`enable_thinking=false` 或 `chat_template_kwargs`），把同一份 32768 预算尽量留给代码正文。可行性取决于 ARC 的 LLM 客户端能否透传该参数——当前 `LLMClient.chat` 只构造 `model/messages/temperature/max_tokens`（[client.py L700-712](../../researchclaw/llm/client.py#L700-L712)），**尚无透传通道**，需新增一个窄开关；同时要评估 Qwen3 thinking 关闭对代码质量的影响（需 A/B）。

**Phase 0 的处置更新**：

| 阶段 | 更新 |
|---|---|
| Phase 0 | ✅ 已完成（P-1..P-6），结论：cap=65536，A' 可行，但新增 E 更优 |
| E（新） | ~~关闭/限定 thinking~~ → **按调用类型分档思考预算**（A/B 已完成，见 §F-7b.10）：设计类保留、机械类限流、硬关闭只作最后手段 |
| Phase 1（C+） | 不变，仍是主方案 |
| Phase 3（A'） | 由「需先证明引擎支持」变为「**可用**，但排在 C+ 与 E 之后」，且只对仍超限的单文件启用 |

**诚实边界**：本探针只测「参数是否被接受 / 预算如何分配」，**没有**跑一次真实 4 万 token 的代码生成来观测 `completion_tokens>32768`；该结论由 P-1/P-3/P-5 三处独立读数支撑（模型卡 + 服务策略报错 + 源码 clamp 逻辑）。E 的效果同样是单句问答读数，尚未在代码生成上验证——代码任务复测见 §F-7b.10。

#### F-7b.10 关闭思考会不会降低学术场景质量（文献 + 本地 A/B，2026-11-26）

**问题**：在 token 预算充足（可到 65536）的前提下，是否应当为代码生成关闭 thinking？关闭会不会让算法/学术内容变差？

**一、文献读数（按证据层）**

| ID | 来源（层 / 日期） | 原文要点 | 对本问题的含义 |
|---|---|---|---|
| R-1 | [Qwen3 官方博客](https://qwenlm.github.io/zh/blog/qwen3/)（T2，2025-04-29） | 思考模式「适合需要深入思考的复杂问题」，非思考模式「适用于对速度要求高于深度的简单问题」；「Qwen3 展现出可扩展且平滑的性能提升，这与分配的计算推理预算直接相关」 | **思考不是装饰**：性能随预算平滑变化，预算过小会掉分 |
| R-2 | [Qwen3 Technical Report](https://arxiv.org/abs/2505.09388)（T1，arXiv 2505.09388） | 思考/非思考融合进统一框架；专设 §4.3.3 Thinking Budget 与 §4.7.1「The Effectiveness of Thinking Budget」 | 官方把「思考预算」当一等能力，说明正确做法是**限流**而非一刀切 |
| R-3 | [Qwen 快速开始](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html)（T2） | `enable_thinking=False` 是 **hard switch**：「严格禁用思考行为，使其功能与 Qwen2.5-Instruct 对齐」 | 关闭 = 退回**非推理模型**行为，复杂算法设计能力下降 |
| R-4 | [vLLM Reasoning Outputs](https://docs.vllm.ai/en/stable/features/reasoning_outputs/)（T2） | Qwen3/DeepSeek/Nemotron3 支持 `thinking_token_budget`；达到预算即强制结束思考并转入回答；不设则不受额外限制 | 业界标准做法是**思考预算**，不是关闭 |
| R-5 | [Do NOT Think That Much for 2+3=?](https://arxiv.org/abs/2412.21187)（T1，arXiv 2412.21187） | 简单问题上过度思考「消耗 1953% 更多 token，收益极小」；提出按难度分配预算 | 我们默认的 `xhigh` 在**机械模块**上大概率是浪费 |
| R-6 | [THOUGHT TERMINATOR](https://arxiv.org/abs/2504.13367)（T1） | 问题难度与最优 token 花费存在明确关系；多数推理模型对此校准不佳 | 应按**调用类型**分档（设计类 vs 机械类） |

**二、本地 A/B（B 站 halogen，同一 data.py 提示词，`max_tokens=8192`，n=2 轮）**

| 模式 | completion | reasoning | reasoning 占比 | 代码行 | AST | 需求命中 | 文档串 | try 块 | 耗时 |
|---|---|---|---|---|---|---|---|---|---|
| 默认（`xhigh`） | 4 068 / 8 175 | 3 097 / **6 989** | **76% / 85%** | 101 / 115 | ✅ | 5/5 | 4 | 1 | 44.7 s |
| `reasoning_effort=low` | 1 318 / 1 346 | **114 / 114** | 9% | 144 / 149 | ✅ | 5/5 | 4 | 0 | 13.2 s |
| `reasoning.max_tokens=1024/2048` | 1 902 / 3 036 | 1 049 / 2 073 | 55% / 68% | 93 / 96 | ✅ | 5/5 | 4 | 0 | 22.7 s |
| `enable_thinking=false` | 956 / 1 119 | 0 | 0% | 132 / 147 | ✅ | 5/5 | 4 | 0 | 9.3 s |

**三、结论**

1. **默认 `xhigh` 把 76–85% 的输出预算花在思考上**——这直接解释了 `data.py` 为何在 32768 触顶：代码正文实际只拿到约 5–7k。**根因不是「代码写不下」，而是「思考挤占了代码」。**
2. **代理指标上四种模式没有可见质量差异**（语法、5/5 需求名、4 个 docstring、0 lazy 标记）；默认模式在首轮多写了 1 个 `try` 块。但这是 **n=1 的语法级代理**，不等于语义正确性，不能据此宣称「关闭无损失」。
3. **文献一致指向「限流」而非「关闭」**：关闭是硬开关、等于退回非推理模型（R-3），而学术代码里恰恰有需要推理的部分（τ-KL / Fréchet 的算法设计）；同时机械模块确实存在过度思考（R-5/R-6）。
4. **在「预算充足」前提下，最优解不是二选一**：保持 thinking，但**按调用类型分档**，并把单模块预算上限提到 65536 兜底。

**四、建议策略（写入 §F-7b.8 的 Phase 1）**

| 调用类型 | 建议 | 理由 |
|---|---|---|
| 蓝图 / 实验对齐 / 方法设计 | `reasoning_effort` 保持默认或 `medium` | 需要设计推理，R-1/R-2 |
| 核心算法模块（`methods.py`、模型定义） | 保持 thinking + 预算 65536 | 算法正确性优先，代码正文需要足够空间 |
| 机械模块（`config.py`、`schema.py`、`io` 层） | `reasoning_effort=low` 或 `reasoning.max_tokens≈2048` | R-5/R-6：低难度过度思考是纯浪费 |
| 极端兜底 | `enable_thinking=false` 仅在单模块连续两次超预算时启用 | R-3：硬开关有质量风险，只作最后手段 |

**五、诚实边界**

- 质量代理只有语法与符号覆盖，**没有**跑单测、没有跑对齐门与证据门；真正裁决者仍是 Stage 10 出口门。
- 每格 n=2（两轮同 prompt），不足以给出统计结论；建议在 B-34 M4 落地时把「同 prompt 四模式 × 5 轮」作为固定 A/B。
- 模型是 `halogen-qwen3.8-flash-next`（供应商定制卡），R-1..R-4 的结论来自 Qwen3 官方与 vLLM，**不能直接外推到该定制版本**；只能作为方向。

#### F-7b.11 蓝图 / 对齐 / 方法设计的外部工具与技能缺口（B-35 立项依据）

> 问题：这三步是否配置了 MCP 或 skill 工具？结论：**都没有**，只有静态文本注入；三类外部能力中一类未生效、一类未接通、一类方向相反。

| 步骤 | 现有输入 | 工具 / MCP | 缺口 |
|---|---|---|---|
| 蓝图规划（[`_phase1_blueprint`](../../researchclaw/pipeline/code_agent.py#L383-L451)） | topic、`exp_plan`、metric + [`_build_domain_context`](../../researchclaw/pipeline/code_agent.py#L574-L610) 注入的域 profile 与 code search 结果 | 无 skill、无 MCP、无工具循环 | 见下 ①②③ |
| 实验对齐门（[_code_generation.py L1784-1810](../../researchclaw/pipeline/stage_impls/_code_generation.py#L1784-L1810)） | 文件清单 + main.py 全文（≤12k 字符）+ 其他文件签名摘要 | 无 | 纯 LLM 判词（`max_tokens=1024`），无 AST 符号表等确定性证据 |
| 方法设计 | 内嵌在蓝图 prompt | 无 | 无独立步骤、无实验设计 skill、无文献支撑 |

**缺口一：唯一的外部检索在 B 站返回 0 条**

运行 F 日志：

```text
Code search started for: ... (domain=generic)
GitHub API error 401: https://api.github.com/search/code?q=...
Code search complete: 0 repos, 0 snippets, 0 patterns, 4 API calls
```

B 站 `env | grep -i github` 为空、`config.g7-field.yaml` 无 `code_search` 键 → [`GitHubClient`](../../researchclaw/agents/code_searcher/github_client.py#L65-L70) 以匿名身份调用，被限流/鉴权拒绝，蓝图实际拿到 0 条参考代码。

**缺口二：skills 存在且标注适用 Stage 10，但从未进入 CodeAgent**

- 内置 20+ skills（[`researchclaw/skills/builtin/`](../../researchclaw/skills/builtin)），如 [`data-loading/SKILL.md`](../../researchclaw/skills/builtin/tooling/data-loading/SKILL.md) 含 `applicable-stages: "10"`
- 映射表中 `code_generation → 10`（[schema.py L21](../../researchclaw/skills/schema.py#L21)）
- 但 `_get_evolution_overlay(..., "code_generation")` **只在旧单发路径**调用（[_code_generation.py L1195](../../researchclaw/pipeline/stage_impls/_code_generation.py#L1195)）；CodeAgent 构造签名（[L230-254](../../researchclaw/pipeline/code_agent.py#L230-L254)）无 skills 参数，`_phase1_blueprint` 也不读 overlay

**缺口三：MCP 方向相反，且无 tool-calling 循环**

[`mcp/server.py`](../../researchclaw/mcp/server.py) 暴露 6 个工具（`run_pipeline`、`search_literature`、`review_paper` 等）供**外部调用 ARC**；`mcp/client.py` / `registry.py` 存在但管线未引用。`LLMClient.chat` 只构造 `model/messages/temperature/max_tokens`，没有 `tools=` 参数。

**立项建议（B-35，本批只登记）**：

| 级别 | 动作 | 改动面 | 验收 |
|---|---|---|---|
| P0 零代码 | B 站配置只读 `GITHUB_TOKEN` | 环境变量 | `Code search complete: N repos`，N>0 |
| P1 | skills overlay 接入 CodeAgent（蓝图 + 单文件 prompt） | 2 文件 ~30 行 | 命中 `data-loading` 的 topic 断言 prompt 含 skill 正文 |
| P1 | 对齐门增加确定性证据（AST 符号表 + 蓝图文件清单） | 1 函数 | 缺文件产物在 LLM 判词前即失败 |
| P2 | Stage 4–6 文献/知识摘要注入蓝图；或经 `MCPServerRegistry` 调 `search_literature` | 中等 | 蓝图 prompt 含 N 条可追溯文献 |
| P3 | CodeAgent 内 tool-calling 循环（sandbox / 检索） | 大 | 独立批次设计 |

**纪律**：每增加一个输入源，必须同时给出可测量验收（检索命中数、skill 命中率、对齐门纠正次数），否则只是 prompt 膨胀（与 §F-7b.8「先探针再改」同一原则）。

### F-8 阶段重试从零重跑（已修：B-33 M1，运行 F 已验）

- **现象**：09:45 失败后，`agent_runs/attempt_001` 被**重新创建**（此前已有 001–004），`code_agent_log.json` 仍是 08:25 旧版 → 第 2 次重试从 Phase 1 重新开始。
- **机制**：`checkpoint.json` 只在 stage DONE 后写，Stage 10 内部无任何可恢复状态；`_call_with_retries`（`executor.py` L613-629）最多 3 次，每次都是完整重跑。
- **代价**：单次重试约 70 分钟 / 17–20 次调用，全部丢弃重来。运行 E 的三次内部重试合计约 4 h 22 m，其中可复用部分为零。
- **状态**：**B-33 M1 已由 P-193 实现，随 `dc5f80b` 部署，运行 F 已验**——`checkpoint.json` 出现 `in_progress_stage=10`（`last_completed_stage` 仍 11），`stage-10/steps.jsonl` 首次落盘（`blueprint/done`、`generate_file/data.py/failed`）。运行 E 现场无 `steps.jsonl`，故当时断点收益为零。L2（生成路径实际跳过）与 L3（LLM 响应缓存）仍未做。

### F-9 可观测性盲区（已修：B-31a，运行 F 已验）

- **现象**：运行 E 前 2 h 44 m，`/tmp/p192_stage12.log` 只有 **22 行 / 6 656 B**；`heartbeat.json` 停留在 2026-11-25T14:14:37Z；`events.jsonl` 只有 `stage.started`。运行 E 全程结束时日志 12 153 B / 4 h 22 m。
- **机制**：① `_write_heartbeat` 仅在 DONE 后调用；② 无 `logging.basicConfig`，`logger.info` 全丢；③ `print` 在重定向下块缓冲；④ `llm.call/llm.result` 有声明无生产者；⑤ dashboard/`ops` 不读 lease 与 `steps.jsonl`。
- **后果**：08:43–09:45 这 62 分钟（对齐重生成 + 消融修复）在现场完全不可见，只能靠 `cost_log.jsonl` 的调用节奏反推。
- **运行 E 终态的直接实证**：日志文件的**行序**证明块缓冲——所有 `logger.warning`（stderr，无缓冲）写在前面，`print` 的 `ResearchClaw v0.5.0 — Starting pipeline` 与 `Stage 10/23 ... running...` 却出现在文件**末尾**，即进程退出时才 flush。
- **状态**：**B-31a 已修复并随 `dc5f80b` 部署，运行 F 已验**。P-195 加 `run --log-level/--log-file` + `basicConfig(force=True)` + 行缓冲 + 阶段横幅入日志；P-198 补录真实红→绿。运行 F 的 `~/arc-runs/p207-stage10.log` 全程可读 INFO（蓝图截断、模块生成、失败原因），不再只有 WARNING。B-31b（心跳 details + `STALLED`）仍未做。

---

## 4. 修复决策回溯

| 批次 | 编号 | 触发故障 | 核心改动 | 交付 | B 站现场验证 |
|---|---|---|---|---|---|
| P-178 | — | F-1 / F-2 | 围栏容错、截断重试 32768、评审守卫、出口门（AST 检查 `__main__` + `METRIC_DEF`） | `spec/arc-stage10-codegen-truncation/` | 运行 B/C 的失败证明门在检查；运行 E 未再出现「无守卫入口」 |
| P-190 | B-28 | F-3 | repair 合并而非替换、AST 过滤、截断重试 | `spec/arc-stage10-repair-merge/` | 运行 E 08:35 `repair: response truncated — retrying with 32768` |
| P-191 | B-29 | F-4 | 删除文件提升；`entrypoint_contract.py`；专用入口生成；repair 拒绝不合契约 main.py | `spec/arc-stage10-entrypoint-contract/` | 运行 E 08:25 `entrypoint contract unmet ... generating main.py` |
| P-192 | B-30 | F-5 | 预算 32768→65536；提示 ≤150 行 + 禁止重写；`synthesize_entrypoint`（`nan` 兜底）；repair 2 次止损 | `spec/arc-stage10-entrypoint-budget/` | 运行 E 入口一次成功，未升级 65536，未再出现「repair 空转 4 次」 |
| P-193 | B-33 M1 | F-8 | `in_progress_stage`（含事件重建回填）；蓝图 Phase 1 后即落盘；`step_journal`（append-only / 摘要 / 复合键 / `should_skip`） | `spec/arc-stage10-intra-stage-checkpoint/` | 已部署（`dc5f80b`）；运行 F：`checkpoint.in_progress_stage=10`、`steps.jsonl` 落盘 |
| P-194 | B-32 M1 | F-6 | 折叠「行尾冒号 + 缩进续行」；一次窄提示 YAML 重试；回退写 `codegen_decision.json` + `logger.warning` | `spec/arc-stage10-blueprint-yaml-robust/` | 已部署（`dc5f80b`）；运行 F：蓝图 19 943 字符一次解析成功 |
| P-195 / P-198 | B-31a | F-9 | `run --log-level/--log-file`；`basicConfig(force=True)`；行缓冲；阶段横幅入日志；补真实 TDD 红→绿 | `spec/arc-runtime-log-visibility/` | 已部署（`dc5f80b`）；运行 F：`p207-stage10.log` 全程 INFO 可读 |
| P-197 | B-32 M2 | F-6 后果 | 四项证据门（文件集合 / 指标一致 / 数据源 WARN / 非配置计算）+ 折叠 mapping 保护 | 同上（v1.1） | 已部署（`dc5f80b`）；运行 F 未触达（生成阶段失败） |
| P-202 | B-32 M3 | F-6 + P-200 复审 | 指标名 AST 优先；数据源递归取叶子；折叠双守卫；无围栏 `files:` 对齐；门读磁盘 `experiment/` | 同上（v2.0） | 已部署（`dc5f80b`）；运行 F 未触达（生成阶段失败） |
| P-207 | B-34 | F-7b + P-204 F-1..F-6 | M1-a 单文件提取器补 `_close_unterminated_fence`；M1-b 升级后仍截断/空 → `steps.jsonl(failed)` + `ModuleExtractionError`；F-1/F-5 剔除注释；F-2 `*Config` 行为判据；F-3 指标名保留括号；F-4 `bool` 显式；F-6 版本回落 DEBUG | [spec/arc-stage10-module-extraction-fallback/](../spec/arc-stage10-module-extraction-fallback/) | **已部署（`dc5f80b`）**；运行 F 于 1 489.86 s 在 `data.py` 显式失败并留账 |

> 提交：`6274eb2`（P-190/P-191）、`afd0dd5`（P-192/P-193）、`9ac80b3`（边界写点登记）、`8744c84`（P-194..P-199）、`1d7853a`（P-200..P-202）、`0bec5e7` + `dc5f80b`（P-203..P-207，PR [#57](https://github.com/StormstoutLau/AutoResearchClaw/pull/57)）；PR [#55](https://github.com/StormstoutLau/AutoResearchClaw/pull/55)、[#56](https://github.com/StormstoutLau/AutoResearchClaw/pull/56)、[#57](https://github.com/StormstoutLau/AutoResearchClaw/pull/57) CI 各 8/8；`main` = `dc5f80b`。
> **一句话**：P-178..P-192 与本次部署的 P-193..P-207 都已在现场验证；区别是前者证明了「门在检查」，后者证明了「失败提前到模块边界」。B-32 M2 出口门仍待一次四模块齐全的重跑。

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
| 1 | ~~P-193..P-207 全部未部署~~ → **已于 2026-11-26 部署 `dc5f80b`** | 部署前 B 站跑 P-192 之前代码；部署后首轮运行 F 已验（§2.4） | 保持 `dc5f80b`；后续修复按新批次部署 |
| 2 | **`data.py` 单模块超出 32768（运行 F 新证据，§F-7b.7；处置见 §F-7b.8 / §F-7b.9 / §F-7b.10）** | 升级后 `completion_tokens=32768` 打满仍截断；M1-a/M1-b 只能让它快速失败，不能让它成功 | **根因已定位**：默认 `xhigh` 把 76–85% 预算花在思考上（§F-7b.10），代码正文只剩 3–7k；cap=65536（服务策略）也已证。**下一步**：E'（思考预算分档：设计类保留、机械类 `low`/`max_tokens≈2048`、硬关闭作最后手段）→ C+（文件预算 + 符号契约）→ C++（函数级，默认关）→ A'（按文件 65536 兜底） |
| 3 | 对齐门只有否决、无「合格线」 | 判词正确但不可执行，连否 3 次 ×2 轮 | 建议在 regen 提示中附带蓝图 `files`/`classes` 清单作为最低实现要求 |
| 4 | 阶段重试 3 次上限 | 3 次全失败后 Stage 10 直接失败，管线停在 12 之前 | 与 B-8（退出码分类）一起评估「降级 + 标注」而非硬失败 |
| 5 | B-31b 未做（心跳 + `STALLED`） | 部署 B-31a 后日志可见，但仍无「活着但停滞」判定 | 与 B-33 M2 同批 |
| 6 | 证据门**仍未在真实产出上触达** | 运行 F 在生成阶段失败，`codegen_evidence.json` 未生成 | 待一次四模块齐全的重跑（取决于 §5#2 的裁决） |
| 7 | 运行期无 `heartbeat` / 运行中的 `stage_health` 更新 | 无法判断「活着但停滞」；运行 F 的 `stage_health.json` 只在失败后写出 | 部署 B-31a 后日志可见（已验），但要判定停滞仍需 B-31b |

---

## 6. 成本统计

| 项 | 值 |
|---|---|
| Stage 10 累计墙钟（A–E） | 1 491 + 13 007 + 14 564 + 约 9 400（D 被杀）+ **15 770（E）** ≈ **12.7 h** |
| 运行 E 单轮 | 15 769.77 s，**91 次 LLM 调用**，3 次内部重试 |
| 运行 F 单轮（部署后） | **1 489.86 s**；蓝图 2 次调用（8192→32768）、`config.py` 2 次（8192→32768）、`data.py` 2 次（8192→32768）；`data.py` 的 32768 输出打满 |
| 单次 CodeAgent 典型耗时 | 3 471 s（58 min），17 次 LLM，4 次沙箱，2 轮 review |
| 生成链内部日志 | `code_agent_log.json` 中 `truncated` 命中 **5 次**，全部为**首轮 8192** 的 `finish_reason=length`（蓝图 1 + `config.py`/`data.py`/`models.py`/`methods.py` 各 1）；运行 E 的代码无二次检查，故当时 32768 状态不可观测；**部署后（运行 F）可观测：`data.py` 的 32768 `completion_tokens` 打满** |
| 实际交付体量 | `methods.py` 448 行/15.8 KB、`config.py` 343 行/12.5 KB、`models.py` 217 行/6.9 KB ≈ **2–4.5 k tokens**，均远低于 8192 ⇒ 首轮截断不能归因于"模块太大"；**该表不含 `data.py`（运行 E 缺失），运行 F 已证其 32768 打满，故结论只对已交付三模块成立** |
| 截断率 | 运行 E 前段 245 次调用中 **84 次（34%）** `completion_tokens=16384` 打满 |
| 失败重试浪费 | 每次 stage 重试丢弃前一整轮（约 17–20 次调用、约 70 min）；E 的三次重试各被对齐门否决 |
| 观测成本 | 运行 E 全程 4 h 22 m 仅产出 **12 153 B** 日志；`heartbeat` 滞后 19 h |
| 未被结构门捕获的漂移 | `data.py` 缺失 / 指标全缺 / `main.py` 截断 —— 若 B-32 M2 已部署，本可在**秒级**判定 |

---

## 7. 教训与流程建议

1. **修一个暴露下一个是正常的，但要按「生成链」顺序修**。B-28/29/30 都是「有产物之后」的修复，而 F-6 让产物路径根本不成立——**应先修前置（B-32），再修后置**。
2. **成功判据比错误处理更危险**。运行 A 的 `exit_code=0` 比任何崩溃都糟：它让 25 分钟的穷产物被当作成功。任何「能跑即通过」的判据都应配结构/语义门。
3. **本地门禁与 CI 门禁的判定模式不同**。P-179..P-189 在本地提交时走 `session-progress` 模式（通过），CI 对 PR 区间走 `batch` 模式（红）。这类差异应在本地预演（本次已用 `step_enforce --base origin/main <changed>` 补齐）。
4. **未部署的修复等于没修**。B-31/B-32/B-33 都已实现并合入 `main`，但 B 站跑的是旧代码，因此同一故障会持续复现。**部署本身应作为批次的一部分登记**，而不是一个可选的后续动作。（2026-11-26 已部署 `dc5f80b`；本条作为流程要求保留。）
5. **现场必须留「进行时」痕迹**。本次定位 08:43–09:45 的 62 分钟空白，只能靠 `cost_log.jsonl` 的行数与时间戳反推，成本极高。
6. **「判定」与「修复」必须分层**。运行 E 证明：结构门（B-32 M2）能秒级判定 `data.py` 缺失，但不能让模型把 `data.py` 生成出来。把二者混在一个批次里，会让门看起来"没用"——其实它只是**下游**。
7. **日志的行序本身就是证据**。运行 E 的日志里 `print` 横幅全部落后于 `logger.warning`，这一现象单独就证实了块缓冲；无需另做实验。排查时应优先看"顺序异常"而非只看"内容缺失"。
8. **失败判词要可执行**。对齐门的三段判词在科学上正确，但对生成侧没有可操作指令；这类"只否决不指路"的门应附最低实现清单（蓝图 `files`/`classes`）。
9. **归因要看"实测体积"，不要看"应然体积"**。F-7b 初版把「四模块 32768 打满」当事实写入，实际 5 条 `truncated` 全是**首轮 8192**，交付模块只用了限额的 1/3～1/8。用"模块应当很大"代替实测，会把「提取器缺兜底」误诊为「模型容量不足」，从而给出错误处方（加预算而非补兜底）。
10. **同一修法要检查是否覆盖所有分支**。P-178 的 `_close_unterminated_fence` 只补在单发路径的两个提取器上，顺序生成的 `_extract_single_file_code` 一行未补——这就是 `data.py` 消失的直接原因。修一个缺陷时应枚举所有调用点。
11. **归因表的样本集合必须与结论的作用域一致**。P-205 用「实际交付 2–4.5k tokens」撤销「模块超容量」，但那张表只统计了**已交付**文件，`data.py` 因缺失从未被测到；运行 F 才直接测到它 32768 打满。**用「其余模块很小」推断「这个模块也不大」是样本选择偏差**，订正时必须先核对「结论覆盖的每一个对象是否都有读数」。
12. **「仍然失败」不等于「修复无效」**。运行 F 的 Stage 10 依然 FAILED，但失败点从 4 h 22 m 后的对齐门提前到 24 m 50 s 的模块边界，并留下结构化账本；同时 B-33 L0、B-31a 都获得了现场正证。评价一个失败批次的收益，要看**失败的位置、成本与可观测性**，而不只看终态。

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

# ---- 运行 F：部署 dc5f80b 后的 Stage 10 单阶段验证（2026-11-26 21:27–21:52 CST）----

# 1) 部署证据：导入与符号
~/arc-venv/bin/python -c "import researchclaw.pipeline.codegen_evidence, researchclaw.pipeline.step_journal, researchclaw.runtime.logging_setup; print('IMPORT_OK')"
grep -c 'class ModuleExtractionError' ~/AutoResearchClaw-main/researchclaw/pipeline/code_agent.py
grep -c '_close_unterminated_fence' ~/AutoResearchClaw-main/researchclaw/pipeline/code_agent.py

# 2) 终态：1 489.86 s / failed / 模块级错误
cat ~/arc-runs/g7-baseline/stage-10/stage_health.json
cat ~/arc-runs/g7-baseline/stage-10/decision.json

# 3) 账本：blueprint/done + generate_file/data.py/failed
cat ~/arc-runs/g7-baseline/stage-10/steps.jsonl

# 4) 截断与预算：data.py 的 32768 打满
grep -E 'truncated|module generation failed|FAILED' ~/arc-runs/p207-stage10.log
tail -4 ~/arc-runs/g7-baseline/cost_log.jsonl

# 5) 失败早于出口门：无 experiment/、无 codegen_evidence.json
ls ~/arc-runs/g7-baseline/stage-10/
ls ~/arc-runs/g7-baseline/stage-10/codegen_evidence.json

# 6) B-33 L0：in_progress_stage=10 且 last_completed=11
cat ~/arc-runs/g7-baseline/checkpoint.json

# 7) 回退点
ls -d ~/arc-runs/g7-baseline/stage-10.bak-p207 ~/AutoResearchClaw-main.prev-20261126

# ---- Phase 0：引擎输出上限探针（2026-11-26 执行，结论见 §F-7b.9）----

# 1) 模型卡与运行时上限
curl -s http://127.0.0.1:8080/v1/models | head -c 800
curl -s http://127.0.0.1:8080/props | head -c 400

# 2) 服务启动参数（cap / context）
ps -ef | grep '[s]erve_api.py'
docker ps --format '{{.Names}} | {{.Image}} | {{.Ports}}' | grep -i halogen

# 3) 超限即被拒（应返回 cap 65536 的 400）
curl -s http://127.0.0.1:8080/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"halogen-qwen3.8-flash-next","messages":[{"role":"user","content":"Reply OK"}],"max_tokens":70000}'

# 4) 思考预算开关（默认 vs enable_thinking=false，看 reasoning_tokens）
curl -s http://127.0.0.1:8080/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"halogen-qwen3.8-flash-next","messages":[{"role":"user","content":"In one sentence: what is a sentinel?"}],"max_tokens":512,"temperature":0}' \
  | python3 -c 'import json,sys;u=json.load(sys.stdin)["usage"];print(u["completion_tokens"],u["completion_tokens_details"]["reasoning_tokens"])'
curl -s http://127.0.0.1:8080/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"halogen-qwen3.8-flash-next","messages":[{"role":"user","content":"In one sentence: what is a sentinel?"}],"max_tokens":512,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}' \
  | python3 -c 'import json,sys;u=json.load(sys.stdin)["usage"];print(u["completion_tokens"],u["completion_tokens_details"]["reasoning_tokens"])'

# 5) 代码任务四模式 A/B（§F-7b.10）：同一 data.py 提示词，比较 completion/reasoning/行数/AST
#    modes: {} | {"reasoning_effort":"low"} | {"reasoning":{"max_tokens":2048}} | {"chat_template_kwargs":{"enable_thinking":false}}
```

### B. 证据文件清单

| 文件 | 用途 |
|---|---|
| `attempts/stage-10/attempt-{1,2,3,4}.json` | 四次阶段结果、退出码、resume_note、产物快照（**attempt-4 为运行 E 终态；attempt-5 为运行 F**） |
| `stage-10/stage_health.json` | 运行 E 终态：`duration_sec=15769.77`、`status=failed`、错误原文 |
| `stage-10/code_agent_log.json` | CodeAgent 逐阶段日志（蓝图截断、YAML 错误、回退、硬校验、exec-fix；运行 E 中 `truncated` ×5） |
| `stage-10/architecture_spec.yaml` | 蓝图原文（运行 E：36 907 B / 36 831 字符，**解析成功**；上一轮：57 957 B，失败行 1055–1056） |
| `stage-10/agent_runs/attempt_00N/` | 每次沙箱执行的完整文件集 |
| `stage-10/experiment/` | 最终交付（运行 E：config/methods/models/synthetic_finance/main/utils 六文件；`data.py` 缺失） |
| `stage-10/ablation_warning.json` | 消融条件重复判词 |
| `stage-10/decision.json` | 阶段判决（`status=failed`、`next_stage=10`） |
| `stage-10/experiment_spec.md` | 阶段规格与对齐状态 |
| `cost_log.jsonl` | 调用节奏与截断率（运行 E：91 次） |
| `events.jsonl` / `checkpoint.json` / `lease.json` | 阶段边界与存活信号（运行 E：seq 82 `run.failed`、`lease.released=true`；运行 F：`checkpoint.in_progress_stage=10`） |
| `stage-10/steps.jsonl` | 运行 F 首次出现：`blueprint/retry/done`、`generate_file/data.py/failed` |
| `~/arc-runs/p207-stage10.log`、`p207-stage10.stdout` | 运行 F 的 INFO 级全量日志（B-31a 部署后） |
| `stage-10.bak-p207`、`AutoResearchClaw-main.prev-20261126` | 运行 F 前的现场 Stage 10 与旧代码，回退点 |
| `/tmp/p191_stage12.log`、`/tmp/p192_stage12.log` | WARNING 级现场日志（运行 E：12 153 B；**行序证明 `print` 块缓冲**） |

### C. 相关文档与提交

- 修复规格：[P-178](../spec/arc-stage10-codegen-truncation/)、[B-28](../spec/arc-stage10-repair-merge/)、[B-29](../spec/arc-stage10-entrypoint-contract/)、[B-30](../spec/arc-stage10-entrypoint-budget/)、[B-31a](../spec/arc-runtime-log-visibility/)、[B-32 v2.0](../spec/arc-stage10-blueprint-yaml-robust/)、[B-33](../spec/arc-stage10-intra-stage-checkpoint/)、[B-34](../spec/arc-stage10-module-extraction-fallback/)
- 立项调研：[B-31](arc-longrun-progress-observability-20261126.md)、[B-32](arc-stage10-blueprint-fallback-20261126.md)、[B-33](arc-stage10-intra-stage-checkpoint-20261126.md)
- 异构复审：[B-31 复审](arc-longrun-progress-review-20261126.md)、[B-33 复审](arc-stage10-checkpoint-review-20261126.md)、[P-194..P-199 复审](arc-p194-p199-heterogeneous-review-20261126.md)、[P-203 postmortem 复审](arc-p203-postmortem-review-20261126.md)
- 总纲：[arc-master-roadmap.md](../arc-master-roadmap.md) §3.2（B-28..B-34）
- 提交：`6274eb2`、`afd0dd5`、`9ac80b3`、`8744c84`、`1d7853a`、`0bec5e7`、`dc5f80b`；PR [#55](https://github.com/StormstoutLau/AutoResearchClaw/pull/55)、[#56](https://github.com/StormstoutLau/AutoResearchClaw/pull/56)、[#57](https://github.com/StormstoutLau/AutoResearchClaw/pull/57)；`main` = `dc5f80b`（已部署 B 站）

### D. 与本文其余文档的关系

| 文档 | 关系 |
|---|---|
| `docs/arc-stage10-blueprint-fallback-20261126.md`（B-32 调研） | F-6 的方案来源；本文 §F-6 的「运行 E 反证」为其增加一条边界（YAML 缺陷可自发消失，不能只靠它解释失败） |
| `docs/arc-p194-p199-heterogeneous-review-20261126.md` | B-32/B-31a 合入内容的复审；本次运行 E 的产物对账为它提供第一个**真实产出形态**的样本 |
| `spec/arc-stage10-blueprint-yaml-robust/`（DESIGN v2.0） | §5.1 五项边界的关闭记录；本文 §2.3 反事实所用的门即该批交付 |
| `spec/arc-stage10-module-extraction-fallback/`（P-207） | §F-7b.1/F-7b.2 的实现规格与红→绿记录；本文 §2.4 的运行 F 即该批部署后的首验 |
| `docs/arc-longrun-progress-observability-20261126.md`（B-31 调研） | F-9 的方案来源；本文 §2.3「日志行序」为其根因提供现场实证 |
