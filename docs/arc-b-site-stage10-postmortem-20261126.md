# B 站 Stage 10 排查、修复与故障分析完整记录（2026-11-26）

> **性质**：Layer-0 事后分析（postmortem），零代码 / 零门禁变更。本文只做取证、归因与决策回溯，不新增实施承诺。
> **范围**：B 站（`scott-lau-GTR-Pro.local`）run 目录 `~/arc-runs/g7-baseline`，topic 为「LNN 内部动力学信号的分层漂移监测：τ-KL 粗筛与 Fréchet 伴随状态变点检测的金融时序比较研究」，Stage 10（CODE_GENERATION）自 2026-11-25 13:48Z 起的全部尝试。
> **证据来源**：`attempts/stage-10/attempt-{1,2,3}.json`、`stage-10/code_agent_log.json`、`stage-10/architecture_spec.yaml`、`stage-10/agent_runs/`、`stage-10/experiment/`、`stage-10/ablation_warning.json`、`stage-10/experiment_spec.md`、`cost_log.jsonl`、`events.jsonl`、`checkpoint.json`、`lease.json`、`/tmp/p19{1,2}_stage12.log`。
> **方法**：读码锚点 + 远端文件采样 + 本地测试复跑。未做受控实验，未改动远端任何源码。
> **边界**：① 单一 run、单一 topic；② 时间戳统一 UTC，括号内为 B 站本地时间（UTC+8）；③ attempt 编号为跨 run 全局计数，不等同于「某一次 stage 重试」；④ 本文不评价 topic 本身的科学价值。

---

## 0. 结论摘要

1. **Stage 10 在 24 小时内失败 4 次，根因是 5 个不同缺陷的串联**，不是单一 bug：出口门缺失 → 截断/围栏 → repair 整体替换 → 文件提升 → 入口生成无兜底 → 蓝图 YAML 失效导致单发退化。
2. **每修一个，下一个才暴露**。P-178、P-190、P-191、P-192 四次修复各自在 B 站现场被日志证实生效，但 Stage 10 仍未通过。
3. **当前阻塞点已从「入口不可执行」转移到「实验内容不成立」**：新增的「主题-实验对齐门」判定产物只实现了配置与代理算法，未实现 LNP/τ-KL/伴随状态，因而主动判失败。**这是护栏在正确工作，不是护栏误报。**
4. **剩余结构性缺口有两个，都已立项但未部署到 B 站**：B-32（蓝图 YAML 失效 → 单发回退）与 B-33（阶段内无断点，重试从零重跑）。B-31（长跑可观测）同样未部署，现场 2 小时 44 分钟只有 22 行日志。
5. **成本已经可量化**：4 次失败累计 Stage 10 墙钟约 **8.3 小时**（13007 s + 14564 s + 约 2.6 h 被杀 + 当前进行中），LLM 调用以约 1 次/3.7 分钟稳定消耗，245 次采样中 84 次（34%）打满 16384 token 上限。

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

### 2.1 五次运行 / 四次失败

| # | 时窗（UTC） | 时长 | 结果 | 关键错误 | 触发修复 |
|---|---|---|---|---|---|
| A | 11-25 13:48:50 → 14:13:41 | 1 491 s（25 min） | `exit_code=0` | 无（但产出仅 `experiment/` 2 文件、`architecture_spec.yaml` 4 478 B） | P-178（出口门缺失，穷产物被放行） |
| B | 11-25 14:42:25 → 18:19:12 | **13 007 s（3 h 37 m）** | `exit_code=75` | `main.py has a syntax error: unterminated string literal (line 130)` | **P-190 / B-28** |
| C | 11-25 21:33:16 → 11-26 01:36:00 | **14 564 s（4 h 3 m）** | `exit_code=75` | `main.py missing if __name__ == "__main__"; never prints METRIC_DEF` | **P-191 / B-29** |
| D | 11-26 04:51 → 07:27（人工终止） | 约 2 h 36 m | 未记录 attempt（阶段未结束） | `entrypoint attempt 1/2 truncated` ×2，越界第 517 行；`dedicated entrypoint generation failed`；`Repair attempt returned invalid Python for data.py` ×4 | **P-192 / B-30** |
| E | 11-26 07:27:49 → 进行中 | 已 2 h 44 m | Stage 10 **失败 1 次**，第 2/3 次重试中 | 对齐门判 MISALIGNED → 2 次重生成仍不合格 → `Persistent topic-experiment misalignment` | **B-32 / B-33**（已立项，未部署） |

> A 的 `exit_code=0` 是「没有出口门」的直接后果：只有 2 个文件、蓝图 4.5 KB 的产物被判通过，说明当时的成功判据只看「能跑」。

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

### F-6 蓝图 YAML 失效 → 顺序生成被跳过 → 单发退化（未修：B-32）

- **现象**：运行 E 蓝图 57 948 字符，两次解析均失败：

  ```
  Blueprint YAML parse error: while scanning a simple key ... line 1055:
      HiddenStateTauKLMonitor override ...
  could not find expected ':'  (line 1056)
  Sequential generation requested but blueprint invalid — falling back to single-shot
  ```

- **机制**：`_parse_blueprint` 的预处理把 key 分隔符定为 `":\s"`（冒号 + 空白），不覆盖「值以冒号结尾 + 下一行续写」的形态；解析失败后 `blueprint=None`，`_is_valid_blueprint` 不满足 → 走单发。
- **后果**：单发只生成 `config.py` + 配置校验型 `main.py`。蓝图声明 5 个文件 / 6 个 `class:` / 32 处 `Monitor`，实际交付 0 个 monitor 类。B-29/B-30 所在的**顺序路径根本没有执行**。
- **证据**：`architecture_spec.yaml` 第 1055–1056 行；`code_agent_log.json` 第 4、5 行；`experiment/` 仅 3 个文件。
- **状态**：已立项 **B-32**（`docs/arc-stage10-blueprint-fallback-20261126.md`），未实施。

### F-7 主题-实验对齐门（既有护栏，运行 E 首次真实触发）

- **机制**：`_code_generation.py` L1780-1910 先让模型自评「代码是否真的检验了 topic」，不合格则最多重生成 2 次并复检；仍不合格则 FAILED（L2020）。
- **运行 E 判词（节选，属正确判断）**：

  > main.py 只做合成 AR 式隐状态模拟，没有实例化或训练 LNN；τ-KL 不是对 LNN 内部动力学的粗筛，而是对差分序列的高斯均值/方差 KL；Fréchet 是对窗口累积偏差的离散距离，不是伴随状态变点检测；没有分层漂移架构，没有金融时序数据管线。

  以及消融判词：12 个条件只是 `DRIFT_TYPES × DRIFT_SPEEDS × NOISE_LEVELS` 的标签组合，无参数差异、无代码分支、无消融开关。

- **评价**：**这是护栏按设计工作**。它把「假实验」挡在 Stage 12 之外，代价是 Stage 10 显式失败而不是静默带着穷产物继续。
- **问题**：护栏只负责否决，不提供「怎么改才合格」的有效路径——在 F-6 未修的前提下，重生成仍在单发模式下打转。

### F-8 阶段重试从零重跑（未修：B-33）

- **现象**：09:45 失败后，`agent_runs/attempt_001` 被**重新创建**（此前已有 001–004），`code_agent_log.json` 仍是 08:25 旧版 → 第 2 次重试从 Phase 1 重新开始。
- **机制**：`checkpoint.json` 只在 stage DONE 后写，Stage 10 内部无任何可恢复状态；`_call_with_retries`（`executor.py` L613-629）最多 3 次，每次都是完整重跑。
- **代价**：单次重试约 70 分钟 / 17–20 次调用，全部丢弃重来。
- **状态**：已立项 **B-33** 并由 **P-193** 在本地实现 M1（`in_progress_stage` + 蓝图尽早落盘 + `steps.jsonl`），**尚未部署到 B 站**。

### F-9 可观测性盲区（未修：B-31）

- **现象**：运行 E 已 2 h 44 m，`/tmp/p192_stage12.log` 只有 **22 行 / 6 656 B**；`heartbeat.json` 停留在 2026-11-25T14:14:37Z；`events.jsonl` 只有 `stage.started`。
- **机制**：① `_write_heartbeat` 仅在 DONE 后调用；② 无 `logging.basicConfig`，`logger.info` 全丢；③ `print` 在重定向下块缓冲；④ `llm.call/llm.result` 有声明无生产者；⑤ dashboard/`ops` 不读 lease 与 `steps.jsonl`。
- **后果**：08:43–09:45 这 62 分钟（对齐重生成 + 消融修复）在现场完全不可见，只能靠 `cost_log.jsonl` 的调用节奏反推。
- **状态**：已立项 **B-31**（`docs/arc-longrun-progress-observability-20261126.md` + 异构复审），未实施。

---

## 4. 修复决策回溯

| 批次 | 编号 | 触发故障 | 核心改动 | 交付 | B 站现场验证 |
|---|---|---|---|---|---|
| P-178 | — | F-1 / F-2 | 围栏容错、截断重试 32768、评审守卫、出口门（AST 检查 `__main__` + `METRIC_DEF`） | `spec/arc-stage10-codegen-truncation/` | 运行 B/C 的失败证明门在检查；运行 E 未再出现「无守卫入口」 |
| P-190 | B-28 | F-3 | repair 合并而非替换、AST 过滤、截断重试 | `spec/arc-stage10-repair-merge/` | 运行 E 08:35 `repair: response truncated — retrying with 32768` |
| P-191 | B-29 | F-4 | 删除文件提升；`entrypoint_contract.py`；专用入口生成；repair 拒绝不合契约 main.py | `spec/arc-stage10-entrypoint-contract/` | 运行 E 08:25 `entrypoint contract unmet ... generating main.py` |
| P-192 | B-30 | F-5 | 预算 32768→65536；提示 ≤150 行 + 禁止重写；`synthesize_entrypoint`（`nan` 兜底）；repair 2 次止损 | `spec/arc-stage10-entrypoint-budget/` | 运行 E 入口一次成功，未升级 65536，未再出现「repair 空转 4 次」 |
| P-193 | B-33 M1 | F-8 | `in_progress_stage`（含事件重建回填）；蓝图 Phase 1 后即落盘；`step_journal`（append-only / 摘要 / 复合键 / `should_skip`） | `spec/arc-stage10-intra-stage-checkpoint/` | **未部署** |
| — | B-32 | F-6 | （已立项）YAML 预处理修「行尾冒号」；结构修复重试；回退显式化；文件/指标/数据源结构门 | `docs/arc-stage10-blueprint-fallback-20261126.md` | **未实施** |
| — | B-31 | F-9 | （已立项）心跳 details（含 `step_id`）+ `STALLED` + 日志级别/缓冲 | `docs/arc-longrun-progress-observability-20261126.md` | **未实施** |

> 提交：`6274eb2`（P-190/P-191）、`afd0dd5`（P-192/P-193）、`9ac80b3`（边界写点登记）；PR [#55](https://github.com/StormstoutLau/AutoResearchClaw/pull/55)，CI 8/8。

### 4.1 关键决策与理由

| 决策 | 被拒替代 | 理由 |
|---|---|---|
| 入口契约前置到「校验前 + 出口门前」 | 只在出口门拦 | 出口门在阶段末，失败要等数小时；前置把失败成本从小时级降到分钟级 |
| 截断后**升级**预算而非同额度重试 | 32 768 重试两次 | 运行 D 两次都在同一行截断，同额度无信息增量 |
| 兜底打印 `nan` | 填 `0.0` | `0.0` 会被下游当作有效指标，污染结论（与 B-30 纪律一致） |
| repair 连续 2 次不可用即止损 | 耗满 5 个槽 | 同一失败重复 4 次无收益，纯增耗时 |
| `--resume` 让 `in_progress_stage` 优先 | 只在 CLI 侧推断 | 事件推断无法区分「已完成」与「已开始未完成」 |
| 蓝图在 Phase 1 后立即落盘 | 阶段末统一落盘 | Phase 1 后崩溃是最贵窗口（生成前），否则断点无产物可校验 |

---

## 5. 仍未解决

| # | 项 | 影响 | 处置 |
|---|---|---|---|
| 1 | **B-32 未实施** | Stage 10 会继续退化为单发 config-only；对齐门会继续否决 | 建议优先；M1 只动 YAML 预处理 + 回退显式化 |
| 2 | **B-33 未部署** | 每次 stage 重试仍从零重跑（约 70 min） | 部署 P-193 三文件即可；顺带获得蓝图即时落盘 |
| 3 | **B-31 未实施** | 现场日志 2.7 h 仅 22 行，无法定位阶段内进度 | 与 B-33 共享 `step_id`，可同批 |
| 4 | 对齐门只有否决、无「合格线」 | 重生成方向不明确，容易反复 | 建议在 regen 提示中附带蓝图 `files`/`classes` 清单作为最低实现要求（依赖 B-32） |
| 5 | 阶段重试 3 次上限 | 3 次全失败后 Stage 10 直接失败，管线停在 12 之前 | 与 B-8（退出码分类）一起评估是否需要「降级 + 标注」而非硬失败 |
| 6 | `data.py` 仅 181 B（第 2 次重试） | 金融数据管线可能仍缺失，对齐门大概率再否 | 需 B-32 的文件集合门兜底 |
| 7 | 现场无 `heartbeat` / `stage_health` 更新 | 无法判断「活着但停滞」 | B-31 M1 |

---

## 6. 成本统计

| 项 | 值 |
|---|---|
| Stage 10 累计失败墙钟 | 13 007 s（B）+ 14 564 s（C）+ 约 9 400 s（D，被杀）+ 运行 E 已 9 800 s ≈ **8.3 h** |
| 单次 CodeAgent 典型耗时 | 3 471 s（58 min），17 次 LLM，4 次沙箱，2 轮 review |
| LLM 调用节奏 | 约 1 次 / 3.7 min（运行 E：245 次 / 15 h 采样段） |
| 截断率 | 245 次调用中 **84 次（34%）** `completion_tokens=16384` 打满 |
| 失败重试浪费 | 每次 stage 重试丢弃前一整轮（约 17–20 次调用、70 min） |
| 观测成本 | 2.7 h 产出 22 行日志；`heartbeat` 滞后 19 h |

---

## 7. 教训与流程建议

1. **修一个暴露下一个是正常的，但要按「生成链」顺序修**。B-28/29/30 都是「有产物之后」的修复，而 F-6 让产物路径根本不成立——**应先修前置（B-32），再修后置**。
2. **成功判据比错误处理更危险**。运行 A 的 `exit_code=0` 比任何崩溃都糟：它让 25 分钟的穷产物被当作成功。任何「能跑即通过」的判据都应配结构/语义门。
3. **本地门禁与 CI 门禁的判定模式不同**。P-179..P-189 在本地提交时走 `session-progress` 模式（通过），CI 对 PR 区间走 `batch` 模式（红）。这类差异应在本地预演（本次已用 `step_enforce --base origin/main <changed>` 补齐）。
4. **未部署的修复等于没修**。B-32/B-33/B-31 都已立项成文，但 B 站跑的是旧代码，因此同一故障会持续复现。
5. **现场必须留「进行时」痕迹**。本次定位 08:43–09:45 的 62 分钟空白，只能靠 `cost_log.jsonl` 的行数与时间戳反推，成本极高。

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
```

### B. 证据文件清单

| 文件 | 用途 |
|---|---|
| `attempts/stage-10/attempt-{1,2,3}.json` | 三次阶段结果、退出码、resume_note、产物快照 |
| `stage-10/code_agent_log.json` | CodeAgent 逐阶段日志（蓝图截断、YAML 错误、回退、硬校验、exec-fix） |
| `stage-10/architecture_spec.yaml` | 蓝图原文（57 957 B，失败行 1055–1056） |
| `stage-10/agent_runs/attempt_00N/` | 每次沙箱执行的完整文件集 |
| `stage-10/experiment/` | 最终交付（config/utils/main） |
| `stage-10/ablation_warning.json` | 消融条件重复判词 |
| `stage-10/experiment_spec.md` | 阶段规格与对齐状态 |
| `cost_log.jsonl` | 调用节奏与截断率 |
| `events.jsonl` / `checkpoint.json` / `lease.json` | 阶段边界与存活信号 |
| `/tmp/p191_stage12.log`、`/tmp/p192_stage12.log` | WARNING 级现场日志 |

### C. 相关文档与提交

- 修复规格：[P-178](../spec/arc-stage10-codegen-truncation/)、[B-28](../spec/arc-stage10-repair-merge/)、[B-29](../spec/arc-stage10-entrypoint-contract/)、[B-30](../spec/arc-stage10-entrypoint-budget/)、[B-33](../spec/arc-stage10-intra-stage-checkpoint/)
- 立项调研：[B-31](arc-longrun-progress-observability-20261126.md)、[B-32](arc-stage10-blueprint-fallback-20261126.md)、[B-33](arc-stage10-intra-stage-checkpoint-20261126.md)
- 异构复审：[B-31 复审](arc-longrun-progress-review-20261126.md)、[B-33 复审](arc-stage10-checkpoint-review-20261126.md)
- 总纲：[arc-master-roadmap.md](../arc-master-roadmap.md) §3.2（B-28..B-33）
- 提交：`6274eb2`、`afd0dd5`、`9ac80b3`；PR [#55](https://github.com/StormstoutLau/AutoResearchClaw/pull/55)
