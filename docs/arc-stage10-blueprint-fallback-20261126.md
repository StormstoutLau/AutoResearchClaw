# Stage 10 蓝图 YAML 失效与单发回退退化调研（2026-11-26）

> **性质**：Layer-0 调研（候选 T3 / B-32 立项依据），零代码 / 零 session / 零门禁变更。只做取证与方案比较，不构成实施承诺。
> **触发**：P-192（B-30）部署后 B 站重跑 Stage 10-12，Stage 10 自身未报错，但产出退化为「配置类 + 配置校验入口」，与蓝图声明严重不符（详见 §1）。
> **取证环境**：B 站 `scott-lau@scott-lau-GTR-Pro.local`，run 目录 `~/arc-runs/g7-baseline`，tmux `p192-stage12`（pid 747630），取证窗口 2026-11-26 08:25–08:38 UTC（本地 16:25–16:38）。
> **方法**：E1 现场产物采样 / E2 读码锚点 / E3 对照本轮 `code_agent_log.json` 的逐行记录。**未做行为复现实验**，也未修改远端任何文件。
> **边界**：① 单一 run、单一 topic 的现场观察，样本量为 1，不外推为普遍规律；② 指标漂移的「是否可接受」属科学判断，本文只列事实；③ 时间戳为 UTC，与本地（UTC+8）相差 8 小时。

---

## 0. 结论摘要

1. **蓝图 YAML 因为「列表项以冒号结尾 + 下一行缩进续写」被判非法**。`_parse_blueprint` 的预处理只覆盖「行内 `key: value` 且值里含 `:`」，漏掉「值以 `:` 结尾」这一形态；两道解析尝试（sanitized / 原文）全部失败，`blueprint=None`。
2. **`blueprint=None` 直接跳过顺序生成**。`_is_valid_blueprint` 要求 ≥2 个 `generation_order`，于是走 `_phase2_generate_and_fix` 单发回退——**B-29/B-30 所在的顺序生成路径（含专用入口按文件生成）根本没执行**。
3. **单发回退的「成功」判据过弱**。`_exec_fix_loop` 以沙箱 `returncode == 0` 判定成功；产物只有 `config.py` + 一个「校验配置」的 `main.py`，跑通是必然的，于是形成「配置校验通过 = 实验成功」的假阳性。
4. **B-30 的入口兜底确实救回了可解析指标**：新 `experiment/main.py` 128 行、含 `METRIC_DEF`、输出真实数值（非 `nan`），且未触发 65536 升级。但**语义漂移**：蓝图的主指标是 `auroc_frechet_adjoint_minus_tau_kl`（AUROC 差值），入口打印的是窗口级 F1；蓝图要求 yfinance 真实行情，入口用 `np.random.default_rng` 合成数据。
5. **全仓没有任何「蓝图 ↔ 产物」结构比对**：蓝图声明 5 个文件、6 个 `class:`、32 处 `Monitor`，实际只交付 2 个 `.py`，6 个 monitor 类一个都没实现，却没有任何门禁报错。
6. **定位**：B-28/B-29/B-30 修的是「有顺序路径时的入口与截断」；B-32 是它们的**前置缺陷**——顺序路径压根没跑。应排在 B-9（A7-1 现场验证）之前。

---

## 1. 现场事实（E1）

### 1.1 时间线（UTC）

| 时刻 | 事件 | 证据 |
|---|---|---|
| 07:27:49 | 启动，lease 获取 | `lease.json` `fencing=1` |
| 07:39 / 07:40 / 07:44 | `attempt_001..003` | `agent_runs/` 目录 mtime |
| 07:47–08:22 | 蓝图 8192 截断 → 32768 重试 → 57948 字符 → **YAML 解析失败** → 单发回退 | `code_agent_log.json` 前 10 行 |
| 08:25 | `CodeAgent.generate()` 完成：**3471.0 s、17 次 LLM、4 次沙箱**，`Exec-fix iter 0: code runs OK` | `code_agent_log.json` 末 3 行 |
| 08:25 | `Stage 10: entrypoint contract unmet (main.py never prints METRIC_DEF); generating main.py` | `/tmp/p192_stage12.log` 第 2 行 |
| 08:27 | 新 `experiment/main.py`（6399 B / 128 行）落盘，含 `METRIC_DEF` + `__main__` | `stage-10/experiment/main.py` |
| 08:35 | `Stage 10 repair: response truncated — retrying with 32768` | 日志末行（B-28 生效） |
| 08:38 | 仍在 Stage 10 修复循环；`stage-12/` 未创建 | `ls stage-12` 为空 |

### 1.2 关键产物对账

| 维度 | 蓝图（`architecture_spec.yaml`） | 实际交付（`stage-10/experiment/`） |
|---|---|---|
| 规格体量 | 57 957 字符 | — |
| 声明文件 | `files:` 下 **5** 个条目带 `generation_order` | **2** 个 `.py`：`config.py`、`main.py` |
| 类定义 | `class:` 6 处，`Monitor` 出现 **32** 次 | 仅 `config.py` 的 5 个 Config 类；**0 个 monitor 类** |
| 主指标 | `auroc_frechet_adjoint_minus_tau_kl` = `AUROC(FrechetAdjointMonitor) − AUROC(HiddenStateTauKLMonitor)` | `primary_metric` = 窗口级 F1（`METRIC_DEF` 与 `primary_metric:` 均为此） |
| 数据来源 | `source: yfinance`，6 个标的（^GSPC/^IXIC/^DJI/^VIX/BTC-USD/ETH-USD），2018–2024 | `np.random.default_rng(seed)` 合成序列，**无任何行情读取** |
| 时间预算 | `max_seconds: 1800` | 未引用 |

### 1.3 YAML 失败原文

`code_agent_log.json`：

```
Blueprint truncated (finish_reason=length) — retrying with 32768
Blueprint spec: 57948 chars
Blueprint YAML parse error: while scanning a simple key
  in "<unicode string>", line 1055, column 5:
        HiddenStateTauKLMonitor override ...
        ^
could not find expected ':'  (line 1056)
Blueprint YAML parse error: <同上>
WARNING: Could not parse blueprint YAML
Sequential generation requested but blueprint invalid — falling back to single-shot
```

对应 `architecture_spec.yaml`：

```yaml
verification_criteria:
  - All condition classes have DIFFERENT core method implementations:
    HiddenStateTauKLMonitor overrides score with tau-rescaled KL;
    FrechetAdjointMonitor overrides score with adjoint C(t) and Fréchet distance;
    ...
```

即：列表项的值以 `:` 结尾（看起来像 mapping key 的空值），下一行同缩进级的续写被 YAML 当成新 key，缺少 `:` → 报错。

### 1.4 截断开销

| 指标 | 数值 |
|---|---|
| 本轮 LLM 调用总数 | 245（08:22 时点） |
| `completion_tokens == 16384`（打满上限，大概率截断） | 84（34%） |
| 单次打满调用耗时 | 约 4 分钟 |
| CodeAgent 总耗时 | 3471 s（58 min），其中 4 次沙箱 |

---

## 2. 机制解剖（E2）

### 2.1 蓝图生成与截断升级

[`_phase1_blueprint`](../researchclaw/pipeline/code_agent.py#L259-L307)：先以 `max_tokens=8192` 调用，`resp.truncated` 为真时以 **32768** 重试一次（[L284-289](../researchclaw/pipeline/code_agent.py#L284-L289)）。本轮该重试成功（57948 字符），所以**截断不是本次失败原因**。

### 2.2 YAML 预处理的漏判（根因）

[`_parse_blueprint`](../researchclaw/pipeline/code_agent.py#L347-L444) 的 sanitizer 逐行找 `key: value`：

- 列表项先剥掉 `- `（[L376-382](../researchclaw/pipeline/code_agent.py#L376-L382)）；
- 用 `re.search(r":\s", inner)` 定位 key 分隔符（[L390-393](../researchclaw/pipeline/code_agent.py#L390-L393)）；
- 值里含 `:` 或 `->` 才加引号（[L417-418](../researchclaw/pipeline/code_agent.py#L417-L418)）。

**`:\s` 要求冒号后必须跟空白**。本轮失败行是 `- All condition classes have DIFFERENT core method implementations:`——冒号在**行尾**，`m` 为 `None`，整行原样保留；下一行 `HiddenStateTauKLMonitor overrides score ...` 无冒号，同样原样保留。于是 YAML 得到「key 空值 + 缩进更深的裸标量」，报 `could not find expected ':'`。

同类漏判还有：值本身跨行的纯文本（本可用 `|` block scalar）、行内 `#` 注释、`[a: b]` flow 集合。本轮只命中了「行尾冒号」一种。

### 2.3 回退分支与有效性判据

[`CodeAgent.generate`](../researchclaw/pipeline/code_agent.py#L178-L221)：

- 若 `tree_search_enabled` → 走树搜索；
- 否则要求 `sequential_generation` **且** `blueprint is not None` **且** `_is_valid_blueprint(blueprint)`；
- `_is_valid_blueprint` 要求 `files` 是列表且**至少 2 个条目带 `generation_order`**（[L446-457](../researchclaw/pipeline/code_agent.py#L446-L457)）；
- 三者任一不满足 → `_phase2_generate_and_fix`（单发）。

本轮 `blueprint=None`，直接落到单发；顺序生成（含 B-29 的 `_generate_entrypoint_file`）未执行。

### 2.4 单发路径与「成功」判据

- [`_generate_code`](../researchclaw/pipeline/code_agent.py#L1040-L1090)：把 58 KB 蓝图塞进 `pkg_hint` 槽位后一次性生成，仅在「提取为空」或截断时以 32768 重试一次；**提取到 1 个文件即视为成功**。
- [`_exec_fix_loop`](../researchclaw/pipeline/code_agent.py#L1021-L1038)：`result.returncode == 0` 即 `code runs OK` 并 `break`。

两个判据都只看「能跑」，不看「跑的是不是实验」。产物 `main.py` 只做配置自检（读取 `Config()`、打印维度与 seed），天然 `rc=0`。

### 2.5 没有任何结构完整性门

全仓对 `architecture_spec` 的引用只有一处**写入**（[_code_generation.py L1173-1175](../researchclaw/pipeline/stage_impls/_code_generation.py#L1173-L1175)）。没有任何代码把 `blueprint["files"]` 与 `generated_files` 做集合比对，也没有检查 `config.primary_metric` 与入口 `METRIC_DEF` 是否一致。因此「声明 5 个文件、交付 2 个」「指标名不同」都不会触发任何门禁。

### 2.6 B-30 兜底的实际行为

`entrypoint contract unmet` 后走 `_generate_entrypoint`（32768，失败升 65536）。本轮**第 1 次即成功**，未出现升级日志。生成的 `main.py`：

- 128 行（≤150 上限）；
- 打印 `METRIC_DEF: primary_metric | direction=higher | ...`；
- 用 `np.random.default_rng` 合成 LNN 式隐状态，实现 τ-KL 与 Fréchet 两种打分并计算窗口级 F1；
- 不 import 任何算法模块（因为项目里只有 `config.py`），等于把蓝图里的算法**内联重写**——与 B-30 提示中的「Do NOT re-implement」相悖，但在当前产物形态下是唯一可行解。

---

## 3. 失效链路

- **L1 预处理漏判**：`:\s` 正则不覆盖行尾冒号 → 非法 YAML 通过预处理。
- **L2 无结构修复重试**：解析失败只记 WARNING，不做「要求模型只输出合法 YAML」的定向重试。
- **L3 静默降级**：`blueprint=None` 触发单发，只在 `_log_event` 留痕；该日志走 `logger.info`，默认级别下不可见（与 B-31 同一根因），现场日志直到 `logger.warning` 出现才可见。
- **L4 弱成功判据**：`rc==0` + 「提取到文件」双重放行，配置自检脚本满足二者。
- **L5 无结构门**：蓝图与产物、指标名、数据源三处漂移均无检查。
- **L6 伪补救**：B-30 入口兜底保证了「有指标输出」，反而让下游更难识别「实验根本没实现」。

---

## 4. 影响面

| 面 | 影响 |
|---|---|
| 科学保真度 | 主指标由 AUROC 差值变为 F1，二者不可比；论文阶段无法与蓝图假设对齐 |
| 数据真实性 | 蓝图要求真实行情（yfinance），实际为合成序列，结论不可外推 |
| 消融完整性 | 6 个 monitor 类未实现，蓝图的核心对照（tau-KL vs Fréchet vs 组合）不存在 |
| B-11 验收 | 即使 Stage 12 产出 `run-1.json`，也只能证明「管道能跑」，不能作为 A7-1/A7-5 的科学依据 |
| B-29/B-30 的验证价值 | 二者只在「有顺序路径」时生效；本轮未覆盖其主路径，其测试有效性需另找样本 |
| 成本 | 84/245 次调用打满 16384，单阶段 58 分钟；其中相当部分消耗在非法产物的反复修复上 |

---

## 5. 方案

> 原则同 B-30：不伪造、不静默降级、失败要显式。分三档，M1 可独立上线。

### 5.1 M1 / P0：让合法蓝图不再被判非法

1. **修预处理**（[L390-393](../researchclaw/pipeline/code_agent.py#L390-L393)）：key 分隔符改为「冒号后跟空白**或**行尾」；对「值以 `:` 结尾」的行统一加引号或转为 block scalar。补 4 个用例：行尾冒号、跨行纯文本、值内 `[a: b]`、值内 `#` 注释。
2. **加一次结构修复重试**：`_parse_blueprint` 失败后，用「只输出合法 YAML、不要解释」的窄提示重试 1–2 次（预算 32768），再决定是否回退。参考 B-30 的「换额度而非同额度重试」纪律。
3. **回退必须显式**：单发回退时 `logger.warning`（当前 `_log_event` 走 INFO），并在 `stage-10/decision.json` 记录 `fallback: single_shot`、`reason: blueprint_unparsable`，供 Stage 12/15 与后续审计读取。

### 5.2 M2 / P1：结构与语义门

4. **文件集合门**：`blueprint["files"]` 的名字集合必须 ⊆ 产物文件名集合；缺失时先尝试按缺失清单补齐生成，仍缺则 FAILED（不用 `rc==0` 兜底）。
5. **指标一致门**：`config.primary_metric` 的字符串必须等于入口 `METRIC_DEF` 的指标名；不等即 FAILED，错误信息给出两侧取值。
6. **数据源门**：蓝图声明的 `data.source`（如 `yfinance`）必须在产物中出现（静态字符串/import 检查）；否则至少 WARN 并在 `decision.json` 标注 `synthetic_data: true`。

### 5.3 M3 / P2：降低回退损失

7. 单发回退的产物要求最低复杂度：至少存在 1 个非 Config 的算法类或 ≥N 行的计算函数，否则判 FAILED。避免「配置自检」通过 `rc==0`。
8. 回退时为单发路径单独提高预算（当前 `max_tokens` 传入值取决于调用点），并像 B-29 那样在提示中给出文件清单与依赖顺序。

### 5.4 明确不做

- **不把 YAML 换成 JSON**：蓝图含大量多行文本，JSON 更易被模型写坏；且会破坏既有 5 份 spec 与解析器。
- **不对 `verification_criteria` 做语义解析**：它是自然语言，只需能作为字符串存下来，不参与判定。
- **不在回退后假装成功**：宁可 FAILED 并保留 `decision.json`，也不让下游拿着合成数据当真实实验。

---

## 6. 与其他编号的关系

| 编号 | 关系 |
|---|---|
| B-28（P-190） | 修 repair/review-fix 的截断与部分覆盖；本轮已生效（08:35 日志）。与 B-32 无重叠 |
| B-29（P-191） | 修入口契约 + 专用 main.py 生成；**依赖顺序路径**，B-32 不修则主路径不跑 |
| B-30（P-192） | 修入口预算与兜底；本轮救回指标，但兜底本身掩盖了 B-32 |
| B-31 | 长跑可观测性；L3 的「静默降级不可见」由 B-31 的日志修复直接缓解 |
| B-11 | Stage 10-12 现场验收；B-32 决定本次验收能否有科学意义 |
| B-9 | A7-1 72h 现场验证；**B-32 应在其之前**，否则长时间 soak 跑的是退化产物 |

---

## 7. 风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| 过度加引号 | 引号策略若过宽会把本应多行的文本压成单行，破坏语义 | 只对「行尾冒号 / 值内冒号 / 未闭合引号」三类处理，并保留原文作第二道尝试（现有逻辑已有） |
| 结构门误杀 | 蓝图可能声明可选文件 | 门只对 `generation_order` 条目生效，且允许 `optional: true` 显式豁免 |
| 指标门过严 | 允许「同义不同名」的指标 | 先做**归一化比较**（小写、去空格、去 `-`），不等再 FAILED；错误信息给出两侧 |
| 重试放大成本 | 结构修复重试增加 4–8 分钟 | 限制 2 次，且只在解析失败时触发（正常路径零成本） |
| 与 B-31 交叉 | 日志级别修复会改变现场可见性 | 两批都改 `logger.warning`，互不冲突 |

---

## 8. 待决

1. B-32 是否独立立项（T1），还是并入 B-29 的后续修复批？
2. 指标一致门失败时是 FAILED 还是「降级 + 标注」？（建议 FAILED，与 B-30「不伪造」一致）
3. 结构门是否要求「蓝图声明的每个类都必须有实现」，还是只要求文件级集合？（建议先文件级，类级留 M3）
4. B-11 的验收是否要加上「产物必须通过结构门/指标门」这一前置，避免再次拿到退化产物。

---

## 附录 A 复现命令

A-1 日志与产物（B 站）：

```bash
grep -nE 'Blueprint|Sequential|Exec-fix|entrypoint' /tmp/p192_stage12.log
python - <<'EOF'
import json, pathlib
d = json.loads(pathlib.Path("~/arc-runs/g7-baseline/stage-10/code_agent_log.json").expanduser().read_text())
print(d["llm_calls"], d["sandbox_runs"], d["review_rounds"])
print("\n".join(d["log"][:12]))
EOF
sed -n '1045,1062p' ~/arc-runs/g7-baseline/stage-10/architecture_spec.yaml
grep -cE 'generation_order|class:|Monitor' ~/arc-runs/g7-baseline/stage-10/architecture_spec.yaml
ls ~/arc-runs/g7-baseline/stage-10/experiment
grep -nE 'primary_metric' ~/arc-runs/g7-baseline/stage-10/experiment/config.py | head -3
```

A-2 读码取证（本地仓）：

```powershell
# 预处理正则（应只匹配「冒号 + 空白」）
Select-String -Path researchclaw\pipeline\code_agent.py -Pattern 're\.search\(r":\\s"'

# 回退判据
Select-String -Path researchclaw\pipeline\code_agent.py -Pattern '_is_valid_blueprint|_phase2_generate_and_fix'

# 结构门（应零命中）
Get-ChildItem researchclaw -Recurse -Filter *.py |
  Select-String -Pattern 'blueprint\[.files.\]|missing_files|structural_gate'
```

## 附录 B 证据文件

| 文件 | 用途 |
|---|---|
| `stage-10/code_agent_log.json` | 逐阶段日志（蓝图截断、YAML 错误、回退、硬校验 4 轮、exec-fix 通过） |
| `stage-10/architecture_spec.yaml` | 蓝图原文（57 957 字符，含失败行 1055） |
| `stage-10/agent_runs/attempt_004/` | 单发产物 `config.py` 13 978 B + `main.py` 1 235 B |
| `stage-10/experiment/` | B-30 兜底后的入口 `main.py` 6 399 B / 128 行 + 原 `config.py` |
| `/tmp/p192_stage12.log` | 入口契约未满足、B-28 截断重试等 WARNING 级记录 |
| `cost_log.jsonl` | 245 次调用的 token/时长，用于截断率统计 |
