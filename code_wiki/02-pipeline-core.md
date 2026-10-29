# 02 · 流水线核心（Stage 状态机 / Runner / Executor）

本篇是理解整个系统的核心：**阶段如何定义、如何执行、如何判定成功、如何回滚、如何恢复**。

---

## 1. 23 个阶段与 8 个 Phase

定义在 `researchclaw/pipeline/stages.py:22-62`，Phase 分组在 `stages.py:154-182`。

| # | Stage | Phase | 门控 | 主要产物 |
|---|-------|-------|------|----------|
| 1 | `TOPIC_INIT` | A 研究选题 | | `goal.md`、`hardware_profile.json` |
| 2 | `PROBLEM_DECOMPOSE` | A | | `problem_tree.md` |
| 3 | `SEARCH_STRATEGY` | B 文献发现 | | `search_plan.yaml`、`sources.json`、`queries.json` |
| 4 | `LITERATURE_COLLECT` | B | | `candidates.jsonl` |
| 5 | `LITERATURE_SCREEN` | B | ✅ Gate | `shortlist.jsonl` |
| 6 | `KNOWLEDGE_EXTRACT` | B | | `cards/` |
| 7 | `SYNTHESIS` | C 知识综合 | | `synthesis.md` |
| 8 | `HYPOTHESIS_GEN` | C | | `hypotheses.md` |
| 9 | `EXPERIMENT_DESIGN` | D 实验设计 | ✅ Gate | `exp_plan.yaml` |
| 10 | `CODE_GENERATION` | D | `hep_ph` 时 Gate | `experiment/`、`experiment_spec.md`（collider 模式为 `collider_plan.md`） |
| 11 | `RESOURCE_PLANNING` | D | | `schedule.json` |
| 12 | `EXPERIMENT_RUN` | E 实验执行 | | `runs/` |
| 13 | `ITERATIVE_REFINE` | E | | `refinement_log.json`、`experiment_final/` |
| 14 | `RESULT_ANALYSIS` | F 分析与决策 | | `analysis.md` |
| 15 | `RESEARCH_DECISION` | F | | `decision.md` |
| 16 | `PAPER_OUTLINE` | G 论文写作 | | `outline.md` |
| 17 | `PAPER_DRAFT` | G | | `paper_draft.md` |
| 18 | `PEER_REVIEW` | G | | `reviews.md` |
| 19 | `PAPER_REVISION` | G | | `paper_revised.md` |
| 20 | `QUALITY_GATE` | H 收尾 | ✅ Gate | `quality_report.json` |
| 21 | `KNOWLEDGE_ARCHIVE` | H | 非关键 | `archive.md`、`bundle_index.json` |
| 22 | `EXPORT_PUBLISH` | H | | `paper_final.md`、`code/`（以及 `paper.tex`、`references.bib`、`charts/`） |
| 23 | `CITATION_VERIFY` | H | 关键 | `verification_report.json`、`references_verified.bib` |

> `NONCRITICAL_STAGES` 只包含 Stage 21；Stage 20 与 23 被刻意设为关键阶段，失败必须阻断导出（`stages.py:140-148`）。

---

## 2. 状态与迁移

### 2.1 状态枚举

`StageStatus`（`stages.py:65-74`）：

`PENDING → RUNNING → DONE`，旁路状态包括 `BLOCKED_APPROVAL`、`APPROVED`、`REJECTED`、`PAUSED`、`RETRYING`、`FAILED`。

`TRANSITION_MAP`（`stages.py:189-203`）是允许的迁移表：

| 当前状态 | 允许的下一状态 |
|----------|----------------|
| PENDING | RUNNING |
| RUNNING | DONE / BLOCKED_APPROVAL / FAILED |
| BLOCKED_APPROVAL | APPROVED / REJECTED / PAUSED |
| APPROVED | DONE |
| REJECTED | PENDING |
| PAUSED | RUNNING |
| RETRYING | RUNNING |
| FAILED | RETRYING / PAUSED |
| DONE | （终态） |

### 2.2 `advance()` 的行为

`advance(stage, status, event)`（`stages.py:252-361`）把「当前阶段 + 状态 + 事件」映射为 `TransitionOutcome`：

| 事件 | 前置状态 | 结果 |
|------|----------|------|
| `START` | PENDING / RETRYING / PAUSED | RUNNING |
| `SUCCEED` | RUNNING | 若该阶段需要门控 → BLOCKED_APPROVAL；否则 DONE 并指向下一阶段 |
| `APPROVE` | BLOCKED_APPROVAL | DONE + 下一阶段 |
| `REJECT` | BLOCKED_APPROVAL | 回滚到 `GATE_ROLLBACK` 目标，状态 PENDING |
| `TIMEOUT` | BLOCKED_APPROVAL | PAUSED |
| `FAIL` | RUNNING | FAILED |
| `RETRY` | FAILED | RETRYING |
| `RESUME` | PAUSED | RUNNING |
| `PAUSE` | FAILED | PAUSED |

`TransitionOutcome` 还携带 `rollback_stage`、`checkpoint_required`、`decision`，供 Runner/Executor 决定是否落盘。

> 注意：`execute_stage` 内部只调用了 `advance(stage, PENDING, START)` 做语义校验；真正决定阶段产物与门控的是 Executor 自己的逻辑（见 §4）。因此状态机是「规则描述」而非唯一执行路径。

### 2.3 门控阶段与回滚目标

`GATE_STAGES`（`stages.py:109-115`）：Stage 5、9、20。

`GATE_ROLLBACK`（`stages.py:118-123`）：

| 被拒绝的门 | 回滚到 |
|------------|--------|
| LITERATURE_SCREEN (5) | LITERATURE_COLLECT (4) |
| EXPERIMENT_DESIGN (9) | HYPOTHESIS_GEN (8) |
| CODE_GENERATION (10) | EXPERIMENT_DESIGN (9) |
| QUALITY_GATE (20) | PAPER_OUTLINE (16) |

`gate_required()`（`stages.py:216-244`）额外把 `profile == "hep_ph"` 下的 Stage 10 视为强制门，不受 `security.hitl_required_stages` 过滤。

### 2.4 PIVOT / REFINE 回滚

Stage 15 产出 `decision.md` 与 `StageResult.decision`。`DECISION_ROLLBACK`（`stages.py:129-132`）：

| decision | 回滚目标 | 含义 |
|----------|----------|------|
| `pivot` | HYPOTHESIS_GEN (8) | 丢弃假设，重新生成研究方向 |
| `refine` | ITERATIVE_REFINE (13) | 保留假设，重跑/改进实验 |

`MAX_DECISION_PIVOTS = 2`（`stages.py:134`），防止无限循环。达到上限后强制 `PROCEED`，并可写入 `quality_warning.txt`。

---

## 3. 阶段契约（StageContract）

### 3.1 数据结构

`pipeline/contracts.py:18-27`：

| 字段 | 含义 |
|------|------|
| `stage` | 阶段枚举 |
| `input_files` | 本阶段读取的前序产物（相对 run 目录或 stage 目录） |
| `output_files` | 本阶段必须产出的文件/目录（目录以 `/` 结尾） |
| `collider_output_files` | `collider_agent` 模式下的替代输出 |
| `dod` | Definition of Done，人类可读的验收标准 |
| `error_code` | 唯一错误码（如 `E09_GATE_REJECT`） |
| `max_retries` | 失败重试次数建议 |

### 3.2 契约如何被使用

`execute_stage`（`executor.py:594-819`）：

1. 执行前遍历 `contract.input_files`，用 `_read_prior_artifact()` 查找；找不到立即失败（`executor.py:615-627`）。
2. 执行成功后遍历 `contract.output_files`（collider 模式用 `_select_output_files()` 替换），检查文件存在且非空，目录非空（`executor.py:680-705`）。
3. 任一缺失 → `StageStatus.FAILED`，`error="Missing or empty output: ..."`，`decision="retry"`。

这使得「阶段实现返回 DONE 但没写产物」也会被兜住，是产物导向设计的核心保障。

完整的 23 条契约（输入/输出/DoD/错误码/重试）见 [03-stage-reference.md](03-stage-reference.md)。

---

## 4. `execute_stage()`：单阶段执行流程

实现：`researchclaw/pipeline/executor.py:594`。

```
execute_stage(stage)
├─ 1. HITL 前置钩子 _run_hitl_pre_stage()          # 可按策略暂停、SKIP/ABORT/注入指导
├─ 2. 创建 stage-XX/ 目录，读取 StageContract
├─ 3. 校验 input_files                              # 缺失即 FAILED(retry)
├─ 4. OpenClaw 通知/记忆（若 bridge 开启）
├─ 5. 创建 LLM 客户端（ACP 或 OpenAI 兼容）
├─ 6. advance(PENDING, START) 语义校验
├─ 7. 构建 PromptManager（domain → ml/hep_ph/biology，加载 overrides/extra_prompts）
├─ 8. 从 _STAGE_EXECUTORS 取函数并调用
│     └─ 兼容旧签名：若函数不接受 prompts= 则回退调用
├─ 9. 捕获异常 → FAILED(retry)
├─ 10. 输出契约校验（文件/目录存在且非空）
├─ 11. MetaClaw PRM 质量门（可选；分数 -1 时 FAILED）
├─ 12. Gate 判定：门控阶段且未 auto-approve → BLOCKED_APPROVAL
├─ 13. 写 decision.json + stage_health.json
└─ 14. HITL 后置钩子 _run_hitl_post_stage()
      ├─ CostGuard 预算检查
      ├─ SmartPause 置信度检查
      ├─ APPROVE / REJECT / EDIT / SKIP / ABORT / COLLABORATE / INJECT
      └─ 返回可能被修改的 StageResult
```

### 4.1 分发与阶段实现

`_STAGE_EXECUTORS`（`executor.py:567-591`）把 23 个 Stage 映射到 `stage_impls/` 中的 `_execute_xxx` 函数：

| 文件 | 覆盖阶段 |
|------|----------|
| `stage_impls/_topic.py` | 1–2 |
| `stage_impls/_literature.py` | 3–6 |
| `stage_impls/_synthesis.py` | 7–8 |
| `stage_impls/_experiment_design.py` | 9 |
| `stage_impls/_code_generation.py` | 10 |
| `stage_impls/_execution.py` | 11–13 |
| `stage_impls/_analysis.py` | 14–15 |
| `stage_impls/_paper_writing.py` | 16–17 |
| `stage_impls/_review_publish.py` | 18–23 |

### 4.2 结果对象 `StageResult`

`pipeline/_helpers.py:34-43`：

```python
@dataclass(frozen=True)
class StageResult:
    stage: Stage
    status: StageStatus
    artifacts: tuple[str, ...]
    error: str | None = None
    decision: str = "proceed"      # proceed / retry / block / pivot / abort / degraded
    evidence_refs: tuple[str, ...] = ()
```

`decision` 是 Runner 做回滚/中止判断的关键字段；`evidence_refs` 用于把产物路径回填到论文/KB 中。

---

## 5. `execute_pipeline()`：整条流水线

实现：`researchclaw/pipeline/runner.py:431-912`。

### 5.1 参数

| 参数 | 作用 |
|------|------|
| `run_dir` / `run_id` | 本次运行目录与 ID |
| `config` | `RCConfig` |
| `adapters` | `AdapterBundle`（含可选 `hitl`） |
| `from_stage` / `to_stage` | 起止阶段（支持断点续跑与局部重跑） |
| `auto_approve_gates` | 自动通过门控 |
| `stop_on_gate` | 遇到 BLOCKED_APPROVAL 是否立即停止 |
| `skip_noncritical` | 非关键阶段失败时是否跳过 |
| `kb_root` | 知识库根目录（可选） |
| `cancel_event` | 线程取消事件（Web 服务使用） |

### 5.2 主循环顺序

1. **强制领域**：若 `config.project.profile` 非空，调用 `set_forced_profile()`，保证所有 Stage 的领域检测一致（`runner.py:451-458`）。
2. **集成钩子（全部可选）**：`EventLog`、`ExperimentMemory`、成本预算（`runner.py:460-481`）。
3. 遍历 `STAGE_SEQUENCE`：
   - `_should_start()` 跳过 `from_stage` 之前的阶段；
   - 检查 `cancel_event`；
   - 成本预算超限则停止；
   - 进入 Stage 16 前调用 `_promote_best_stage14()`，确保写作使用最佳实验数据；
   - `execute_stage()`；
   - 写事件日志；
   - Stage 9 后生成 `experiment_spec.md`；Stage 14 后按 spec 校验结果；
   - Stage 10/12 后运行 `PitfallDetector`（若可用）；
   - Stage 12/13 后写入 `ExperimentMemory`；
   - 成功后写 KB、`checkpoint.json`、`heartbeat.json`；
   - `to_stage` 到达则停止；
   - Stage 14 后运行实验诊断 `_run_experiment_diagnosis()`，必要时运行修复循环 `_run_experiment_repair()`（agent 模式跳过）；
   - Stage 15 的 PIVOT/REFINE：读 `pivot_count`、检查连续空指标、版本化回滚目录、递归调用 `execute_pipeline()`；
   - `abort` / `FAILED` / `PAUSED` / `REJECTED` / `BLOCKED_APPROVAL` 的处理。
4. 循环结束：
   - `_build_pipeline_summary()` + `pipeline_summary.json`；
   - `extract_lessons()` + `EvolutionStore`；
   - MetaClaw `lesson_to_skill` 后处理；
   - `_package_deliverables()`；
   - HITL 会话 finalize（abort/complete）。

### 5.3 PIVOT/REFINE 的细节

- `pivot_count = len(decision_history.json)`;
- 若 `pivot_count > 0` 且连续 REFINE 产生空指标 → 强制 PROCEED，避免无意义循环（`runner.py:706-716`）；
- 否则若 `pivot_count < 2`：
  - agent 模式的 `refine` 直接回到 Stage 12（而不是 13），因为 Stage 13 对 agent 模式是 no-op；
  - `_version_rollback_stages(run_dir, target, attempt)` 把将被覆盖的 `stage-XX` 重命名为 `stage-XX_vN`；
  - 递归执行并 `break`，由递归调用完成后续阶段；
  - 递归结束后 `_promote_best_stage14()`。
- 达到上限：`_check_experiment_quality()` 决定是否写 `quality_warning.txt`，然后强制 PROCEED。

### 5.4 Stage 14 诊断与修复

- `_run_experiment_diagnosis()`（`runner.py:209`）：解析 stdout/stderr/metrics/计划，输出 `experiment_diagnosis.json`，分类缺陷（无完成条件、缺 baseline、种子不足、OOM、依赖缺失等，`pipeline/experiment_diagnosis.py:23-40`）。
- 若 `repair_needed`，`_run_experiment_repair()`（`runner.py:346`）调用修复循环：诊断 → 生成修复 prompt → OpenCode/LLM 改写代码 → 沙箱重跑 → 重新评估，最多 3 轮（`experiment_repair.py:34`）。
- 该逻辑对 `collider_agent` / `biology_agent` / `stat_agent` 跳过（它们在 Stage 12 原子完成，`runner.py:669-682`）。

---

## 6. Prompt 解析链

每个 Stage 的提示词由 `PromptManager`（`prompts/manager.py:102`）组装：

```
PromptManager(
    overrides_path = config.prompts.custom_file,
    domain         = 由 profile/检测得到的提示库（ml / hep_ph / biology_metabolic）,
    extra_prompts  = config.prompts.extra_prompts
)
```

- `_load_bank(domain)`：`hep_ph` → `prompts/hep.py`；`biology_metabolic` → `prompts/biology.py`；其他 → `prompts/ml.py`（`manager.py:74-94`）。
- YAML 覆盖只允许修改已存在的 stage/block/sub_prompt，未知键会 warning 并丢弃。
- `extra_prompts` 的值可以是内联文本或文件路径；未知 stage 名会被丢弃并 warning（`manager.py:181-211`）。
- 领域 `PromptAdapter` 在 Stage 9/10/14/22 额外注入领域块（`domains/prompt_adapter.py:52-110`）。

---

## 7. 检查点、恢复与心跳

| 机制 | 文件 | 代码 |
|------|------|------|
| 检查点 | `checkpoint.json` | `_write_checkpoint()` `runner.py:78-107`；原子写（临时文件 + replace） |
| 读取下一阶段 | `read_checkpoint()` | `runner.py:126-144`：返回 `last_completed_stage` 的**下一个** Stage |
| 恢复入口 | `resume_from_checkpoint()` | `runner.py:146-151` |
| 心跳 | `heartbeat.json` | `_write_heartbeat()` `runner.py:110-123`（pid、stage、timestamp） |
| 看门狗 | `sentinel.sh` | 心跳 >5 分钟且 PID 死亡 → 重启（脚本头部说明） |
| 决策历史 | `decision_history.json` | `_read_pivot_count()` / `_record_decision_history()` `runner.py:1557-1593` |
| 阶段元数据 | `stage-XX/decision.json` | `_write_stage_meta()` `_helpers.py:306-328` |
| 阶段健康 | `stage-XX/stage_health.json` | `executor.py:801-816` |

`--resume` 时 CLI 还会在 `artifacts/` 下按 topic hash 找到最近的 run 目录（`cli.py:244-281`），避免新建空目录。

---

## 8. 失败语义与降级

| 情况 | 行为 |
|------|------|
| 阶段实现抛异常 | `FAILED`，`decision="retry"`，Runner 在非 `skip_noncritical` 时停止 |
| 契约输出缺失 | `FAILED`，`decision="retry"` |
| PRM 分数 -1 | `FAILED`，`decision="retry"` |
| 门控未批准且 `stop_on_gate=True` | 停在 `BLOCKED_APPROVAL` |
| HITL 拒绝 | `REJECTED`，Runner 停止（CLI 的 HITL 流程会单独处理回滚） |
| HITL 中止 | `decision="abort"`，Runner 停止 |
| 质量降级 | `result.decision == "degraded"`，打印 DEGRADED 但继续 |
| 非关键阶段失败 | `skip_noncritical=True` 时记录 warning 并继续 |
| 可选模块导入失败 | warning/debug 日志，不阻断（EventLog、ExperimentMemory、PitfallDetector、MetaClaw 等） |

---

## 9. 交付物打包

`_package_deliverables()`（`runner.py:915-...`）按「最佳可用版本优先」收集：

| 交付物 | 优先级 |
|--------|--------|
| `paper_final.md` | `stage-23/paper_final_verified.md` > `stage-22/paper_final.md` |
| `paper.tex` | 若 Stage 22 有 `sanitization_report.json` 则保留已清洗的 Stage 22 版本；否则可从验证后的 Markdown 重新生成 |
| `references.bib` | `stage-23/references_verified.bib` > `stage-22/references.bib` |
| `code/` | `stage-22/code/` |
| `verification_report.json` | `stage-23/` |
| `sanitization_report.json` | `stage-22/` |
| `charts/` | `stage-22/charts/` |

若用户未显式覆盖 `export.target_conference`，且领域适配器声明了 `preferred_template`，会使用领域模板而非默认 `neurips_2025`。

---

## 10. 迭代式流水线（次级 API）

`execute_iterative_pipeline()`（`runner.py:1629`）在首次跑完 Stage 1–22 后，若质量分低于阈值，则重跑 Stage 16–22 并注入评审反馈；停止条件为：

- 分数 ≥ `quality_threshold`（默认 7.0）；
- 连续 `convergence_rounds` 轮无提升；
- 达到 `max_iterations`（默认 3）。

> 当前 CLI 与 Web 路由都直接调用 `execute_pipeline()`，`execute_iterative_pipeline()` 属于可编程 API/实验性入口。

---

## 11. 关键函数索引

| 名称 | 位置 | 作用 |
|------|------|------|
| `Stage` / `StageStatus` / `TransitionEvent` | `pipeline/stages.py:22/65/77` | 阶段、状态、事件枚举 |
| `advance()` | `pipeline/stages.py:252` | 计算状态迁移 |
| `gate_required()` | `pipeline/stages.py:216` | 判断阶段是否需要人工门控 |
| `StageContract` / `CONTRACTS` | `pipeline/contracts.py:18/29` | 阶段 I/O 契约 |
| `execute_pipeline()` | `pipeline/runner.py:431` | 顺序执行、回滚、检查点、收尾 |
| `execute_iterative_pipeline()` | `pipeline/runner.py:1629` | 写作质量迭代 |
| `read_checkpoint()` / `resume_from_checkpoint()` | `pipeline/runner.py:126/146` | 断点恢复 |
| `_package_deliverables()` | `pipeline/runner.py:915` | 汇总最终交付物 |
| `execute_stage()` | `pipeline/executor.py:594` | 单阶段执行与契约校验 |
| `_STAGE_EXECUTORS` | `pipeline/executor.py:567` | Stage → 实现函数分发表 |
| `_run_hitl_pre_stage()` / `_run_hitl_post_stage()` | `pipeline/executor.py:200/257` | HITL 前置/后置钩子 |
| `StageResult` | `pipeline/_helpers.py:34` | 阶段结果对象 |
| `PromptManager` | `prompts/manager.py:102` | 提示库选择、覆盖与渲染 |
