# Stage 10 内部断点（intra-stage checkpoint）机制调研（2026-11-26）

> **性质**：Layer-0 调研（**B-33 立项依据**；已登记总纲 §3.2/§3.3 W0，实施未开始），零代码 / 零 session / 零门禁变更。只做取证、社区对标与方案设计。
> **立项裁决（2026-11-26）**：① 立 **B-33**；② `steps.jsonl` **先在 Stage 10 试点**，暂不推广到 Stage 12/14；③ 复审新增的 **N-1（蓝图 Phase 1 后立即落盘）归入 B-33 的 M1 范围**。
> **触发**：B 站 Stage 10（P-192 重跑）单阶段耗 3471 s / 17 次 LLM 调用；排查期间每次终止都要整体重跑，单次试错成本约 1 小时。用户要求评估「能否建立内部断点，避免反复重跑」。
> **取证环境**：B 站 `~/arc-runs/g7-baseline`（tmux `p192-stage12`，pid 747630），窗口 2026-11-26 07:27–08:38 UTC；本地仓 HEAD `56b3dde` + P-192 未提交改动。
> **方法**：E1 现场产物与 `cost_log.jsonl` 采样 / E2 读码 / E3 社区一手文档（访问 2026-11-26）。未做行为实验。
> **边界**：① 样本为单 run、单 topic；② 外部资料只作模式对照，未复现其行为；③ 本文不评估「该不该继续跑这条 topic」，只评估断点机制本身。

---

## 0. 结论摘要

1. **现状是「阶段原子」**：`checkpoint.json` 只在阶段 DONE 后写，Stage 10 内部没有任何可恢复状态。终止 = 丢弃本轮全部 LLM 工作（蓝图 + 逐文件生成 + 硬校验修复 + exec-fix + review + 入口生成 + 校验修复）。
2. **更危险的是 `--resume` 语义**：`read_checkpoint` 返回「checkpoint 的下一阶段」。本轮 checkpoint 停在上一轮的 `11`，所以 `--resume` 会**跳过未完成的 Stage 10 直接跑 Stage 12**，拿退化产物当实验。
3. **社区已有成熟范式**，可归纳为四条：**步骤级日志（journal）**、**内容寻址的结果复用（cache key = 输入 + 代码版本）**、**可重放的确定性（replay）**、**状态机显式区分「进行中/已完成」**。代表：LangGraph checkpointer、Temporal heartbeat details + Continue-As-New、Prefect 结果持久化与缓存键、Dagster materialization + code version、DBOS 步骤检查点、OpenAI Agents SDK Session/RunState、Claude Code `--resume` 会话转录、MLflow 的缓存键构成建议。
4. **推荐方案是「步骤日志 + 文件为载荷 + 版本化输入摘要」两层**：`stage-10/steps.jsonl` 记录每一步的 `step_id / inputs_digest / outputs_sha256`，产物仍写 `stage-10/experiment/`；恢复时按摘要命中跳过，命中失败才调模型。LLM 响应缓存作为**可选第二层**，默认只缓存未截断响应，避免把坏输出固化。
5. **必须同时修 `--resume` 语义**（记录 `in_progress` 阶段），否则断点机制在「整进程重启」这条主路径上不会被使用——它会先跳阶段。
6. **收益可量化**：当前一次终止损失 ≈ 3471 s（约 58 min）+ 入口生成 ~8 min ≈ **66 min / 约 20 次调用**；引入步骤日志后，最坏只重跑在途步骤（≈4 min），典型收益 **>90%**。
7. **附带收益**：与 B-31（心跳 details）、B-32（结构门）、B-28/29/30（截断与入口）互补——断点提供「从哪继续」，B-31 提供「还活着吗」，B-32 提供「继续的东西对不对」。

---

## 1. 现场问题与代价（E1）

### 1.1 本轮 Stage 10 的实际构成

`stage-10/code_agent_log.json` 终态：`llm_calls=17`、`sandbox_runs=4`、`review_rounds=2`、耗时 **3471.0 s**（[B-32 调研 §1.1](arc-stage10-blueprint-fallback-20261126.md)）。

| 阶段（CodeAgent 内部） | 调用数 | 典型耗时 | 是否持久化中间态 |
|---|---|---|---|
| Phase 1 蓝图 | 2（8192 截断 → 32768） | ~6 min | 仅终态写 `architecture_spec.yaml` |
| Phase 2 顺序生成（逐文件）或单发 | 1–N | 最长 | 仅沙箱 `attempt_NNN/` |
| Phase 2.5 硬校验修复 | ≤4（`hard_validation_max_repairs=4`） | 4 min/次 | 无 |
| Exec-fix 循环 | ≤3（`exec_fix_max_iterations=3`） | 沙箱 + 修复 | `attempt_NNN/` |
| Phase 5 Review | ≤2 轮 × 2 次（`review_max_rounds=2`） | 4–8 min | 无 |
| 入口契约生成 | ≤2（32768 → 65536） | 4–8 min | 写 `experiment/main.py` |
| 深度质量 + repair | 不定（`invalid_returns>=2` 止损） | 4 min/次 | 无 |

配置默认值见 [config.py L481-496](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/config.py#L481-L496)。

### 1.2 终止代价

| 场景 | 丢失内容 | 代价 |
|---|---|---|
| 蓝图后终止 | 蓝图 + 全部生成 | ~6 min + 后续全部 |
| 生成后、修复循环中终止（本轮实测） | 17 次调用全部 | **≈58 min** |
| 入口生成后终止 | 入口 + 校验结果 | ≈8 min |
| 本轮 08:38 终止（假设） | CodeAgent 3471 s + 入口 2 次 | **≈66 min / 约 20 次调用** |

### 1.3 当前状态面清单（可恢复吗）

| 文件 | 写入时机 | 能否用于恢复 |
|---|---|---|
| `checkpoint.json` | 阶段 DONE | 只能决定「下一个阶段」，粒度=阶段 |
| `stage-10/architecture_spec.yaml` | CodeAgent 结束 | **只写不读**（唯一引用是写入 [L1173-1175](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/stage_impls/_code_generation.py#L1173-L1175)） |
| `stage-10/code_agent_log.json` | CodeAgent 结束 | 事后日志，非状态 |
| `stage-10/agent_runs/attempt_NNN/` | 每次沙箱执行 | 仅供人看；`CodeAgent._runs` 每次重入从 001 重计，跨轮不可比 |
| `stage-10/experiment/*.py` | 逐步覆盖写 | 内容在，但没有「对应哪一步、输入是什么」的元数据 |
| `stage-10/steps.jsonl` | — | **不存在** |

---

## 2. 断点边界为什么定在阶段（E2）

1. `_write_checkpoint` 仅在 `result.status == DONE` 后调用（[runner.py L971](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/runner.py#L971)），写入内容只有 `last_completed_stage / name / timestamp / hitl`（[L192-221](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/runner.py#L192-L221)），**没有 `in_progress` 字段**。
2. `read_checkpoint` 返回**下一阶段**（[L365-395](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/runner.py#L365-L395)）；`--resume` 直接采用它（[cli.py L349-353](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/cli.py#L349-L353)）。
3. `--from-stage` 重跑**不做版本化**：`_version_rollback_stages` 只在 PIVOT/REFINE 路径调用（[runner.py L1076](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/runner.py#L1076)），手动重跑会直接覆盖 `stage-10/`，旧文件残留。
4. Stage 10 内部没有任何「已完成的子步骤」记录：`exp_dir.mkdir(exist_ok=True)` 后直接重建（[_code_generation.py L329-330](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/stage_impls/_code_generation.py#L329-L330)）。
5. LLM 层无响应缓存：`llm/` 全目录检索 `cache` 仅命中 provider 侧的 prompt-caching 用量统计与 acpx 路径缓存，**没有本地响应缓存**。

---

## 3. 社区案例（E3）

### 3.1 LangGraph：checkpointer + thread + superstep 快照

- 每个 superstep 边界把 `StateSnapshot`（图状态、待执行节点）持久化到 SQLite/Postgres，带 `thread_id`；异常后可「以 `None` 为输入、同一 thread」自动从上一个成功检查点恢复。
- 提供 durability 模式（`async` / `sync` / `exit`）权衡性能与崩溃窗口。
- **可迁移**：状态快照应是「图/阶段级 + 步骤边界」，而不是每 token；`thread_id` ≈ 我们的 `run_id + stage`。

### 3.2 Temporal：heartbeat details + Continue-As-New

- 长 Activity 在循环里 `heartbeat(details)`，details 持久化；重试时 `getHeartbeatDetails()` 从断点续跑。
- `Continue-As-New` 用同一 Workflow Id 开新 Run，历史重置——解决「历史无限增长」。
- **可迁移**：details 里放「走到第几个条目」这类最小游标即可，不必放全量数据；ARC 的 `AgentJob` 循环正好对应。

### 3.3 Prefect：结果持久化 + 缓存键

- 任务返回值落到用户自己的对象存储；缓存键默认包含 **输入 + 源代码 + 当前 flow 版本**；支持「1 小时内复用」「代码变了重跑」等策略。
- 官方定位是「Results, not Replay」——失败后加载已完成结果，而不是从头重放。
- **可迁移**：缓存键必须包含**代码版本与提示版本**，否则改了 prompt 还在用旧结果，这正是 B-32 一类问题的温床。

### 3.4 Dagster：materialization + code version + partition

- 每次 materialization 记录运行时元数据与资产版本；代码版本变化时 UI 标出「版本不一致」；分区天然支持增量重算。
- **可迁移**：「产物 + 版本 + 元数据」三者绑定；把 Stage 10 的每个文件视作一个 asset，`steps.jsonl` 就是它的 materialization 账本。

### 3.5 DBOS：步骤检查点（Postgres）

- 给 workflow/step 打注解，步骤完成即写入数据库；崩溃后从最后一个完成步骤恢复，**不重复已检查点的步骤**。
- 明确支持「replaying completed model calls from their checkpoints instead of re-contacting the provider」。
- **可迁移**：模型调用本身可作为可检查点步骤；ARC 无需 Postgres，用 append-only JSONL 即可等价。

### 3.6 OpenAI Agents SDK：Session / RunState

- `Session` 持久化对话条目，run 结束后写回；可从被中断的 `RunState` 恢复；sandbox 会话也可恢复（复用同一 session 或反序列化状态）。
- **可迁移**：把「会话/沙箱状态」与「业务状态」分开存；沙箱状态不必序列化，重开即可，但**文件产物**要留下。

### 3.7 Claude Code：`--resume` 与会话转录

- 会话转录落盘，`claude --resume <id>` / `-p --resume` 续接；`claude purge` 管理保留期。
- **可迁移**：resume 要能被**显式指定**（session id），而不是「猜最近的」；保留期需可配置。

### 3.8 LLM 响应缓存：键怎么构造

- MLflow 建议：键 = 模型标识 + **提示模板哈希（不只是填充值）** + 采样参数 + **检索/工件版本标签**；否则会持续返回基于旧文档的答案。
- OpenAI 的 prompt caching 是 provider 侧前缀缓存（省钱/提速），与本地的「结果复用」是两件事，不能互相替代。
- **可迁移**：本地缓存键必须含模板版本与上游工件摘要；provider 缓存只能降成本，不能省调用。

### 3.9 共性四原则

| # | 原则 | 代表 | 对 ARC 的含义 |
|---|---|---|---|
| D-1 | 状态按**步骤**记录，不按 token | LangGraph / DBOS | `steps.jsonl`，每步一行 |
| D-2 | 复用判据是**内容摘要**（输入 + 代码/提示版本） | Prefect / Dagster / MLflow | `inputs_digest` 含 prompt_version 与代码版本 |
| D-3 | 大载荷放文件，账本只放指针/摘要 | Dagster / Prefect | 产物落 `experiment/`，账本存 sha256 |
| D-4 | 恢复要**显式**、可审计、可禁用 | Claude Code / Temporal | `--resume` 语义修正 + `--fresh` 逃生舱 |

---

## 4. 方案设计

> 目标：单次终止的最大重跑代价从「整个阶段」降到「一个步骤」。约束：不破坏 file-as-state、事件日志 I-4（不放 prompt/大 payload）、单写者租约、现有原子写工具 `_replace_with_retry`。
>
> **M1 范围（立项裁决）**：L0（`--resume` 语义，含事件重建回填 `in_progress_stage`）+ L1（步骤账本）+ **N-1（蓝图提早落盘）**，仅 Stage 10。L2/L3 为 M2/M3，试点验收通过后评估。

### 4.1 L0：修正 `--resume` 语义（前置，成本最低）

- `checkpoint.json` 增 `in_progress_stage`：阶段开始时写，阶段 DONE 时清空。
- `read_checkpoint` 的返回值改为 `min(下一阶段, in_progress_stage)`：未完成阶段必须重入，不能跳过。
- 验收：在 Stage 10 中途 kill，`--resume` 必须落在 Stage 10 而不是 12。

### 4.2 L1：步骤账本 `stage-10/steps.jsonl`

每步一行，append-only + `flush + fsync`，复用 `filelock` 互斥（与 `stage_events.jsonl` 同模式）。锁文件用 **stage 级**（`stage-10/.steps.lock`）而非 run 级全局锁：`stage_events.jsonl` 是 run 级共享文件，`steps.jsonl` 是 stage 私有文件，分开可避免与循环守卫争锁（复审 O-3）。

```json
{
  "seq": 7,
  "ts": "2026-11-26T08:25:40+00:00",
  "stage": 10,
  "step_id": "gen:config.py",
  "attempt": 1,
  "status": "done",
  "inputs_digest": "sha256:…",
  "outputs": {"config.py": "sha256:…"},
  "model": "halogen-qwen3.8-flash-next",
  "elapsed_sec": 241.7,
  "truncated": false,
  "code_version": "code_agent@e2504a90",
  "prompt_version": "code_generation@v3"
}
```

- `step_id` 采用 **`<phase>:<subject>:<variant>`** 三段式，`variant` 承载「同类步骤的不同尝试/路径」（复审 D-2 补全）：

  | phase | subject | variant 取值 | 对应实现 |
  |---|---|---|---|
  | `blueprint` | `-` | `first`（8192）/ `retry`（32768） | [code_agent.py L284-289](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/code_agent.py#L284-L289) |
  | `gen` | `<file>` | `sequential` / `single` | 顺序路径 [_phase2_sequential_generate L461](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/code_agent.py#L461)；单发回退 [_phase2_generate_and_fix L999](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/code_agent.py#L999) |
  | `gen` | `entrypoint` | `prevalidate` / `gate` | `_ensure_entrypoint` 两个调用点（[_code_generation.py L1272](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/stage_impls/_code_generation.py#L1272)、[L2033](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/stage_impls/_code_generation.py#L2033)） |
  | `hardfix` | `-` | `<n>`（0..`hard_validation_max_repairs`） | [_hard_validate_and_repair L732](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/code_agent.py#L732) |
  | `execfix` | `-` | `<n>`（0..`exec_fix_max_iterations-1`） | [_exec_fix_loop L1026](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/code_agent.py#L1026) |
  | `review` | `-` | `<n>`（0..`review_max_rounds-1`） | [_phase4_review L1390](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/code_agent.py#L1390) |
  | `validate` | `<file>` | `<n>`（repair 轮次） | repair 循环 [_code_generation.py L1294](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/stage_impls/_code_generation.py#L1294) |
  | `finalize` | `-` | `-` | 阶段收尾 |

  幂等键为 `(step_id, inputs_digest)`：同一 step_id 在不同摘要下是**不同**条目，取 `last_done` 时按 `(step_id, variant)` 定位后再比对摘要。
- 载荷只有摘要，不放代码正文（满足 I-4 类比）。
- 记录 `truncated`：命中缓存的目的是复用**成功**步骤，截断输出必须视为未完成。
- 同一步骤的多条记录保留全部（append-only），不覆盖；`last_done` 取该 `(step_id, variant)` 下最后一条 `status=done`。

**前置修补（复审 N-1，必做）**：蓝图当前只在 `CodeAgent.generate()` 返回后才落盘（[_code_generation.py L1173-1176](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/stage_impls/_code_generation.py#L1173-L1176)），Phase 1 结束后仍在内存。若此时崩溃，磁盘上没有蓝图，账本里也就无 `outputs` 可校验。因此在 `_phase1_blueprint` 返回前**立即原子写** `stage-10/architecture_spec.yaml`（含解析失败时的原始文本），再记 `blueprint:*` 步骤。这是 L1 能否生效的前提，不能留到阶段末。

### 4.3 L2：内容寻址复用

恢复时的判定（纯函数，可单测）：

```
def should_skip(step_id, variant, inputs_digest, journal, files_on_disk) -> bool:
    last = journal.last_done(step_id, variant)
    if last is None or last.inputs_digest != inputs_digest:
        return False
    if last.code_version != CURRENT_CODE_VERSION:
        return False
    if last.prompt_version != CURRENT_PROMPT_VERSION:
        return False
    for name, expected in last.outputs.items():
        actual = files_on_disk.get(name)          # 文件被删 → None
        if actual is None or actual != expected:   # 复审 O-5：缺失必须判 miss
            return False
    return True
```

`inputs_digest` 的构成（最小集，任一项变化即重跑）：

1. `topic` / `metric` / `exp_plan` 内容摘要；
2. **蓝图摘要**：`stage-10/architecture_spec.yaml` 的 sha256（复审 D-1 核实：该项在原文已列，但见 §10 N-1——蓝图落盘时机过晚，必须先修持久化才可用）；
3. 提示模板版本：由 `runtime.mandate.prompt_version(system=…, user_template=…, model_role=…, prompt_bank_version=…)` 计算（[mandate.py L219-235](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/runtime/mandate.py#L219-L235)），或取 `RenderedPrompt.version`（[manager.py L244-261](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/prompts/manager.py#L244-L261)）——**不是** `PromptManager` 的属性（复审 D-3）；
4. 代码版本：统一算法 = `sha256(code_agent.py + _code_generation.py)` 的前 8 位，加 `researchclaw` 包版本作前缀（复审 D-4，只保留一种，不并列备选）；
5. 影响该步的配置：`max_tokens`、`hard_validation_max_repairs`、`exec_fix_max_iterations`、`review_max_rounds`。

任一项变化 → 摘要变化 → 不命中 → 重跑。**这正好把 B-32 的「改了 prompt 却复用旧产物」堵死。**

### 4.4 L3：LLM 响应缓存（可选第二层）

- 路径：`stage-10/llm_cache/<key>.json`，`key = sha256(model + system + user + max_tokens + temperature + prompt_version)`。
- 默认策略：**只缓存 `truncated == false` 且 `finish_reason == stop` 的响应**，避免把 B-30 那类截断结果固化。
- 使用策略：默认关闭；`--replay-cache` 打开（复现/调试），`--no-cache` 显式关闭。命中时写事件 `llm.cache_hit`（只含 key 前缀与 token 数）。
- 与 provider prompt caching 的区别：后者省输入 token 费用，前者省整次调用与等待时间，二者互补。
- **与 L2 的关系（复审 O-2/O-4）**：L2 复用**步骤产物**（默认开启），L3 复用**模型原始响应**（默认关闭）。二者不冲突但语义不同——L2 命中时根本不发起调用；L3 命中时仍走完整步骤逻辑，只是把 `chat()` 换成读文件。启用 L3 会让「同输入不同采样」的复查不可信，故只在显式复现模式下开启。

### 4.5 L4：与心跳/观测合流（依赖 B-31）

`ProgressKeeper` 的 payload 增：

```json
{"step_id": "gen:main.py", "steps_done": 7, "steps_total": 12,
 "last_step_elapsed_sec": 241.7, "resumed": true, "reused_steps": 6}
```

`steps_total` 在蓝图完成后可估（`len(blueprint["files"]) + 固定步骤数`）；蓝图前显示 `null`。

### 4.6 不改什么

- 不改 `checkpoint.json` 的「阶段 DONE 才推进」语义（阶段仍是事务边界）。
- 不序列化 Python 对象/沙箱会话（只留文件产物，重开沙箱）。
- 不把代码正文写进账本或事件（体积与 I-4）。
- 不对「未完成步骤」做半成品复用：只有 `status=done` 且摘要命中才跳过。

---

## 5. 失效与边界

| 风险 | 说明 | 缓解 |
|---|---|---|
| 摘要漏项 → 假命中 | 作者改了逻辑但未更新 `code_version` | 版本取包 sha256 而非手填；对 `code_agent.py`/`_code_generation.py` 计算文件哈希 |
| 产物被手工改过 | 日志说 done，磁盘已变 | 命中前逐一校验 `outputs.sha256`（§4.3 第 2 条） |
| 随机性 | 温度 >0，同输入不同输出 | 缓存是「复现」而非「等价」；默认不复用响应，仅在 `--replay-cache` 下复用 |
| 截断固化 | 缓存了坏响应 | 只缓存 `truncated=false`；否则记 `status=failed` |
| 账本与事件双写 | 两套记录可能不一致 | 账本只记步骤；事件只记 `stage.progress`；以账本为准，事件为投影 |
| fsync 放大 | 每步一次 fsync | 步骤粒度天然低频（≤20 行/阶段），可忽略 |
| 旧 run 兼容 | 无 `steps.jsonl` 的 run | 缺失即视为「全部未完成」，行为等同现状 |
| 中途 `--from-stage` 覆盖 | 旧产物混合 | L0 修正 + 重跑前归档（沿用 `.bak-pNNN` 惯例） |

---

## 6. 验收口径（可机检）

| ID | 正向 | 负向（必须红） |
|---|---|---|
| V-1 | Stage 10 中途 kill → `--resume` 落在 Stage 10 | 若落在 Stage 12 则失败（覆盖 L0） |
| V-2 | 恢复后 LLM 调用数 < 全量（**注入 mock LLM 计数器**，不依赖真实模型，复审 O-6） | 若调用数与全量相同则失败 |
| V-3 | 同一输入二次运行，`steps.jsonl` 命中率 ≥ 已完成步数 | 改 1 字节 `exp_plan` 后命中率归零 |
| V-4 | 改动 `prompt_version` → 相关步骤全部失效 | 若仍命中则失败 |
| V-5 | 篡改 `experiment/main.py` → 该步产物校验失败并重跑 | 若静默接受则失败 |
| V-6 | 删除 `experiment/main.py` → 判 cache miss 并重跑（复审 O-5） | 若因「文件不存在」而跳过则失败 |
| V-7 | 账本/事件中不出现 prompt 正文 | 命中 `system`/`user` 原文即失败 |
| V-8 | 截断响应不入缓存 | 缓存目录出现 `truncated=true` 的条目即失败 |
| V-9 | 蓝图阶段崩溃后，`architecture_spec.yaml` 已在磁盘上（复审 N-1） | 文件缺失即失败 |

---

## 7. 成本收益

| 项 | 现状 | L0+L1+L2 | 收益 |
|---|---|---|---|
| 终止后重跑 | ≈66 min / ~20 次调用 | 最坏 ≈4 min（在途步骤） | **>90%** |
| 正常路径开销 | — | 每步 1 次 append+fsync（≤20 行/阶段）+ 摘要计算（毫秒级） | 相对 Stage 10 总耗时（≈58 min）**<0.1%** |
| 代码改动面（估） | — | `runner.py`（in_progress）、`code_agent.py`（步骤钩子 + 蓝图提早落盘）、`_code_generation.py`（修复/入口钩子）、新增 `pipeline/step_journal.py`、1 个测试文件 | 中等，约 4–5 文件 |
| 风险 | — | 假命中（已由版本摘要 + 产物校验缓解） | 低 |

---

## 8. 与既有编号的关系

| 编号 | 关系 |
|---|---|
| B-31（长跑可观测） | 断点提供「从哪继续」，B-31 提供「还在跑吗」；`step_id` 是二者共同的锚点 |
| B-32（蓝图/回退） | 断点让「修好 B-32 再重跑」只花几分钟；B-32 的版本变更则让断点正确失效 |
| B-28/29/30（截断/入口/预算） | 这些修复改变了 prompt 与逻辑 → 触发 `prompt_version`/`code_version` 变化 → 断点自动失效，天然安全 |
| B-11（Stage 10-12 验收） | 有了断点，B-11 的反复试错成本从小时级降到分钟级 |
| B-8（退出码分类） | 断点不改变退出码语义；kill 后仍按退出码决定是否重启 |

---

## 9. 待决（2026-11-26 立项裁决后更新）

1. ~~是否立项（候选 B-33，T1）~~ → **已决**：立 **B-33**（T1），登记 `arc-master-roadmap.md` §3.2 与 §3.3 W0；与 B-31 分开（B-31 只读观测、B-33 写状态）。
2. L2 默认是否开启（建议：**默认开启复用已完成步骤，默认不复用 LLM 响应**）。
3. 账本保留策略（建议：随 run 目录保留，`sweep_runs` 归档时一并处理）。
4. ~~`steps.jsonl` 是否推广到 Stage 12/14~~ → **已决**：**先只在 Stage 10 试点**，验收（V-1..V-9）通过后再评估推广。
5. 与 HITL 的关系：人工修改 `experiment/` 后，是否提供 `--invalidate-step` 显式失效指令。
6. **N-1 归入 M1**：蓝图 Phase 1 返回前必须原子落盘（§4.2「前置修补」），与 L0/L1 同批交付。

---

## 10. 修正记录（2026-11-26，针对异构复审 D-1..D-4 / O-1..O-6）

> 复审报告：[arc-stage10-checkpoint-review-20261126.md](arc-stage10-checkpoint-review-20261126.md)。本节记录每条意见的**核实结论**（属实 / 不属实 / 部分属真）与落点；核实基于读码 + 现场文件，不采信复审原文。

| 意见 | 核实结论 | 处理 |
|---|---|---|
| **D-1** `inputs_digest` 漏 `architecture_spec.yaml` | **不成立**（复审误判）：原文 §4.3 第 2 项已含该项。但复核查证出一个**更真实的问题** → N-1 | 保留原表述并加指向 N-1；不改清单结构 |
| **D-2** `step_id` 未覆盖重试/多路径 | **成立**。已核实 4 类遗漏：蓝图 8192/32768 两次、单发回退、`_ensure_entrypoint` 两调用点、repair 轮次 | §4.2 改为三段式 `<phase>:<subject>:<variant>` 并给出对照表 |
| **D-3** `prompt_version` 获取方式未明确 | **成立**。`PromptManager` 无该属性；实际是 `runtime.mandate.prompt_version(...)` 自由函数（[mandate.py L219-235](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/runtime/mandate.py#L219-L235)）或 `RenderedPrompt.version` | §4.3 第 3 项改写为可调用 API |
| **D-4** `code_version` 两种备选未定夺 | **成立** | §4.3 第 4 项统一为「双文件 sha256 前 8 位 + 包版本前缀」 |
| **O-1** `<0.1%` 缺分母 | 成立 | §7 明确「相对 Stage 10 总耗时（≈58 min）」 |
| **O-2/O-4** L2 与 L3 关系不清 | 成立 | §4.4 增「与 L2 的关系」段 |
| **O-3** filelock 作用域 | 成立 | §4.2 明确 stage 级 `.steps.lock` |
| **O-5** 文件被删应判 miss | 成立（原伪代码 `files_on_disk.get(n) == h` 在删除时得 `None == h` 为假，实际已 miss，但意图不显式） | §4.3 `should_skip` 改为显式 `actual is None` 分支，并加 V-6 |
| **O-6** V-2 依赖真实 LLM | 成立 | V-2 标注「注入 mock LLM 计数器」 |

**复核中新发现（复审未列）**

| # | 事实 | 证据 | 落点 |
|---|---|---|---|
| N-1 | 蓝图只在 `CodeAgent.generate()` 返回后落盘（[_code_generation.py L1173-1176](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/stage_impls/_code_generation.py#L1173-L1176)）；Phase 1 后崩溃则磁盘无蓝图，账本无 `outputs` 可校验 | 读码 + B 站 `architecture_spec.yaml` mtime（16:25，与 `code_agent_log.json` 同刻） | §4.2 增「前置修补」；新增 V-9 |

---

## 附录 A 复现命令

```bash
# 本轮代价证据
python - <<'EOF'
import json, pathlib
d = json.loads(pathlib.Path("~/arc-runs/g7-baseline/stage-10/code_agent_log.json").expanduser().read_text())
print(d["llm_calls"], d["sandbox_runs"], d["review_rounds"])
print(d["log"][-1])
EOF

# checkpoint 语义
cat ~/arc-runs/g7-baseline/checkpoint.json

# 是否已有步骤账本（应不存在）
ls ~/arc-runs/g7-baseline/stage-10/steps.jsonl 2>&1
```

读码取证（本地仓）：

```powershell
Select-String -Path researchclaw\pipeline\runner.py -Pattern "_write_checkpoint|last_completed_stage"
Select-String -Path researchclaw\pipeline\runner.py -Pattern "def read_checkpoint"
Get-ChildItem researchclaw -Recurse -Filter *.py | Select-String -Pattern "steps\.jsonl|step_journal|in_progress_stage"
```

## 附录 B 参考资料（访问 2026-11-26）

1. LangChain, *LangGraph Durable Execution* — https://docs.langchain.com/oss/python/langgraph/durable-execution
2. LangChain, *Checkpointers* — https://docs.langchain.com/oss/javascript/langgraph/checkpointers
3. Temporal, *Long-Running Activity（heartbeat details）* — https://docs.temporal.io/design-patterns/long-running-activity
4. Temporal, *Continue-As-New* — https://docs.temporal.io/dev-guide/typescript/features
5. Prefect, *Decomposed Durability* — https://www.prefect.io/blog/decomposed-durability-a-different-approach-to-durable-execution
6. Prefect, *Durable Execution（results, not replay）* — https://www.prefect.io/solutions/durable-execution
7. Dagster, *Asset metadata and tags / code versions* — https://docs.dagster.io/guides/build/assets/metadata-and-tags
8. DBOS, *Durable Execution & Workflows on Postgres* — https://www.dbos.dev/
9. DBOS, *Architecture（step checkpoint）* — https://docs.dbos.dev/architecture
10. OpenAI, *Agents SDK — Running Agents / Sessions* — https://openai.github.io/openai-agents-js/guides/running-agents/
11. OpenAI, *Sandbox Agents（RunState 恢复）* — https://developers.openai.com/api/docs/guides/agents/sandboxes
12. Anthropic, *Claude Code — Manage sessions* — https://code.claude.com/docs/en/sessions
13. MLflow, *Building Exact-Match Request Caching（缓存键构成）* — https://mlflow.org/articles/tags/cache-llm-responses/
14. OpenAI, *Prompt caching* — https://developers.openai.com/api/docs/guides/prompt-caching
